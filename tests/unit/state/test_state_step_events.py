"""A step's start and settlement are each recorded once (decisions.md D-162 item 1; invariant 8; V0.5 close-out).

The intake refuses a repeated ``NODE_STARTED`` or ``NODE_SETTLED`` for the same step of a plan, and a fold from scratch (replay, restore, JSONL, the
projection) refuses a log that has one, so the live log and a replay of it agree. ``MissionState`` gains no per-node state: the memory is the log's own.
"""

import pytest

from eidos.contracts import CapabilityId, MissionEventType, PlanStepKind, StepId
from eidos.runtime import NodeStatus
from eidos.state import (
    EventLog,
    EventProposal,
    NodeSettledPayload,
    NodeStartedPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    ReduceOutcome,
    ReplayRejection,
    ReplayRejectionCode,
    checkpoint_at,
    dump_jsonl,
    execution_record,
    records_after,
    replay,
    replay_jsonl,
    resume,
)
from eidos.state.step_events import repeated_step_event, step_event_key, step_event_keys

from eidos_mission_factories import make_mission_plan
from eidos_state_factories import ANALYSIS_AGENT, at, event_id, verified_baseline, verify_result, work_result

GATHER_STARTED, GATHER_SETTLED = 3, 4  # indices in the verified baseline's records


def proposal(builder, payload, number: int) -> EventProposal:
    return EventProposal(
        event_id=event_id(number), tenant_id=builder.state.tenant_id, mission_id=builder.state.mission_id,
        occurred_at=at(500 + number), recorded_at=at(500 + number), payload=payload,
    )


def open_log(builder, upto: int = 5) -> EventLog:
    """A live log holding the first ``upto`` records of the verified baseline (default: gather started and settled), accepted through the intake."""
    log = EventLog()
    for record in builder.records[:upto]:
        e = record.event
        result = log.accept(EventProposal(event_id=e.event_id, tenant_id=e.tenant_id, mission_id=e.mission_id, occurred_at=e.occurred_at, recorded_at=e.recorded_at, payload=record.payload))
        assert result.applied, result.reason
    return log


# --- the intake ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("index, changed", [
    (GATHER_SETTLED, {}), (GATHER_SETTLED, {"duration_ms": 9999}),
    (GATHER_STARTED, {}), (GATHER_STARTED, {"agent_id": ANALYSIS_AGENT}),
], ids=["settled-identical", "settled-different", "started-identical", "started-different"])
def test_the_intake_refuses_a_repeated_start_or_settlement_and_leaves_everything_as_it_was(index, changed):
    builder = verified_baseline()
    log = open_log(builder)
    before = (log.records, log.state, log.applied_event_ids, log.to_jsonl())
    again = builder.records[index].payload.model_copy(update=changed)
    result = log.accept(proposal(builder, again, 900))  # a new event_id: this is not a duplicate of the event, it is the same step's event again
    assert result.outcome is ReduceOutcome.REPEATED_STEP_EVENT and not result.applied and result.record is None
    assert "already has a" in result.reason and again.event_type.value in result.reason
    assert (log.records, log.state, log.applied_event_ids, log.to_jsonl()) == before  # nothing appended, folded or remembered
    assert result.state == before[1] and result.state.model_dump_json() == before[1].model_dump_json()
    assert log.state.agent_calls_used == 1  # the counters were not folded a second time


def test_a_refused_repeat_consumes_no_sequence_and_the_next_event_takes_it():
    builder = verified_baseline()
    log = open_log(builder)
    assert log.accept(proposal(builder, builder.records[GATHER_SETTLED].payload, 900)).outcome is ReduceOutcome.REPEATED_STEP_EVENT
    next_event = log.accept(proposal(builder, builder.records[5].payload, 901))  # analyse started
    assert next_event.applied and next_event.record.event.sequence == 6 and len(log) == 6


def test_a_start_and_a_settlement_of_one_step_are_different_events_and_a_settlement_alone_is_fine():
    builder = verified_baseline()
    log = open_log(builder, upto=4)  # gather started, not yet settled
    assert log.accept(proposal(builder, builder.records[GATHER_SETTLED].payload, 900)).applied  # its settlement: a different type, so not a repeat
    # a node that never started (skipped, not reached, or one whose port raised) is settled with no start
    skipped = NodeSettledPayload(plan_id=builder.plan.plan_id, result=verify_result("check", status=NodeStatus.SKIPPED), dispatched=False)
    assert log.accept(proposal(builder, skipped, 901)).applied


def test_the_same_step_id_in_another_plan_version_is_another_step_so_a_replan_may_run_it_again():
    builder = verified_baseline()
    log = open_log(builder)
    second = make_mission_plan(
        builder.state, {"gather": "", "check": "gather"}, verify=("check",), capability_of={"gather": "research"},
        version=2, parent=builder.plan, reason="the first plan's analysis was unsupported", plan_number=2,
    )
    assert log.accept(proposal(builder, PlanGeneratedPayload(plan=second), 900)).applied
    assert log.accept(proposal(builder, PlanCompiledPayload(plan_id=second.plan_id, plan_version=2), 901)).applied
    started = NodeStartedPayload(plan_id=second.plan_id, step_id=StepId("gather"), kind=PlanStepKind.AGENT, capability=CapabilityId("research"), agent_id=ANALYSIS_AGENT)
    settled = NodeSettledPayload(plan_id=second.plan_id, result=work_result("gather"), dispatched=True, duration_ms=5, model_calls=())
    assert log.accept(proposal(builder, started, 902)).applied and log.accept(proposal(builder, settled, 903)).applied
    assert log.accept(proposal(builder, started, 904)).outcome is ReduceOutcome.REPEATED_STEP_EVENT  # but not twice within that plan


def test_the_reducers_own_outcomes_take_precedence_over_the_repeat_check():
    builder = verified_baseline()
    log = open_log(builder, upto=len(builder.records))  # the mission is completed
    late = log.accept(proposal(builder, builder.records[GATHER_SETTLED].payload, 900))
    assert late.outcome is ReduceOutcome.POST_TERMINAL  # after a terminal event, whatever else it is

    open_ = open_log(builder)
    same_id = open_.accept(EventProposal(
        event_id=builder.records[GATHER_SETTLED].event.event_id, tenant_id=builder.state.tenant_id, mission_id=builder.state.mission_id,
        occurred_at=at(700), recorded_at=at(700), payload=builder.records[GATHER_SETTLED].payload,
    ))
    assert same_id.outcome is ReduceOutcome.DUPLICATE  # the same event_id is a duplicate of the event, not a repeat of the step


def test_a_log_restored_from_records_remembers_which_steps_have_started_and_settled():
    builder = verified_baseline()
    restored = EventLog.restore(builder.records[:5])
    assert isinstance(restored, EventLog)
    assert restored.accept(proposal(builder, builder.records[GATHER_SETTLED].payload, 900)).outcome is ReduceOutcome.REPEATED_STEP_EVENT
    assert restored.accept(proposal(builder, builder.records[GATHER_STARTED].payload, 901)).outcome is ReduceOutcome.REPEATED_STEP_EVENT
    assert restored.accept(proposal(builder, builder.records[5].payload, 902)).applied  # analyse started: a step not yet seen


# --- a fold from scratch -------------------------------------------------------------------------------------------------------------


def with_a_repeat(index: int, **changed):
    builder = verified_baseline()
    again = builder.records[index].payload.model_copy(update=changed)
    builder.records.pop()  # drop the terminal event so the mission is still open
    builder.add(again)
    return builder


@pytest.mark.parametrize("index, changed", [(GATHER_SETTLED, {"duration_ms": 9999}), (GATHER_STARTED, {"agent_id": ANALYSIS_AGENT})], ids=["settled", "started"])
def test_replay_restore_jsonl_and_the_projection_all_refuse_a_log_with_a_repeat_in_the_same_way(index, changed):
    builder = with_a_repeat(index, **changed)
    repeat_sequence = len(builder.records)
    for rejection in (
        replay(builder.records).rejection,
        EventLog.restore(builder.records),
        replay_jsonl(dump_jsonl(builder.records)).rejection,
        execution_record(builder.records),
    ):
        assert isinstance(rejection, ReplayRejection)
        assert (rejection.code, rejection.outcome, rejection.sequence) == (ReplayRejectionCode.NOT_APPLICABLE, ReduceOutcome.REPEATED_STEP_EVENT, repeat_sequence)
        assert "already has a" in rejection.reason


def test_the_live_intake_and_a_replay_refuse_the_same_record_of_the_same_log():
    builder = with_a_repeat(GATHER_SETTLED, duration_ms=9999)
    replayed = replay(builder.records).rejection
    log = EventLog()
    refused_at = []
    for record in builder.records:
        e = record.event
        result = log.accept(EventProposal(event_id=e.event_id, tenant_id=e.tenant_id, mission_id=e.mission_id, occurred_at=e.occurred_at, recorded_at=e.recorded_at, payload=record.payload))
        if not result.applied:
            refused_at.append((e.sequence, result.outcome))
    assert refused_at == [(replayed.sequence, replayed.outcome)]  # exactly the record the replay names, with the same outcome


def test_a_log_the_intake_wrote_replays_and_a_checkpoint_plus_the_tail_still_equals_the_full_replay_at_every_sequence():
    builder = verified_baseline()
    log = open_log(builder, upto=len(builder.records))
    full = replay(log.records).state
    assert full == log.state
    for sequence in range(1, len(log) + 1):
        checkpoint = checkpoint_at(log.records, sequence)
        assert resume(checkpoint, records_after(log.records, checkpoint)).state == full


# --- the key and the check, on their own ---------------------------------------------------------------------------------------------


def test_only_a_start_and_a_settlement_have_a_step_event_key_and_a_start_and_a_settlement_of_one_step_have_different_keys():
    builder = verified_baseline()
    keys = [step_event_key(r) for r in builder.records]
    assert [k is not None for k in keys] == [False, False, False, True, True, True, True, True, True, False]  # created, generated, compiled, six node events, completed
    started, settled = keys[GATHER_STARTED], keys[GATHER_SETTLED]
    assert started[0] is MissionEventType.NODE_STARTED and settled[0] is MissionEventType.NODE_SETTLED
    assert started[1:] == settled[1:] == (builder.plan.plan_id, StepId("gather"))  # a settlement's step is the one its result names
    assert len(step_event_keys(builder.records)) == 6


def test_the_check_names_the_step_the_plan_and_the_event_type_and_passes_everything_else():
    builder = verified_baseline()
    seen = step_event_keys(builder.records[:5])
    assert repeated_step_event(seen, builder.records[GATHER_SETTLED]) is not None
    reason = repeated_step_event(seen, builder.records[GATHER_STARTED])
    assert "'gather'" in reason and str(builder.plan.plan_id) in reason and "NODE_STARTED" in reason
    assert repeated_step_event(seen, builder.records[5]) is None  # analyse has not started
    assert repeated_step_event(seen, builder.records[-1]) is None  # a terminal event is not a step event
    assert repeated_step_event(frozenset(), builder.records[GATHER_STARTED]) is None
