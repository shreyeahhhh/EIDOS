"""The event log and its intake, replay, the checkpoint and the strict JSONL form (decisions.md D-157, D-160; V0.5 Step 4).

The log is authoritative and holds applied events only, contiguous from 1. The intake assigns the sequence — a producer never does — and orders
by that alone. Replay folds recorded events without any agent. A checkpoint plus the tail equals a full replay, at every sequence.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from eidos.contracts import PlanId, PlanStepKind, StepId
from eidos.state import (
    Checkpoint,
    EventLog,
    EventProposal,
    LoadResult,
    MissionCreatedPayload,
    MissionFailedPayload,
    MissionFailureCause,
    NodeStartedPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    ReduceOutcome,
    ReplayRejection,
    ReplayRejectionCode,
    ReplayResult,
    checkpoint_at,
    dump_jsonl,
    load_jsonl,
    records_after,
    replay,
    replay_jsonl,
    resume,
)

from eidos_mission_factories import make_mission, make_mission_plan
from eidos_state_factories import LogBuilder, at, baseline_state_and_plan, make_record, verified_baseline

ROOT = Path(__file__).resolve().parents[3]


def proposal_of(record) -> EventProposal:
    e = record.event
    return EventProposal(event_id=e.event_id, tenant_id=e.tenant_id, mission_id=e.mission_id, occurred_at=e.occurred_at, recorded_at=e.recorded_at, payload=record.payload)


def logged(records) -> EventLog:
    log = EventLog()
    for record in records:
        result = log.accept(proposal_of(record))
        assert result.applied, result.reason
    return log


RECORDS = tuple(verified_baseline().records)
N = len(RECORDS)


# --- the intake -------------------------------------------------------------------------------------------------------------------


def test_a_log_starts_empty_with_no_state_and_no_checkpoint():
    log = EventLog()
    assert len(log) == 0 and log.records == () and log.state is None and log.checkpoint() is None and log.applied_event_ids == frozenset()


def test_the_intake_assigns_the_sequence_and_the_log_holds_exactly_the_recorded_events():
    log = logged(RECORDS)
    assert log.records == RECORDS  # sequences 1..n were assigned by the intake, in the order proposed
    assert [r.event.sequence for r in log.records] == list(range(1, N + 1))
    assert len(log) == N and log.applied_event_ids == frozenset(r.event.event_id for r in RECORDS)


def test_a_proposal_has_no_sequence_the_producer_cannot_choose_one():
    assert "sequence" not in EventProposal.model_fields


def test_the_view_is_the_fold_of_the_log_and_nothing_else():
    log = logged(RECORDS)
    assert log.state == replay(log.records).state


def test_a_repeated_event_id_is_a_duplicate_it_is_not_appended_and_the_state_is_unchanged():
    log = logged(RECORDS[:5])
    before_state, before_records = log.state, log.records
    again = log.accept(proposal_of(RECORDS[3]))
    assert again.outcome is ReduceOutcome.DUPLICATE and again.record is None and again.reason
    assert log.records == before_records and log.state == before_state and again.state == before_state


def test_the_event_id_alone_decides_a_duplicate_a_different_payload_under_a_known_id_is_still_one():
    log = logged(RECORDS[:5])
    known_id = RECORDS[3].event.event_id
    other_payload_same_id = proposal_of(RECORDS[4]).model_copy(update={"event_id": known_id})
    result = log.accept(other_payload_same_id)
    assert result.outcome is ReduceOutcome.DUPLICATE and len(log) == 5


def test_a_known_event_id_is_a_duplicate_before_the_proposal_is_even_checked_for_consistency():
    # The intake decides duplicates by id first, so a repeated id with a payload that would not build is still a duplicate, not an error.
    other = make_mission(seed=2)
    log = logged(RECORDS[:3])
    known = RECORDS[1].event
    inconsistent = EventProposal(
        event_id=known.event_id, tenant_id=known.tenant_id, mission_id=known.mission_id, occurred_at=at(2), recorded_at=at(2),
        payload=PlanGeneratedPayload(plan=make_mission_plan(other, {"a": ""})),
    )
    result = log.accept(inconsistent)
    assert result.outcome is ReduceOutcome.DUPLICATE and "already applied" in result.reason and len(log) == 3


def test_a_rejected_proposal_is_not_appended_and_consumes_no_sequence():
    log = logged(RECORDS[:3])
    unknown_plan = proposal_of(make_record(PlanCompiledPayload(plan_id=PlanId(UUID(int=7)), plan_version=1), state=verified_baseline().state, sequence=4, number=901))
    refused = log.accept(unknown_plan)
    assert refused.outcome is ReduceOutcome.INVALID_FOR_STATE and refused.record is None
    assert len(log) == 3
    after = log.accept(proposal_of(RECORDS[3]))
    assert after.applied and after.record.event.sequence == 4  # contiguous: the refused proposal took nothing


def test_after_a_terminal_event_the_intake_refuses_everything_with_post_terminal():
    log = logged(RECORDS)  # ends with MISSION_COMPLETED
    late = proposal_of(make_record(NodeStartedPayload(plan_id=RECORDS[1].payload.plan.plan_id, step_id=StepId("check"), kind=PlanStepKind.VERIFY), state=verified_baseline().state, sequence=11, number=902))
    result = log.accept(late)
    assert result.outcome is ReduceOutcome.POST_TERMINAL and len(log) == N


def test_the_first_event_must_be_mission_created():
    log = EventLog()
    result = log.accept(proposal_of(RECORDS[1]))
    assert result.outcome is ReduceOutcome.INVALID_FOR_STATE and len(log) == 0 and log.state is None


def test_a_proposal_whose_payload_disagrees_with_its_identity_is_refused_not_raised():
    other = make_mission(seed=2)
    foreign_plan = make_mission_plan(other, {"a": ""})
    log = logged(RECORDS[:1])
    bad = EventProposal(
        event_id=RECORDS[1].event.event_id, tenant_id=RECORDS[0].event.tenant_id, mission_id=RECORDS[0].event.mission_id,
        occurred_at=at(2), recorded_at=at(2), payload=PlanGeneratedPayload(plan=foreign_plan),
    )
    result = log.accept(bad)
    assert result.outcome is ReduceOutcome.INVALID_FOR_STATE and "inconsistent" in result.reason and len(log) == 1


def test_a_proposal_for_another_mission_is_refused():
    other = make_mission(seed=2)
    log = logged(RECORDS[:1])
    foreign = proposal_of(make_record(MissionCreatedPayload(task_genome=other.task_genome, reliability_contract=other.reliability_contract, execution_id=other.execution_id),
                                      state=other, sequence=1, number=903))
    assert log.accept(foreign).outcome is ReduceOutcome.INVALID_FOR_STATE


def test_order_is_the_call_order_never_the_timestamps():
    # D-160 item 7: two "parallel" nodes may report in either order, and a later event may carry an earlier time. The log records what it accepted.
    base = verified_baseline()
    proposals = [proposal_of(r) for r in base.records[:4]]
    backwards = [p.model_copy(update={"occurred_at": at(100 - i), "recorded_at": at(100 - i)}) for i, p in enumerate(proposals)]
    log = EventLog()
    for p in backwards:
        assert log.accept(p).applied
    assert [r.event.sequence for r in log.records] == [1, 2, 3, 4]
    assert log.records[0].event.recorded_at > log.records[-1].event.recorded_at  # timestamps run backwards; the sequence does not


def test_the_records_property_is_a_snapshot_it_cannot_be_used_to_edit_the_log():
    log = logged(RECORDS[:3])
    snapshot = log.records
    assert isinstance(snapshot, tuple)
    logged_more = log.accept(proposal_of(RECORDS[3]))
    assert logged_more.applied and len(snapshot) == 3 and len(log) == 4


# --- replay -----------------------------------------------------------------------------------------------------------------------


def test_replay_folds_the_recorded_events_to_the_state_the_intake_built():
    result = replay(RECORDS)
    assert result.replayed and result.rejection is None
    assert result.state == logged(RECORDS).state


def test_an_empty_log_is_a_typed_rejection():
    result = replay(())
    assert not result.replayed and result.rejection.code is ReplayRejectionCode.EMPTY_LOG and result.state is None


@pytest.mark.parametrize("label, records, sequence, outcome", [
    ("does not begin with MISSION_CREATED", RECORDS[1:], 2, ReduceOutcome.INVALID_FOR_STATE),
    ("has a gap", RECORDS[:4] + RECORDS[5:], 6, ReduceOutcome.OUT_OF_ORDER),
    ("repeats an event", RECORDS[:5] + (RECORDS[2],), 3, ReduceOutcome.DUPLICATE),
    ("continues after a terminal event", RECORDS + (make_record(
        PlanCompiledPayload(plan_id=RECORDS[2].payload.plan_id, plan_version=1), state=verified_baseline().state, sequence=N + 1, number=904),), N + 1, ReduceOutcome.POST_TERMINAL),
], ids=["no MISSION_CREATED first", "a gap", "a repeated event", "an event after a terminal one"])
def test_a_log_that_does_not_replay_is_a_typed_rejection_naming_the_record_and_never_a_partial_state(label, records, sequence, outcome):
    result = replay(records)
    assert result.state is None, label
    rejection = result.rejection
    assert rejection.code is ReplayRejectionCode.NOT_APPLICABLE and rejection.sequence == sequence and rejection.outcome is outcome and rejection.reason


def test_a_log_that_mixes_two_missions_does_not_replay():
    other = make_mission(seed=2)
    foreign = make_record(MissionCreatedPayload(task_genome=other.task_genome, reliability_contract=other.reliability_contract, execution_id=other.execution_id),
                          state=other, sequence=2, number=905)
    result = replay(RECORDS[:1] + (foreign,))
    assert result.rejection.outcome is ReduceOutcome.INVALID_FOR_STATE and result.rejection.sequence == 2


def test_replay_needs_no_agent_model_or_store_it_consumes_the_events_alone():
    # The whole input is the recorded events: nothing but EventRecord values goes in, and only the reducer is called on them.
    import inspect

    assert list(inspect.signature(replay).parameters) == ["records"]
    assert replay(iter(RECORDS)).replayed  # even a one-shot stream of events is enough


def test_restoring_a_log_lets_appending_continue_and_an_invalid_one_is_refused():
    restored = EventLog.restore(RECORDS[:5])
    assert isinstance(restored, EventLog) and restored.state == replay(RECORDS[:5]).state
    for record in RECORDS[5:]:
        assert restored.accept(proposal_of(record)).applied
    assert restored.records == RECORDS
    assert isinstance(EventLog.restore(RECORDS[1:]), ReplayRejection)
    assert isinstance(EventLog.restore(()), ReplayRejection)


def test_a_restored_log_still_knows_which_events_it_has_applied():
    restored = EventLog.restore(RECORDS[:5])
    assert restored.applied_event_ids == frozenset(r.event.event_id for r in RECORDS[:5])
    result = restored.accept(proposal_of(RECORDS[2]))
    assert result.outcome is ReduceOutcome.DUPLICATE and len(restored) == 5


def test_a_result_is_exactly_one_thing_and_a_rejection_carries_the_locators_its_code_requires():
    state = replay(RECORDS[:4]).state
    rejection = ReplayRejection(code=ReplayRejectionCode.EMPTY_LOG, reason="none")
    for bad in (dict(), dict(state=state, rejection=rejection)):
        with pytest.raises(ValidationError, match="never both and never neither"):
            ReplayResult(**bad)
    with pytest.raises(ValidationError, match="never both and never neither"):
        LoadResult()
    with pytest.raises(ValidationError, match="never both and never neither"):
        LoadResult(records=(), rejection=rejection)
    with pytest.raises(ValidationError, match="reducer's outcome"):
        ReplayRejection(code=ReplayRejectionCode.NOT_APPLICABLE, reason="x", sequence=2)
    with pytest.raises(ValidationError, match="reducer's outcome"):
        ReplayRejection(code=ReplayRejectionCode.EMPTY_LOG, reason="x", outcome=ReduceOutcome.STALE)
    with pytest.raises(ValidationError, match="names its line"):
        ReplayRejection(code=ReplayRejectionCode.MALFORMED_LINE, reason="x")
    with pytest.raises(ValidationError, match="names its line"):
        ReplayRejection(code=ReplayRejectionCode.EMPTY_LOG, reason="x", line=3)


# --- the checkpoint: a value, taken on request, and a checkpoint plus the tail equals a full replay -------------------------------


@pytest.mark.parametrize("k", range(1, N + 1))
def test_a_checkpoint_at_any_sequence_plus_the_tail_equals_a_full_replay(k):
    full = replay(RECORDS).state
    checkpoint = checkpoint_at(RECORDS, k)
    assert isinstance(checkpoint, Checkpoint) and checkpoint.last_sequence == k
    assert checkpoint.state == replay(RECORDS[:k]).state
    resumed = resume(checkpoint, records_after(RECORDS, checkpoint))
    assert resumed.replayed
    assert resumed.state == full and resumed.state.model_dump_json() == full.model_dump_json()


def test_a_checkpoint_the_log_cannot_have_is_a_typed_rejection():
    for bad in (0, -1, N + 1):
        result = checkpoint_at(RECORDS, bad)
        assert isinstance(result, ReplayRejection) and result.code is ReplayRejectionCode.BAD_CHECKPOINT
    broken = checkpoint_at(RECORDS[:4] + RECORDS[5:], 6)
    assert isinstance(broken, ReplayRejection) and broken.code is ReplayRejectionCode.NOT_APPLICABLE


def test_a_checkpoint_states_its_own_sequence_and_cannot_disagree_with_its_state():
    state = replay(RECORDS[:4]).state
    Checkpoint(state=state, last_sequence=4)
    with pytest.raises(ValidationError, match="state_version"):
        Checkpoint(state=state, last_sequence=5)


def test_resuming_with_a_gap_or_an_old_event_in_the_tail_is_a_typed_rejection():
    checkpoint = checkpoint_at(RECORDS, 4)
    gap = resume(checkpoint, RECORDS[5:])
    assert gap.rejection.outcome is ReduceOutcome.OUT_OF_ORDER and gap.rejection.sequence == 6
    old = resume(checkpoint, RECORDS[1:3])
    assert old.rejection.outcome is ReduceOutcome.STALE
    assert resume(checkpoint, ()).state == checkpoint.state  # nothing after it: the checkpoint is the state


def test_the_log_takes_a_checkpoint_only_when_asked_and_it_is_the_latest_state():
    log = logged(RECORDS[:6])
    checkpoint = log.checkpoint()
    assert checkpoint.state == log.state and checkpoint.last_sequence == 6
    assert log.accept(proposal_of(RECORDS[6])).applied
    assert checkpoint.last_sequence == 6  # a value: it does not move when the log does


# --- the strict JSONL form --------------------------------------------------------------------------------------------------------


def test_the_log_serializes_one_record_per_line_and_parses_back_to_an_equal_log():
    text = logged(RECORDS).to_jsonl()
    assert text == dump_jsonl(RECORDS)
    assert text.endswith("\n") and len(text.splitlines()) == N and "\n\n" not in text
    loaded = load_jsonl(text)
    assert loaded.rejection is None and loaded.records == RECORDS
    assert dump_jsonl(loaded.records) == text  # identical text, not just an equal value


def test_replaying_the_serialized_log_gives_the_same_state_as_replaying_the_records():
    text = dump_jsonl(RECORDS)
    assert replay_jsonl(text).state == replay(RECORDS).state == logged(RECORDS).state


def test_an_empty_log_is_the_empty_string_and_replays_as_an_empty_log_rejection():
    assert dump_jsonl(()) == ""
    assert load_jsonl("").records == ()
    assert replay_jsonl("").rejection.code is ReplayRejectionCode.EMPTY_LOG


def test_a_final_record_without_its_newline_still_parses_but_a_blank_or_broken_line_is_named():
    text = dump_jsonl(RECORDS)
    assert load_jsonl(text.rstrip("\n")).records == RECORDS
    lines = text.split("\n")
    with_blank = "\n".join(lines[:3] + [""] + lines[3:])
    blank = load_jsonl(with_blank)
    assert blank.records is None and blank.rejection.code is ReplayRejectionCode.MALFORMED_LINE and blank.rejection.line == 4
    broken = load_jsonl("\n".join(lines[:2] + ['{"event": '] + lines[3:]))
    assert broken.rejection.line == 3
    truncated = load_jsonl(text[: len(text) // 2])
    assert truncated.rejection is not None and truncated.rejection.code is ReplayRejectionCode.MALFORMED_LINE
    assert replay_jsonl(with_blank).rejection.code is ReplayRejectionCode.MALFORMED_LINE


def test_a_record_that_parses_but_does_not_belong_is_refused_by_replay_not_by_the_loader():
    text = dump_jsonl(RECORDS[:1] + RECORDS[2:3])
    assert load_jsonl(text).records is not None
    assert replay_jsonl(text).rejection.outcome is ReduceOutcome.OUT_OF_ORDER


def test_text_a_json_string_may_legally_hold_survives_the_round_trip_line_separators_included():
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created()
    log.generated()
    log.compiled()
    log.add(MissionFailedPayload(plan_id=plan.plan_id, cause=MissionFailureCause.NO_RESULT, reason="line one line two end\x0bmore\x85tail"))
    text = dump_jsonl(log.records)
    assert len(text.split("\n")) == 5  # four records and the empty string after the last newline: the separators did not split a record
    assert load_jsonl(text).records == tuple(log.records)


# --- determinism ------------------------------------------------------------------------------------------------------------------


def test_the_serialized_log_and_its_state_are_identical_across_hash_seeds():
    script = (
        "import sys, hashlib; sys.path[:0] = ['src', 'tests/support', 'tests/unit/state']\n"
        "from eidos_state_factories import verified_baseline\n"
        "from eidos.state import EventLog, EventProposal, replay_jsonl\n"
        "log = EventLog()\n"
        "for r in verified_baseline().records:\n"
        "    e = r.event\n"
        "    assert log.accept(EventProposal(event_id=e.event_id, tenant_id=e.tenant_id, mission_id=e.mission_id, occurred_at=e.occurred_at, recorded_at=e.recorded_at, payload=r.payload)).applied\n"
        "text = log.to_jsonl()\n"
        "assert replay_jsonl(text).state == log.state\n"
        "print(hashlib.sha256(text.encode()).hexdigest(), hashlib.sha256(log.state.model_dump_json().encode()).hexdigest())\n"
    )
    seen = set()
    for seed in ("0", "1", "2", "12345"):
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": seed})
        assert result.returncode == 0, result.stderr
        seen.add(result.stdout.strip())
    assert len(seen) == 1 and len(next(iter(seen)).split()) == 2
