"""In-memory implementations of the repository ports (decisions.md D-230, D-234).

The default test suite runs the whole service on these, so it needs no database and no credentials. They hold the same contract as the PostgreSQL adapters and are checked by the
same contract tests: tenant scoping on every call, compare-and-set transitions, an append that must continue the log exactly, write-once artifacts, idempotent re-commits.

Provisioning (``add_tenant``, ``add_member``) is out of band in production (D-233); the helpers here exist so a test can stand a tenant up. They are not part of any port.
"""

import threading
from collections.abc import Sequence
from datetime import datetime

from eidos.agents import Artifact, ArtifactConflict, ArtifactStore, InMemoryArtifactStore
from eidos.contracts import ArtifactRef, ExecutionId, MissionId, StepId, TenantId
from eidos.state import EventRecord

from .ports import (
    ACTIVE,
    ArtifactWrite,
    DuplicateIdempotencyKey,
    Membership,
    MissionRecord,
    Repositories,
    Role,
    RunStatus,
    SequenceConflict,
    UserId,
    personal_workspace_id,
)

_NIL = "00000000-0000-0000-0000-000000000000"


def _updated(record: MissionRecord, **changes) -> MissionRecord:
    """A validated copy with some fields changed. (``model_copy`` and ``model_construct`` are forbidden anywhere in ``src``: they skip validation.)"""
    fields = {name: getattr(record, name) for name in MissionRecord.model_fields}
    fields.update(changes)
    return MissionRecord.model_validate(fields)


class _TenantArtifacts:
    """An ``ArtifactStore`` bound to one tenant: an execution of another tenant is simply not there."""

    def __init__(self, storage: "InMemoryStorage", tenant_id: TenantId):
        self._storage, self._tenant_id = storage, tenant_id

    def _store(self, execution_id: ExecutionId) -> InMemoryArtifactStore:
        return self._storage._artifact_store(self._tenant_id, execution_id)

    def put_supplied(self, execution_id: ExecutionId, artifact: Artifact) -> None:
        self._store(execution_id).put_supplied(execution_id, artifact)

    def put_step_artifact(self, execution_id: ExecutionId, step_id: StepId, artifact: Artifact) -> None:
        self._store(execution_id).put_step_artifact(execution_id, step_id, artifact)

    def get(self, execution_id: ExecutionId, ref: ArtifactRef) -> Artifact | None:
        return self._store(execution_id).get(execution_id, ref)

    def get_step_artifact(self, execution_id: ExecutionId, step_id: StepId) -> Artifact | None:
        return self._store(execution_id).get_step_artifact(execution_id, step_id)

    def supplied(self, execution_id: ExecutionId) -> tuple[Artifact, ...]:
        return self._store(execution_id).supplied(execution_id)


class InMemoryStorage:
    """``TenancyRepository``, ``MissionRepository`` and ``EventStore`` in one object, behind one lock."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tenants: dict[TenantId, str] = {}
        self._members: dict[UserId, list[Membership]] = {}
        self._missions: dict[MissionId, MissionRecord] = {}
        self._events: dict[MissionId, list[EventRecord]] = {}
        self._artifacts: dict[tuple[TenantId, ExecutionId], InMemoryArtifactStore] = {}

    # --- provisioning, out of band (not a port) -----------------------------------------------------------------------------------

    def add_tenant(self, tenant_id: TenantId, name: str = "tenant") -> None:
        if str(tenant_id) == _NIL:
            raise ValueError("the nil tenant is a reserved sentinel: a real tenant may never take it (D-233)")
        with self._lock:
            self._tenants[tenant_id] = name

    def add_member(self, tenant_id: TenantId, user_id: UserId, role: Role = Role.MEMBER) -> None:
        with self._lock:
            if tenant_id not in self._tenants:
                raise ValueError("no such tenant")
            if any(m.tenant_id == tenant_id for m in self._members.get(user_id, ())):
                raise ValueError("already a member")  # as the primary key refuses it in PostgreSQL
            self._members.setdefault(user_id, []).append(Membership(tenant_id=tenant_id, role=role))

    def repositories(self) -> Repositories:
        return Repositories(tenancy=self, missions=self, events=self, artifacts=self.artifacts_for)

    def artifacts_for(self, tenant_id: TenantId) -> ArtifactStore:
        return _TenantArtifacts(self, tenant_id)

    def _artifact_store(self, tenant_id: TenantId, execution_id: ExecutionId) -> InMemoryArtifactStore:
        with self._lock:
            return self._artifacts.setdefault((tenant_id, execution_id), InMemoryArtifactStore())

    # --- TenancyRepository --------------------------------------------------------------------------------------------------------

    def memberships_of(self, user_id: UserId) -> tuple[Membership, ...]:
        with self._lock:
            return tuple(sorted(self._members.get(user_id, ()), key=lambda m: str(m.tenant_id)))

    def provision_personal_workspace(self, user_id: UserId, name: str) -> tuple[Membership, ...]:
        with self._lock:
            tenant_id = personal_workspace_id(user_id)
            self._tenants.setdefault(tenant_id, name)
            members = self._members.setdefault(user_id, [])
            if not any(m.tenant_id == tenant_id for m in members):
                members.append(Membership(tenant_id=tenant_id, role=Role.OWNER))
            return self.memberships_of(user_id)

    # --- MissionRepository --------------------------------------------------------------------------------------------------------

    def create(self, record: MissionRecord, documents: Sequence[Artifact]) -> None:
        with self._lock:
            if record.tenant_id not in self._tenants:
                raise ValueError("no such tenant")
            if record.idempotency_key is not None and self.find_by_idempotency_key(record.tenant_id, record.idempotency_key) is not None:
                raise DuplicateIdempotencyKey(record.idempotency_key)
            if record.mission_id in self._missions:
                raise ValueError("a mission with this id exists")
            store = self._artifact_store(record.tenant_id, record.execution_id)
            for document in documents:
                store.put_supplied(record.execution_id, document)
            self._missions[record.mission_id] = record
            self._events[record.mission_id] = []

    def get(self, tenant_id: TenantId, mission_id: MissionId) -> MissionRecord | None:
        with self._lock:
            record = self._missions.get(mission_id)
            return record if record is not None and record.tenant_id == tenant_id else None

    def find_by_idempotency_key(self, tenant_id: TenantId, key: str) -> MissionRecord | None:
        with self._lock:
            return next((r for r in self._missions.values() if r.tenant_id == tenant_id and r.idempotency_key == key), None)

    def transition(
        self, tenant_id: TenantId, mission_id: MissionId, *, expected: Sequence[RunStatus], new: RunStatus, reason: str | None, at: datetime
    ) -> bool:
        with self._lock:
            record = self.get(tenant_id, mission_id)
            if record is None or record.run_status not in expected:
                return False
            self._missions[mission_id] = _updated(record, run_status=new, run_status_reason=reason, run_updated_at=at)
            return True

    def count_active(self, tenant_id: TenantId) -> int:
        with self._lock:
            return sum(1 for r in self._missions.values() if r.tenant_id == tenant_id and r.run_status in ACTIVE)

    def interrupt_active(self, *, reason: str, at: datetime) -> int:
        with self._lock:
            moved = 0
            for mission_id, record in list(self._missions.items()):
                if record.run_status in ACTIVE:
                    self._missions[mission_id] = _updated(record, run_status=RunStatus.INTERRUPTED, run_status_reason=reason, run_updated_at=at)
                    moved += 1
            return moved

    # --- EventStore ---------------------------------------------------------------------------------------------------------------

    def commit(
        self,
        *,
        tenant_id: TenantId,
        mission_id: MissionId,
        execution_id: ExecutionId,
        expected_last_sequence: int,
        artifacts: Sequence[ArtifactWrite],
        events: Sequence[EventRecord],
    ) -> int:
        with self._lock:
            record = self.get(tenant_id, mission_id)
            if record is None or record.execution_id != execution_id:
                raise SequenceConflict("no such mission for this tenant")
            if record.last_sequence != expected_last_sequence:
                raise SequenceConflict(f"the durable last sequence is {record.last_sequence}, not {expected_last_sequence}")
            for offset, event in enumerate(events, start=1):
                if event.event.sequence != expected_last_sequence + offset or event.event.mission_id != mission_id or event.event.tenant_id != tenant_id:
                    raise SequenceConflict("the events do not continue the log exactly")
            store = self._artifact_store(tenant_id, execution_id)
            writes: list[ArtifactWrite] = []  # validate every artifact before any is applied, so the commit is atomic
            batch: dict[ArtifactRef, Artifact] = {}
            for write in artifacts:
                ref = write.artifact.ref
                existing = batch.get(ref) or store.get(execution_id, ref)
                if existing is not None:
                    if existing != write.artifact:
                        raise ArtifactConflict(f"ref {str(ref)!r} is already stored with other content")
                    continue  # an identical artifact is a repeat of an earlier commit: idempotent
                if write.kind == "step" and store.get_step_artifact(execution_id, write.step_id) is not None:
                    raise ArtifactConflict(f"step {str(write.step_id)!r} already has its primary artifact")
                batch[ref] = write.artifact
                writes.append(write)
            for write in writes:
                if write.kind == "step":
                    store.put_step_artifact(execution_id, write.step_id, write.artifact)
                else:
                    store.put_supplied(execution_id, write.artifact)
            self._events[mission_id].extend(events)
            new_last = expected_last_sequence + len(events)
            self._missions[mission_id] = _updated(record, last_sequence=new_last)
            return new_last

    def read(self, tenant_id: TenantId, mission_id: MissionId, *, after: int = 0, limit: int | None = None) -> tuple[EventRecord, ...]:
        with self._lock:
            if self.get(tenant_id, mission_id) is None:
                return ()
            selected = [r for r in self._events.get(mission_id, ()) if r.event.sequence > after]
            return tuple(selected if limit is None else selected[:limit])
