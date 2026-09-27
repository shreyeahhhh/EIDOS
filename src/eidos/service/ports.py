"""The repository ports the service is written against (decisions.md D-230, D-233; ``docs/13`` sections 2 and 5).

**A repository is durable storage. It is never a runtime authority.** The events it holds are the mission's history and the fold of them is ``MissionState``; nothing here stores a
``MissionState``, an ``ExecutionRecord`` or a status the reducer folds. The one value derived from the log, ``last_sequence``, is an append guard: the log wins on any mismatch.

**Every operation is tenant-scoped.** Each method takes the ``TenantId`` and answers only for that tenant; a resource of another tenant is indistinguishable from one that does not
exist (D-233). ``eidos.service.memory`` implements these ports in memory (the default suite runs on it), and ``eidos.persistence`` implements them on PostgreSQL. Both are held to the same
contract tests.

``ArtifactStore`` is the existing port (D-137, D-145) and is not redefined here; a repository hands out one bound to a tenant.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, NewType, Protocol
from uuid import UUID

from pydantic import Field

from eidos.agents import Artifact, ArtifactStore
from eidos.contracts import EidosModel, ExecutionId, MissionId, ReliabilityContractId, StepId, TenantId
from eidos.contracts._validators import UtcDateTime
from eidos.state import EventRecord

from .spec import MissionSpec

UserId = NewType("UserId", UUID)  # the Supabase user id (the JWT subject); it lives in the service and the database and in no core contract


class Role(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class RunStatus(StrEnum):
    """The API-level lifecycle of a run (D-234). It is **never** a ``MissionStatus``, never an event and never in ``MissionState``."""

    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    REJECTED = "rejected"
    INTERRUPTED = "interrupted"
    ERROR = "error"


ACTIVE = (RunStatus.QUEUED, RunStatus.RUNNING)
TERMINAL = (RunStatus.FINISHED, RunStatus.REJECTED, RunStatus.INTERRUPTED, RunStatus.ERROR)


@dataclass(frozen=True, slots=True)
class Membership:
    tenant_id: TenantId
    role: Role


class MissionRecord(EidosModel):
    """One row of ``missions``. ``spec`` is the accepted request without its documents (they are supplied artifacts). Once events exist, they are authoritative."""

    mission_id: MissionId
    tenant_id: TenantId
    execution_id: ExecutionId
    contract_id: ReliabilityContractId
    created_by: UUID
    created_at: UtcDateTime
    spec: MissionSpec
    spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    run_status: RunStatus = RunStatus.CREATED
    run_status_reason: str | None = None
    run_updated_at: UtcDateTime
    last_sequence: int = Field(default=0, ge=0)


@dataclass(frozen=True, slots=True)
class ArtifactWrite:
    """One artifact put, as the run's outbox carries it: a supplied artifact, or a step's primary artifact."""

    artifact: Artifact
    kind: Literal["supplied", "step"]
    step_id: StepId | None = None


class SequenceConflict(Exception):
    """An append whose expected ``last_sequence`` is not the durable one: another writer, or a writer that already committed."""


class StorageError(Exception):
    """The store could not be reached or did not answer in time. Retriable; never a mission outcome."""


class DuplicateIdempotencyKey(Exception):
    """A mission with this ``(tenant, idempotency key)`` already exists."""


class TenancyRepository(Protocol):
    def memberships_of(self, user_id: UserId) -> tuple[Membership, ...]: ...


class MissionRepository(Protocol):
    def create(self, record: MissionRecord, documents: Sequence[Artifact]) -> None:
        """Store the mission and its supplied documents together. Raises ``DuplicateIdempotencyKey``."""

    def get(self, tenant_id: TenantId, mission_id: MissionId) -> MissionRecord | None: ...

    def find_by_idempotency_key(self, tenant_id: TenantId, key: str) -> MissionRecord | None: ...

    def transition(
        self, tenant_id: TenantId, mission_id: MissionId, *, expected: Sequence[RunStatus], new: RunStatus, reason: str | None, at: datetime
    ) -> bool:
        """Compare and set: move ``run_status`` to ``new`` only if it is one of ``expected``. ``True`` if it moved."""

    def count_active(self, tenant_id: TenantId) -> int:
        """Runs of this tenant that are ``queued`` or ``running``."""

    def interrupt_active(self, *, reason: str, at: datetime) -> int:
        """Startup recovery: every ``queued`` or ``running`` run becomes ``interrupted``. Writes no event. Returns how many."""


class EventStore(Protocol):
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
        """One atomic write: the artifacts, then the events, then ``last_sequence``. The events must continue the log exactly after ``expected_last_sequence``.

        Raises ``SequenceConflict`` if the durable ``last_sequence`` is not ``expected_last_sequence`` or the events are not contiguous from it. Idempotent for an artifact
        that is already stored identically. Returns the new ``last_sequence``.
        """

    def read(self, tenant_id: TenantId, mission_id: MissionId, *, after: int = 0, limit: int | None = None) -> tuple[EventRecord, ...]:
        """The records with ``sequence > after``, in sequence order, at most ``limit``."""


@dataclass(frozen=True, slots=True)
class Repositories:
    tenancy: TenancyRepository
    missions: MissionRepository
    events: EventStore
    artifacts: Callable[[TenantId], ArtifactStore]
