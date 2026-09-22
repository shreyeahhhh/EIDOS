"""Replay, the strict JSONL form, and the checkpoint value (decisions.md D-157; invariants 1, 8 and 15).

**Replay consumes recorded events and nothing else.** It folds ``EventRecord`` values through the reducer; it imports no agent, provider or
model and makes no call to one, so it cannot re-run an agent (invariant 15). It reconstructs the mission state. Artifact *content* is not in
the log — an ``ArtifactRef`` only — so replay does not reconstruct artifact text (D-157 item 5; D-129 and D-017 stay Open).

A log is *replayable* only if every record applies: contiguous from sequence 1, one mission and tenant, beginning with ``MISSION_CREATED``. The
first record that does not apply is a **typed rejection** carrying its sequence and the reducer's own outcome — never a partial replay
(D-157 item 6).

**JSONL** is one ``EventRecord`` per line, produced by the strict JSON serialization: deterministic field order, UTC timestamps, and a parsed
log equal to the original. A line that does not parse is a typed rejection naming its line number. This is the whole of V0.5's persistence:
there is no file, no database and no store here (D-157 item 3; D-017 stays Open).

A **checkpoint** is a value — the mission state and the last applied sequence — taken only when the caller asks and never automatically. Resuming
applies the events after its sequence, and the invariant that is tested is that **a checkpoint plus the tail equals a full replay**. It is not a
checkpointer of any execution backend (D-113, D-127).
"""

from collections.abc import Iterable
from enum import StrEnum

from pydantic import Field, ValidationError, model_validator

from eidos.contracts import EidosModel, EventId, MissionState

from .agent_task_events import AgentTaskEventKey, agent_task_event_key, repeated_agent_task_event
from .records import EventRecord
from .reducer import ReduceOutcome, reduce
from .step_events import StepEventKey, repeated_step_event, step_event_key


class ReplayRejectionCode(StrEnum):
    EMPTY_LOG = "empty_log"
    MALFORMED_LINE = "malformed_line"  # a JSONL line that is not a valid EventRecord
    NOT_APPLICABLE = "not_applicable"  # a record the reducer did not apply
    BAD_CHECKPOINT = "bad_checkpoint"  # a checkpoint asked for at a sequence the log does not have


class ReplayRejection(EidosModel):
    code: ReplayRejectionCode
    reason: str = Field(min_length=1)
    sequence: int | None = Field(default=None, ge=1)  # the record that did not apply
    line: int | None = Field(default=None, ge=1)  # the JSONL line that did not parse
    outcome: ReduceOutcome | None = None  # what the reducer said, when it did

    @model_validator(mode="after")
    def _check_the_locators_match_the_code(self) -> "ReplayRejection":
        if (self.code is ReplayRejectionCode.NOT_APPLICABLE) != (self.outcome is not None):
            raise ValueError("exactly a not_applicable rejection carries the reducer's outcome")
        if (self.code is ReplayRejectionCode.MALFORMED_LINE) != (self.line is not None):
            raise ValueError("exactly a malformed_line rejection names its line")
        return self


class ReplayResult(EidosModel):
    """The state a log folds to, or the reason it does not. Exactly one of the two."""

    state: MissionState | None = None
    rejection: ReplayRejection | None = None

    @model_validator(mode="after")
    def _check_exactly_one(self) -> "ReplayResult":
        if (self.state is None) == (self.rejection is None):
            raise ValueError("a replay yields a state or a rejection, never both and never neither")
        return self

    @property
    def replayed(self) -> bool:
        return self.state is not None


class Checkpoint(EidosModel):
    """The mission state and the last applied sequence. The applied ``event_id`` set is derived from the log, not stored here (D-157)."""

    state: MissionState
    last_sequence: int = Field(ge=1)

    @model_validator(mode="after")
    def _check_the_sequence_is_the_states_version(self) -> "Checkpoint":
        if self.last_sequence != self.state.state_version:
            raise ValueError("last_sequence must equal the state's state_version (D-097)")
        return self


def _fold(
    state: MissionState | None,
    applied: frozenset[EventId],
    seen: frozenset[StepEventKey],
    task_seen: frozenset[AgentTaskEventKey],
    records: Iterable[EventRecord],
) -> tuple[MissionState | None, ReplayRejection | None]:
    for record in records:
        result = reduce(state, record, applied)
        if result.applied:
            repeated = repeated_step_event(seen, record)  # the intake refuses this live, so a log it wrote never has one (D-162 item 1)
            if repeated is not None:
                return state, ReplayRejection(
                    code=ReplayRejectionCode.NOT_APPLICABLE,
                    reason=repeated,
                    sequence=record.event.sequence,
                    outcome=ReduceOutcome.REPEATED_STEP_EVENT,
                )
            repeated_task = repeated_agent_task_event(task_seen, record)  # the intake refuses this live (D-172), so a log it wrote never has one
            if repeated_task is not None:
                return state, ReplayRejection(
                    code=ReplayRejectionCode.NOT_APPLICABLE,
                    reason=repeated_task,
                    sequence=record.event.sequence,
                    outcome=ReduceOutcome.REPEATED_AGENT_TASK_EVENT,
                )
        else:
            return state, ReplayRejection(
                code=ReplayRejectionCode.NOT_APPLICABLE,
                reason=result.reason or "not applied",
                sequence=record.event.sequence,
                outcome=result.outcome,
            )
        state, applied = result.state, applied | {record.event.event_id}
        key = step_event_key(record)
        if key is not None:
            seen = seen | {key}
        task_key = agent_task_event_key(record)
        if task_key is not None:
            task_seen = task_seen | {task_key}
    return state, None


def replay(records: Iterable[EventRecord]) -> ReplayResult:
    """Fold ``records`` from nothing. Refuses an empty log and the first record that does not apply."""
    materialized = tuple(records)
    if not materialized:
        return ReplayResult(rejection=ReplayRejection(code=ReplayRejectionCode.EMPTY_LOG, reason="there are no events to replay"))
    state, rejection = _fold(None, frozenset(), frozenset(), frozenset(), materialized)
    return ReplayResult(rejection=rejection) if rejection is not None else ReplayResult(state=state)


def checkpoint_at(records: Iterable[EventRecord], sequence: int) -> Checkpoint | ReplayRejection:
    """The checkpoint after the first ``sequence`` events — the caller's explicit request; nothing takes one automatically."""
    materialized = tuple(records)
    if not 1 <= sequence <= len(materialized):
        return ReplayRejection(
            code=ReplayRejectionCode.BAD_CHECKPOINT, reason=f"the log has {len(materialized)} events; no checkpoint at sequence {sequence}"
        )
    folded = replay(materialized[:sequence])
    if folded.rejection is not None:
        return folded.rejection
    return Checkpoint(state=folded.state, last_sequence=sequence)


def records_after(records: Iterable[EventRecord], checkpoint: Checkpoint) -> tuple[EventRecord, ...]:
    """The events a checkpoint has not seen: those with a greater sequence."""
    return tuple(record for record in records if record.event.sequence > checkpoint.last_sequence)


def resume(checkpoint: Checkpoint, tail: Iterable[EventRecord]) -> ReplayResult:
    """Restore ``checkpoint`` and apply ``tail`` — the events after its sequence, contiguous from the next one.

    A checkpoint is a value — the state and a sequence — so it does not carry which ``event_id``s or which steps' events came before it, and a tail
    is judged against nothing earlier: a repeat of an event from before the checkpoint is not seen here. For a log that replays, which is what a
    checkpoint is taken from, ``checkpoint + tail == full replay`` holds; to check a log end to end, replay it (D-157 item 4).
    """
    state, rejection = _fold(checkpoint.state, frozenset(), frozenset(), frozenset(), tail)
    return ReplayResult(rejection=rejection) if rejection is not None else ReplayResult(state=state)


def dump_jsonl(records: Iterable[EventRecord]) -> str:
    """One record per line, each newline-terminated; an empty log is the empty string."""
    return "".join(record.model_dump_json() + "\n" for record in records)


class LoadResult(EidosModel):
    records: tuple[EventRecord, ...] | None = None
    rejection: ReplayRejection | None = None

    @model_validator(mode="after")
    def _check_exactly_one(self) -> "LoadResult":
        if (self.records is None) == (self.rejection is None):
            raise ValueError("a load yields records or a rejection, never both and never neither")
        return self


def load_jsonl(text: str) -> LoadResult:
    """Parse the JSONL form. A blank or malformed line is a typed rejection naming its number; nothing is skipped."""
    lines = text.split("\n")  # not splitlines(): JSON may hold a raw U+2028 or U+2029 inside a string
    if lines and lines[-1] == "":
        lines.pop()  # the newline that ends the last record
    records = []
    for number, line in enumerate(lines, start=1):
        try:
            records.append(EventRecord.model_validate_json(line))
        except ValidationError as error:
            first = error.errors()[0]
            return LoadResult(
                rejection=ReplayRejection(code=ReplayRejectionCode.MALFORMED_LINE, reason=str(first["msg"]) or "invalid", line=number)
            )
    return LoadResult(records=tuple(records))


def replay_jsonl(text: str) -> ReplayResult:
    loaded = load_jsonl(text)
    if loaded.rejection is not None:
        return ReplayResult(rejection=loaded.rejection)
    return replay(loaded.records)
