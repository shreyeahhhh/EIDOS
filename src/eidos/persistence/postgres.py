"""PostgreSQL adapters for the service ports (decisions.md D-230, D-233; ``docs/13`` section 2).

The only module that imports psycopg. It implements ``TenancyRepository``, ``MissionRepository`` and ``EventStore`` from ``eidos.service`` and hands out tenant-bound ``ArtifactStore``
objects. **It stores the event stream and nothing derived from it**: no ``MissionState``, no ``ExecutionRecord``; a caller replays events to get either. Every query filters on the tenant, so a
row of another tenant is never returned and never touched.

**No session state**, so every Supabase connection mode works (to be verified against Supabase's current documentation, which lists prepared statements, ``SET`` and advisory locks as
unavailable through the transaction pooler): server-side prepared statements are switched off (``prepare_threshold=None``), the statement timeout is a connection option rather than a ``SET`` statement, and every timestamp is converted to UTC when it is read, so the session time zone is never relied on, and every mutation is a single compare-and-set statement or one short transaction.

A connection or timeout fault becomes ``StorageError`` (retriable, never a mission outcome). An append that does not continue the log exactly raises ``SequenceConflict``. A second write of an
artifact reference with other content raises ``ArtifactConflict``, and an identical one is idempotent.
"""

import json
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg
from psycopg import errors as pg_errors
from psycopg_pool import ConnectionPool, PoolTimeout

from eidos.agents import Artifact, ArtifactConflict
from eidos.contracts import ArtifactRef, ExecutionId, MissionId, ReliabilityContractId, StepId, TenantId
from eidos.service import (
    ArtifactWrite,
    DuplicateIdempotencyKey,
    Membership,
    MissionRecord,
    MissionSpec,
    Repositories,
    Role,
    RunStatus,
    SequenceConflict,
    StorageError,
    UserId,
    personal_workspace_id,
)
from eidos.state import EventRecord

_MISSION_COLUMNS = (
    "mission_id, tenant_id, execution_id, contract_id, created_by, created_at, spec::text, spec_sha256, idempotency_key, run_status, run_status_reason, run_updated_at, last_sequence"
)
_ARTIFACT_COLUMNS = "ref, content_type, content, source_refs, kind, step_id"


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc)


def _mission(row) -> MissionRecord:
    (mission_id, tenant_id, execution_id, contract_id, created_by, created_at, spec, digest, key, status, reason, updated_at, last_sequence) = row
    return MissionRecord(
        mission_id=MissionId(mission_id), tenant_id=TenantId(tenant_id), execution_id=ExecutionId(execution_id), contract_id=ReliabilityContractId(contract_id), created_by=created_by,
        created_at=_utc(created_at), spec=MissionSpec.model_validate_json(spec), spec_sha256=digest, idempotency_key=key, run_status=RunStatus(status), run_status_reason=reason,
        run_updated_at=_utc(updated_at), last_sequence=last_sequence,
    )


def _artifact(row) -> Artifact:
    ref, content_type, content, source_refs = row[0], row[1], row[2], row[3]
    return Artifact(ref=ArtifactRef(ref), content_type=content_type, content=content, source_refs=tuple(ArtifactRef(item) for item in source_refs))


class PostgresStorage:
    """``TenancyRepository``, ``MissionRepository`` and ``EventStore`` over one connection pool."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    @classmethod
    def open(cls, connection_string: str, *, min_size: int = 1, max_size: int = 8, statement_timeout_ms: int = 10_000, connect_timeout_seconds: int = 10) -> "PostgresStorage":
        pool = ConnectionPool(
            connection_string, min_size=min_size, max_size=max_size, open=False,
            # D-241: a connection the remote end (or a NAT, or a sleeping laptop's network) dropped while idle looks open until it is used, and then the first request waits for the operating system to give up
            # (about 20 s) before failing 503. ``check`` makes the pool test a connection as it is handed out and quietly replace a dead one (one cheap round trip per checkout); the keepalives stop an idle
            # connection being dropped in the first place; ``tcp_user_timeout`` bounds how long a send to a dead peer can wait. All of these are libpq connection parameters, set by the client alone.
            check=ConnectionPool.check_connection,
            kwargs={
                "prepare_threshold": None, "connect_timeout": connect_timeout_seconds, "options": f"-c statement_timeout={statement_timeout_ms}",
                "keepalives": 1, "keepalives_idle": 30, "keepalives_interval": 10, "keepalives_count": 3, "tcp_user_timeout": 10_000,
            },
        )
        try:
            pool.open(wait=True, timeout=float(connect_timeout_seconds))
        except PoolTimeout as error:
            pool.close()
            raise StorageError("the database could not be reached") from error
        return cls(pool)

    def close(self) -> None:
        self._pool.close()

    def repositories(self) -> Repositories:
        return Repositories(tenancy=self, missions=self, events=self, artifacts=self.artifacts_for)

    def artifacts_for(self, tenant_id: TenantId) -> "PostgresArtifacts":
        return PostgresArtifacts(self, tenant_id)

    @contextmanager
    def _transaction(self):
        """A connection in a transaction that commits on success and rolls back on any exception; a connection or timeout fault becomes ``StorageError``."""
        try:
            with self._pool.connection() as connection:
                yield connection
        except (psycopg.OperationalError, psycopg.InterfaceError, pg_errors.QueryCanceled, PoolTimeout) as error:
            raise StorageError(f"{type(error).__name__}") from error

    # --- provisioning helpers for tests (out of band in production; not a port) ------------------------------------------------------------

    def add_tenant(self, tenant_id: TenantId, name: str = "tenant") -> None:
        with self._transaction() as connection:
            connection.execute("insert into eidos.tenants (tenant_id, name) values (%s, %s)", (tenant_id, name))

    def add_member(self, tenant_id: TenantId, user_id: UserId, role: Role = Role.MEMBER) -> None:
        with self._transaction() as connection:
            connection.execute("insert into eidos.tenant_members (tenant_id, user_id, role) values (%s, %s, %s)", (tenant_id, user_id, role.value))

    # --- TenancyRepository --------------------------------------------------------------------------------------------------------

    def memberships_of(self, user_id: UserId) -> tuple[Membership, ...]:
        with self._transaction() as connection:
            rows = connection.execute("select tenant_id, role from eidos.tenant_members where user_id = %s order by tenant_id", (user_id,)).fetchall()
        return tuple(Membership(tenant_id=TenantId(tenant_id), role=Role(role)) for tenant_id, role in rows)

    def provision_personal_workspace(self, user_id: UserId, name: str) -> tuple[Membership, ...]:
        tenant_id = personal_workspace_id(user_id)
        with self._transaction() as connection:  # both inserts are no-ops on a repeat, so two racing first requests end with the same one tenant and one membership
            connection.execute("insert into eidos.tenants (tenant_id, name) values (%s, %s) on conflict (tenant_id) do nothing", (tenant_id, name))
            connection.execute(
                "insert into eidos.tenant_members (tenant_id, user_id, role) values (%s, %s, %s) on conflict (tenant_id, user_id) do nothing", (tenant_id, user_id, Role.OWNER.value)
            )
        return self.memberships_of(user_id)

    # --- MissionRepository --------------------------------------------------------------------------------------------------------

    def create(self, record: MissionRecord, documents: Sequence[Artifact]) -> None:
        try:
            with self._transaction() as connection:
                connection.execute(
                    "insert into eidos.missions (mission_id, tenant_id, execution_id, contract_id, created_by, created_at, spec, spec_sha256, idempotency_key, run_status, "
                    "run_status_reason, run_updated_at, last_sequence) values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)",
                    (
                        record.mission_id, record.tenant_id, record.execution_id, record.contract_id, record.created_by, record.created_at, record.spec.model_dump_json(),
                        record.spec_sha256, record.idempotency_key, record.run_status.value, record.run_status_reason, record.run_updated_at, record.last_sequence,
                    ),
                )
                for document in documents:
                    _insert_artifact(connection, record.execution_id, record.tenant_id, ArtifactWrite(artifact=document, kind="supplied"))
        except pg_errors.UniqueViolation as error:
            if error.diag.constraint_name == "missions_idempotency":
                raise DuplicateIdempotencyKey(record.idempotency_key or "") from error
            raise

    def get(self, tenant_id: TenantId, mission_id: MissionId) -> MissionRecord | None:
        with self._transaction() as connection:
            row = connection.execute(f"select {_MISSION_COLUMNS} from eidos.missions where mission_id = %s and tenant_id = %s", (mission_id, tenant_id)).fetchone()
        return None if row is None else _mission(row)

    def find_by_idempotency_key(self, tenant_id: TenantId, key: str) -> MissionRecord | None:
        with self._transaction() as connection:
            row = connection.execute(f"select {_MISSION_COLUMNS} from eidos.missions where tenant_id = %s and idempotency_key = %s", (tenant_id, key)).fetchone()
        return None if row is None else _mission(row)

    def transition(
        self, tenant_id: TenantId, mission_id: MissionId, *, expected: Sequence[RunStatus], new: RunStatus, reason: str | None, at: datetime
    ) -> bool:
        with self._transaction() as connection:
            cursor = connection.execute(
                "update eidos.missions set run_status = %s, run_status_reason = %s, run_updated_at = %s where mission_id = %s and tenant_id = %s and run_status = any(%s)",
                (new.value, reason, at, mission_id, tenant_id, [status.value for status in expected]),
            )
            return cursor.rowcount == 1

    def count_active(self, tenant_id: TenantId) -> int:
        with self._transaction() as connection:
            (count,) = connection.execute("select count(*) from eidos.missions where tenant_id = %s and run_status in ('queued', 'running')", (tenant_id,)).fetchone()
        return int(count)

    def interrupt_active(self, *, reason: str, at: datetime) -> int:
        with self._transaction() as connection:
            cursor = connection.execute(
                "update eidos.missions set run_status = 'interrupted', run_status_reason = %s, run_updated_at = %s where run_status in ('queued', 'running')", (reason, at)
            )
            return cursor.rowcount

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
        for offset, event in enumerate(events, start=1):
            if event.event.sequence != expected_last_sequence + offset or event.event.mission_id != mission_id or event.event.tenant_id != tenant_id:
                raise SequenceConflict("the events do not continue the log exactly")
        new_last = expected_last_sequence + len(events)
        try:
            with self._transaction() as connection:
                # the guard first: it takes the row's lock, so two writers of one mission are serialised and the loser sees the winner's sequence
                cursor = connection.execute(
                    "update eidos.missions set last_sequence = %s where mission_id = %s and tenant_id = %s and execution_id = %s and last_sequence = %s",
                    (new_last, mission_id, tenant_id, execution_id, expected_last_sequence),
                )
                if cursor.rowcount != 1:
                    raise SequenceConflict(f"the durable last sequence is not {expected_last_sequence}, or there is no such mission for this tenant")
                for write in artifacts:
                    _insert_artifact(connection, execution_id, tenant_id, write)
                for event in events:
                    connection.execute(
                        "insert into eidos.mission_events (mission_id, tenant_id, sequence, event_id, event_type, occurred_at, record) values (%s, %s, %s, %s, %s, %s, %s::jsonb)",
                        (mission_id, tenant_id, event.event.sequence, event.event.event_id, event.event.type.value, event.event.occurred_at, event.model_dump_json()),
                    )
        except pg_errors.UniqueViolation as error:
            if error.diag.constraint_name == "artifacts_one_primary_per_step":
                raise ArtifactConflict("a step already has its primary artifact") from error
            raise SequenceConflict(f"a uniqueness rule refused the append: {error.diag.constraint_name}") from error
        return new_last

    def read(self, tenant_id: TenantId, mission_id: MissionId, *, after: int = 0, limit: int | None = None) -> tuple[EventRecord, ...]:
        with self._transaction() as connection:
            rows = connection.execute(
                "select record::text from eidos.mission_events where mission_id = %s and tenant_id = %s and sequence > %s order by sequence limit %s",
                (mission_id, tenant_id, after, limit),
            ).fetchall()
        return tuple(EventRecord.model_validate_json(text) for (text,) in rows)


def _insert_artifact(connection, execution_id: ExecutionId, tenant_id: TenantId, write: ArtifactWrite) -> None:
    artifact = write.artifact
    source_refs = json.dumps([str(ref) for ref in artifact.source_refs])
    cursor = connection.execute(
        "insert into eidos.artifacts (execution_id, tenant_id, ref, kind, step_id, content_type, content, source_refs) values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb) "
        "on conflict (execution_id, ref) do nothing",
        (execution_id, tenant_id, str(artifact.ref), write.kind, None if write.step_id is None else str(write.step_id), artifact.content_type, artifact.content, source_refs),
    )
    if cursor.rowcount == 0:  # the reference is taken: an identical artifact is a repeat of an earlier commit, anything else is a conflict
        row = connection.execute(
            f"select {_ARTIFACT_COLUMNS} from eidos.artifacts where execution_id = %s and tenant_id = %s and ref = %s", (execution_id, tenant_id, str(artifact.ref))
        ).fetchone()
        if row is None or _artifact(row) != artifact:
            raise ArtifactConflict(f"ref {str(artifact.ref)!r} is already stored with other content")


class PostgresArtifacts:
    """An ``ArtifactStore`` over the ``artifacts`` table, bound to one tenant. Write-once; an execution of another tenant is simply not there."""

    def __init__(self, storage: PostgresStorage, tenant_id: TenantId) -> None:
        self._storage, self._tenant_id = storage, tenant_id

    def _put(self, execution_id: ExecutionId, write: ArtifactWrite) -> None:
        try:
            with self._storage._transaction() as connection:
                cursor = connection.execute(
                    "insert into eidos.artifacts (execution_id, tenant_id, ref, kind, step_id, content_type, content, source_refs) values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb) "
                    "on conflict (execution_id, ref) do nothing",
                    (
                        execution_id, self._tenant_id, str(write.artifact.ref), write.kind, None if write.step_id is None else str(write.step_id), write.artifact.content_type,
                        write.artifact.content, json.dumps([str(ref) for ref in write.artifact.source_refs]),
                    ),
                )
                if cursor.rowcount == 0:
                    raise ArtifactConflict(f"ref {str(write.artifact.ref)!r} is already taken in this execution")
        except pg_errors.UniqueViolation as error:
            raise ArtifactConflict("a step already has its primary artifact") from error
        except pg_errors.ForeignKeyViolation as error:
            raise ValueError("no such execution for this tenant") from error

    def put_supplied(self, execution_id: ExecutionId, artifact: Artifact) -> None:
        self._put(execution_id, ArtifactWrite(artifact=artifact, kind="supplied"))

    def put_step_artifact(self, execution_id: ExecutionId, step_id: StepId, artifact: Artifact) -> None:
        self._put(execution_id, ArtifactWrite(artifact=artifact, kind="step", step_id=step_id))

    def get(self, execution_id: ExecutionId, ref: ArtifactRef) -> Artifact | None:
        with self._storage._transaction() as connection:
            row = connection.execute(
                f"select {_ARTIFACT_COLUMNS} from eidos.artifacts where execution_id = %s and tenant_id = %s and ref = %s", (execution_id, self._tenant_id, str(ref))
            ).fetchone()
        return None if row is None else _artifact(row)

    def get_step_artifact(self, execution_id: ExecutionId, step_id: StepId) -> Artifact | None:
        with self._storage._transaction() as connection:
            row = connection.execute(
                f"select {_ARTIFACT_COLUMNS} from eidos.artifacts where execution_id = %s and tenant_id = %s and kind = 'step' and step_id = %s",
                (execution_id, self._tenant_id, str(step_id)),
            ).fetchone()
        return None if row is None else _artifact(row)

    def supplied(self, execution_id: ExecutionId) -> tuple[Artifact, ...]:
        """Ordered by reference in code-point order, exactly as the in-memory store orders them: the database collation must not change what a model is shown."""
        with self._storage._transaction() as connection:
            rows = connection.execute(
                f"select {_ARTIFACT_COLUMNS} from eidos.artifacts where execution_id = %s and tenant_id = %s and kind = 'supplied' order by ref collate \"C\"",
                (execution_id, self._tenant_id),
            ).fetchall()
        return tuple(_artifact(row) for row in rows)


__all__ = ["PostgresArtifacts", "PostgresStorage"]
