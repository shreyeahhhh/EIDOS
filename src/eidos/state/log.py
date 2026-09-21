"""The append-only event log and its intake (decisions.md D-155, D-157, D-160; invariants 1, 2 and 8).

**The event log is authoritative.** ``MissionState`` is only its materialized view — a fold — and ``ExecutionRecord`` is derived from it (D-157
item 1). The log holds **applied events only**, contiguous from sequence 1, so a log is always replayable.

**Producers propose; the intake orders; the reducer alone writes state.** A producer hands the intake an ``EventProposal`` — identity, times and
a typed payload, but *no sequence*. The intake assigns the next sequence at acceptance (D-011), ignores a repeated ``event_id``, asks the reducer
whether the event fits, and appends it only if it does. A proposal that does not fit (a duplicate, or one after a terminal state, or one that
does not fit the state) is returned with its outcome and is not appended: **ordering is the EIDOS-assigned sequence and nothing else**, and no
order is inferred from a timestamp (D-160 item 7).

The log is not thread-safe, and this module imports no threading: whoever feeds it from several threads serializes access, and the order in which
they get through is the order the log records. Nothing here reads a clock or draws an identifier; the producer supplies both.
"""

from pydantic import ValidationError

from eidos.contracts import EidosModel, EventId, MissionEvent, MissionId, MissionState, TenantId
from eidos.contracts._validators import UtcDateTime

from .records import EventRecord, Payload
from .reducer import ReduceOutcome, reduce
from .replay import Checkpoint, ReplayRejection, dump_jsonl, replay


class EventProposal(EidosModel):
    """What a producer offers the intake. The sequence is deliberately absent: EIDOS assigns it, not the producer (D-011)."""

    event_id: EventId
    tenant_id: TenantId
    mission_id: MissionId
    occurred_at: UtcDateTime
    recorded_at: UtcDateTime
    payload: Payload


class IntakeResult(EidosModel):
    """What happened to one proposal. ``record`` is the appended record when the outcome is ``APPLIED`` and ``None`` otherwise."""

    outcome: ReduceOutcome
    reason: str | None = None
    record: EventRecord | None = None
    state: MissionState | None = None  # the mission state after this call: the new one if applied, the unchanged one if not

    @property
    def applied(self) -> bool:
        return self.outcome is ReduceOutcome.APPLIED


class EventLog:
    def __init__(self) -> None:
        self._records: list[EventRecord] = []
        self._applied: frozenset[EventId] = frozenset()
        self._state: MissionState | None = None

    @classmethod
    def restore(cls, records) -> "EventLog | ReplayRejection":
        """A log holding ``records``, if they replay; otherwise the typed reason they do not. Appending can then continue."""
        materialized = tuple(records)
        folded = replay(materialized)
        if folded.rejection is not None:
            return folded.rejection
        log = cls()
        log._records = list(materialized)
        log._applied = frozenset(r.event.event_id for r in materialized)
        log._state = folded.state
        return log

    @property
    def records(self) -> tuple[EventRecord, ...]:
        return tuple(self._records)

    @property
    def state(self) -> MissionState | None:
        """The view: what the reducer has folded so far. ``None`` until ``MISSION_CREATED`` has been accepted."""
        return self._state

    @property
    def applied_event_ids(self) -> frozenset[EventId]:
        return self._applied

    def __len__(self) -> int:
        return len(self._records)

    def accept(self, proposal: EventProposal) -> IntakeResult:
        """Order, check and append one proposal. Never raises for a proposal that does not fit."""
        if proposal.event_id in self._applied:
            return self._refused(ReduceOutcome.DUPLICATE, f"event {str(proposal.event_id)!r} was already applied")
        try:
            record = EventRecord(
                event=MissionEvent(
                    event_id=proposal.event_id,
                    tenant_id=proposal.tenant_id,
                    mission_id=proposal.mission_id,
                    sequence=len(self._records) + 1,
                    occurred_at=proposal.occurred_at,
                    recorded_at=proposal.recorded_at,
                    type=proposal.payload.event_type,
                ),
                payload=proposal.payload,
            )
        except ValidationError as error:
            return self._refused(ReduceOutcome.INVALID_FOR_STATE, "the proposal is inconsistent: " + str(error.errors()[0]["msg"]))
        result = reduce(self._state, record, self._applied)
        if not result.applied:
            return IntakeResult(outcome=result.outcome, reason=result.reason, state=self._state)
        self._records.append(record)
        self._applied = self._applied | {record.event.event_id}
        self._state = result.state
        return IntakeResult(outcome=ReduceOutcome.APPLIED, record=record, state=self._state)

    def _refused(self, outcome: ReduceOutcome, reason: str) -> IntakeResult:
        return IntakeResult(outcome=outcome, reason=reason, state=self._state)

    def checkpoint(self) -> Checkpoint | None:
        """The checkpoint at the last applied sequence, taken because the caller asked; ``None`` if nothing has been applied."""
        if self._state is None:
            return None
        return Checkpoint(state=self._state, last_sequence=len(self._records))

    def to_jsonl(self) -> str:
        return dump_jsonl(self._records)
