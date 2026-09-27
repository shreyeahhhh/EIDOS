"""The write-through model: a durable event log and a durable artifact store for one run (decisions.md D-230; ``docs/13`` section 2.3; invariants 1, 2, 8 and 15).

**The in-memory log is the runtime authority for a run; the database is behind it, never ahead of it.** ``DurableEventLog`` is an ``EventLog`` that overrides ``accept`` and nothing else: it
calls the real intake, so the reducer decides what is applied, and only an *applied* record is handed to the run's outbox. ``EventLog``, ``Recorder``, ``record_attempt`` and the reducer are
untouched, and nothing the reducer refused is ever persisted. ``WriteThroughArtifactStore`` keeps the run's artifacts in memory (the runtime's own store, read on the hot path) and hands each
put to the same outbox.

**One ordered outbox per run.** A flush is one ``EventStore.commit``: the pending artifacts, then the pending events, then ``last_sequence``, atomically, guarded by the expected durable
sequence. An artifact is put before the event that settles the node that produced it, so a durable event never names an artifact that is not durable.

**Fail-soft.** The recorder holds its lock and nodes run on worker threads, so a flush failure must never raise into the runtime. It is kept, the run is marked degraded, and every later
accept and the final flush retry the whole outbox in order. ``finish`` retries a bounded number of times. If the outbox still cannot be flushed the caller ends the run ``error`` (reason
``persistence``); the events that never reached the database exist only in memory and are lost when the process exits, and the API says so. A ``SequenceConflict`` is retried once as a
read (the commit may have landed although its answer was lost) and is otherwise permanent: another writer touched this mission, and the run must not carry on writing.

The recorder's lock is held while a flush runs, so database latency serialises node settlements. That is the accepted MVP cost (D-230).
"""

import threading
import time
from collections.abc import Callable

from eidos.agents import Artifact, ArtifactConflict, InMemoryArtifactStore
from eidos.contracts import ArtifactRef, ExecutionId, MissionId, StepId, TenantId
from eidos.state import EventLog, EventProposal, EventRecord, IntakeResult

from .ports import ArtifactWrite, EventStore, SequenceConflict


class RunPersistence:
    """The outbox of one run, and the only thing that writes it to the store."""

    def __init__(
        self,
        *,
        events: EventStore,
        tenant_id: TenantId,
        mission_id: MissionId,
        execution_id: ExecutionId,
        attempts: int = 3,
        backoff_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if attempts < 1:
            raise ValueError("a flush is attempted at least once")
        self._events, self._tenant_id, self._mission_id, self._execution_id = events, tenant_id, mission_id, execution_id
        self._attempts, self._backoff, self._sleep = attempts, backoff_seconds, sleep
        self._lock = threading.Lock()
        self._artifacts: list[ArtifactWrite] = []
        self._records: list[EventRecord] = []
        self._durable_last = 0
        self.degraded = False
        self.failure: str | None = None  # set once, permanently: the store will not take this run's writes
        self.last_error: str | None = None

    @property
    def durable_last_sequence(self) -> int:
        with self._lock:
            return self._durable_last

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._artifacts) + len(self._records)

    def add_artifact(self, write: ArtifactWrite) -> None:
        with self._lock:
            self._artifacts.append(write)
            self._flush_locked()

    def add_event(self, record: EventRecord) -> None:
        with self._lock:
            self._records.append(record)
            self._flush_locked()

    def finish(self) -> bool:
        """The final flush, retried a bounded number of times. ``True`` if everything the run produced is durable."""
        for attempt in range(self._attempts):
            with self._lock:
                if self._flush_locked():
                    return True
                if self.failure is not None:
                    return False
            if attempt + 1 < self._attempts:
                self._sleep(self._backoff * (attempt + 1))
        return False

    def _flush_locked(self) -> bool:
        if self.failure is not None:
            return False
        if not self._artifacts and not self._records:
            return True
        try:
            self._durable_last = self._events.commit(
                tenant_id=self._tenant_id, mission_id=self._mission_id, execution_id=self._execution_id,
                expected_last_sequence=self._durable_last, artifacts=tuple(self._artifacts), events=tuple(self._records),
            )
        except SequenceConflict as conflict:
            if self._already_durable():
                self._durable_last += len(self._records)
                self._artifacts.clear()
                self._records.clear()
                self.degraded = False
                return True
            self.failure = f"sequence_conflict: {str(conflict)[:200]}"
            return False
        except ArtifactConflict as conflict:
            self.failure = f"artifact_conflict: {str(conflict)[:200]}"
            return False
        except Exception as error:  # noqa: BLE001 - a store fault must never reach the runtime; it is kept and retried
            self.degraded = True
            self.last_error = f"{type(error).__name__}: {str(error)[:200]}"
            return False
        self._artifacts.clear()
        self._records.clear()
        self.degraded = False
        return True

    def _already_durable(self) -> bool:
        """Whether a commit that raised a conflict had in fact landed: the durable log already holds exactly the pending events, in order."""
        try:
            durable = self._events.read(self._tenant_id, self._mission_id, after=self._durable_last, limit=len(self._records))
        except Exception:  # noqa: BLE001
            return False
        return bool(self._records) and len(durable) == len(self._records) and all(
            held.event.event_id == pending.event.event_id and held.event.sequence == pending.event.sequence for held, pending in zip(durable, self._records)
        )


class DurableEventLog(EventLog):
    """An ``EventLog`` whose applied records also go to a run's outbox. Only ``accept`` and ``accept_resumed`` are overridden, and both call the real intake first."""

    def __init__(self, persistence: RunPersistence) -> None:
        super().__init__()
        self._persistence = persistence

    def accept(self, proposal: EventProposal) -> IntakeResult:
        result = super().accept(proposal)
        if result.applied and result.record is not None:
            self._persistence.add_event(result.record)
        return result

    def accept_resumed(self, proposal: EventProposal) -> IntakeResult:
        result = super().accept_resumed(proposal)
        if result.applied and result.record is not None:
            self._persistence.add_event(result.record)
        return result


class WriteThroughArtifactStore:
    """The run's artifact store: memory is what the run reads and writes; every put is also handed to the outbox. The ``ArtifactStore`` contract is unchanged (write-once, thread-safe)."""

    def __init__(self, persistence: RunPersistence) -> None:
        self._memory = InMemoryArtifactStore()
        self._persistence = persistence

    def preload(self, execution_id: ExecutionId, artifacts: tuple[Artifact, ...]) -> None:
        """Put artifacts that are already durable (the documents the caller supplied at creation) into memory, without writing them again."""
        for artifact in artifacts:
            self._memory.put_supplied(execution_id, artifact)

    def put_supplied(self, execution_id: ExecutionId, artifact: Artifact) -> None:
        self._memory.put_supplied(execution_id, artifact)  # raises ArtifactConflict before anything is queued
        self._persistence.add_artifact(ArtifactWrite(artifact=artifact, kind="supplied"))

    def put_step_artifact(self, execution_id: ExecutionId, step_id: StepId, artifact: Artifact) -> None:
        self._memory.put_step_artifact(execution_id, step_id, artifact)
        self._persistence.add_artifact(ArtifactWrite(artifact=artifact, kind="step", step_id=step_id))

    def get(self, execution_id: ExecutionId, ref: ArtifactRef) -> Artifact | None:
        return self._memory.get(execution_id, ref)

    def get_step_artifact(self, execution_id: ExecutionId, step_id: StepId) -> Artifact | None:
        return self._memory.get_step_artifact(execution_id, step_id)

    def supplied(self, execution_id: ExecutionId) -> tuple[Artifact, ...]:
        return self._memory.supplied(execution_id)
