"""An A2A task's start and completion are each recorded once (decisions.md D-172; invariant 8; V0.6 Step 4).

The intake refuses a repeated ``A2A_TASK_STARTED`` or ``A2A_TASK_COMPLETED`` for the same ``a2a_task_id``, and a fold from scratch (replay,
restore, JSONL, the projection) refuses a log that has one, so the live log and a replay of it agree — exactly the D-162 item 1 pattern
``step_events.py`` already established, one layer over. ``MissionState`` gains no per-task event history: the memory is the log's own.
"""

import pytest

from eidos.contracts import MissionEventType, StepId
from eidos.runtime import VerificationVerdict
from eidos.state import (
    A2ATaskStartedPayload,
    EventLog,
    EventProposal,
    ReduceOutcome,
    ReplayRejection,
    ReplayRejectionCode,
    VerificationFacts,
    checkpoint_at,
    dump_jsonl,
    execution_record,
    records_after,
    replay,
    replay_jsonl,
    resume,
)
from eidos.state.agent_task_events import agent_task_event_key, agent_task_event_keys, repeated_agent_task_event

from eidos_state_factories import ANALYSIS_AGENT, LogBuilder, a2a_task_id, at, baseline_state_and_plan, event_id, response_call, verify_result, work_result

A2A_STARTED, A2A_COMPLETED = 3, 4  # indices in a2a_baseline()'s records


def a2a_baseline(task: int = 1) -> LogBuilder:
    """Like ``verified_baseline`` (eidos_state_factories), but 'gather' is dispatched to a remote A2A task rather than settled locally."""
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created()
    log.generated()
    log.compiled()
    log.a2a_started("gather", task=task)
    log.a2a_completed("gather", task=task)
    log.started("analyse")
    log.settled(work_result("analyse"), duration_ms=3400, model_calls=(response_call(322, 2582, 154.2),))
    log.started("check")
    log.settled(
        verify_result("check"), duration_ms=5,
        verification=VerificationFacts(verdict=VerificationVerdict.PASS, reason="the supported rules were satisfied"),
    )
    log.completed(verified=True)
    return log


def proposal(builder, payload, number: int) -> EventProposal:
    return EventProposal(
        event_id=event_id(number), tenant_id=builder.state.tenant_id, mission_id=builder.state.mission_id,
        occurred_at=at(500 + number), recorded_at=at(500 + number), payload=payload,
    )


def open_log(builder, upto: int = 5) -> EventLog:
    """A live log holding the first ``upto`` records of an a2a_baseline (default: the A2A task started and completed), through the intake."""
    log = EventLog()
    for record in builder.records[:upto]:
        e = record.event
        result = log.accept(EventProposal(event_id=e.event_id, tenant_id=e.tenant_id, mission_id=e.mission_id, occurred_at=e.occurred_at, recorded_at=e.recorded_at, payload=record.payload))
        assert result.applied, result.reason
    return log


# --- the intake ------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("index, changed", [
    (A2A_COMPLETED, {}), (A2A_COMPLETED, {"reason": "a different reason"}),
    (A2A_STARTED, {}), (A2A_STARTED, {"a2a_context_id": "remote-context-9"}),
], ids=["completed-identical", "completed-different", "started-identical", "started-different"])
def test_the_intake_refuses_a_repeated_start_or_completion_and_leaves_everything_as_it_was(index, changed):
    builder = a2a_baseline()
    log = open_log(builder)
    before = (log.records, log.state, log.applied_event_ids, log.to_jsonl())
    again = builder.records[index].payload.model_copy(update=changed)
    result = log.accept(proposal(builder, again, 900))  # a new event_id: not a duplicate of the event, the same task's event again
    assert result.outcome is ReduceOutcome.REPEATED_AGENT_TASK_EVENT and not result.applied and result.record is None
    assert "already has a" in result.reason and again.event_type.value in result.reason
    assert (log.records, log.state, log.applied_event_ids, log.to_jsonl()) == before  # nothing appended, folded or remembered
    assert result.state == before[1] and result.state.model_dump_json() == before[1].model_dump_json()


def test_a_refused_repeat_consumes_no_sequence_and_the_next_event_takes_it():
    builder = a2a_baseline()
    log = open_log(builder)
    assert log.accept(proposal(builder, builder.records[A2A_COMPLETED].payload, 900)).outcome is ReduceOutcome.REPEATED_AGENT_TASK_EVENT
    next_event = log.accept(proposal(builder, builder.records[5].payload, 901))  # analyse started
    assert next_event.applied and next_event.record.event.sequence == 6 and len(log) == 6


def test_a_start_and_a_completion_of_one_task_are_different_events_and_a_completion_alone_is_fine():
    builder = a2a_baseline()
    log = open_log(builder, upto=4)  # the task started, not yet completed
    assert log.accept(proposal(builder, builder.records[A2A_COMPLETED].payload, 900)).applied  # its completion: a different type, so not a repeat


def test_two_independent_a2a_tasks_do_not_collide():
    builder = a2a_baseline(task=1)
    log = open_log(builder, upto=4)  # task 1 started, not yet completed
    # A second, independent remote task for a different step: its own a2a_task_id, so it does not repeat task 1's A2A_TASK_STARTED.
    second = A2ATaskStartedPayload(plan_id=builder.plan.plan_id, step_id=StepId("analyse"), agent_id=ANALYSIS_AGENT, a2a_task_id=a2a_task_id(2))
    result = log.accept(proposal(builder, second, 900))
    assert result.applied
    # each task's own repeat is still caught independently
    assert log.accept(proposal(builder, second, 901)).outcome is ReduceOutcome.REPEATED_AGENT_TASK_EVENT
    assert log.accept(proposal(builder, builder.records[A2A_STARTED].payload, 902)).outcome is ReduceOutcome.REPEATED_AGENT_TASK_EVENT


def test_the_reducers_own_outcomes_take_precedence_over_the_repeat_check():
    builder = a2a_baseline()
    log = open_log(builder, upto=len(builder.records))  # the mission is completed
    late = log.accept(proposal(builder, builder.records[A2A_COMPLETED].payload, 900))
    assert late.outcome is ReduceOutcome.POST_TERMINAL  # after a terminal event, whatever else it is

    open_ = open_log(builder)
    same_id = open_.accept(EventProposal(
        event_id=builder.records[A2A_COMPLETED].event.event_id, tenant_id=builder.state.tenant_id, mission_id=builder.state.mission_id,
        occurred_at=at(700), recorded_at=at(700), payload=builder.records[A2A_COMPLETED].payload,
    ))
    assert same_id.outcome is ReduceOutcome.DUPLICATE  # the same event_id is a duplicate of the event, not a repeat of the task


def test_a_log_restored_from_records_remembers_which_tasks_have_started_and_completed():
    builder = a2a_baseline()
    restored = EventLog.restore(builder.records[:5])
    assert isinstance(restored, EventLog)
    assert restored.accept(proposal(builder, builder.records[A2A_COMPLETED].payload, 900)).outcome is ReduceOutcome.REPEATED_AGENT_TASK_EVENT
    assert restored.accept(proposal(builder, builder.records[A2A_STARTED].payload, 901)).outcome is ReduceOutcome.REPEATED_AGENT_TASK_EVENT
    assert restored.accept(proposal(builder, builder.records[5].payload, 902)).applied  # analyse started: a step, not a repeated A2A task


# --- a fold from scratch -----------------------------------------------------------------------------------------------------------------


def with_a_repeat(index: int, **changed):
    builder = a2a_baseline()
    again = builder.records[index].payload.model_copy(update=changed)
    builder.records.pop()  # drop the terminal event so the mission is still open
    builder.add(again)
    return builder


@pytest.mark.parametrize("index, changed", [(A2A_COMPLETED, {"reason": "a different reason"}), (A2A_STARTED, {"a2a_context_id": "remote-context-9"})], ids=["completed", "started"])
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
        assert (rejection.code, rejection.outcome, rejection.sequence) == (ReplayRejectionCode.NOT_APPLICABLE, ReduceOutcome.REPEATED_AGENT_TASK_EVENT, repeat_sequence)
        assert "already has a" in rejection.reason


def test_the_live_intake_and_a_replay_refuse_the_same_record_of_the_same_log():
    builder = with_a_repeat(A2A_COMPLETED, reason="a different reason")
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
    builder = a2a_baseline()
    log = open_log(builder, upto=len(builder.records))
    full = replay(log.records).state
    assert full == log.state
    for sequence in range(1, len(log) + 1):
        checkpoint = checkpoint_at(log.records, sequence)
        assert resume(checkpoint, records_after(log.records, checkpoint)).state == full


# --- the key and the check, on their own ------------------------------------------------------------------------------------------------


def test_only_a_start_and_a_completion_have_an_agent_task_event_key_and_they_differ_by_type():
    builder = a2a_baseline()
    keys = [agent_task_event_key(r) for r in builder.records]
    assert [k is not None for k in keys] == [False, False, False, True, True, False, False, False, False, False]  # created, generated, compiled, a2a started/completed, then local steps and completion
    started, completed = keys[A2A_STARTED], keys[A2A_COMPLETED]
    assert started[0] is MissionEventType.A2A_TASK_STARTED and completed[0] is MissionEventType.A2A_TASK_COMPLETED
    assert started[1] == completed[1] == a2a_task_id(1)  # the same remote task
    assert len(agent_task_event_keys(builder.records)) == 2


def test_the_check_names_the_task_and_the_event_type_and_passes_everything_else():
    builder = a2a_baseline()
    seen = agent_task_event_keys(builder.records[:4])  # through the A2A_TASK_STARTED, not yet the completion
    assert repeated_agent_task_event(seen, builder.records[A2A_STARTED]) is not None
    reason = repeated_agent_task_event(seen, builder.records[A2A_STARTED])
    assert repr(a2a_task_id(1)) in reason and "A2A_TASK_STARTED" in reason
    assert repeated_agent_task_event(seen, builder.records[A2A_COMPLETED]) is None  # not yet completed
    assert repeated_agent_task_event(seen, builder.records[5]) is None  # a local NODE_STARTED is not an agent task event
    assert repeated_agent_task_event(frozenset(), builder.records[A2A_STARTED]) is None
