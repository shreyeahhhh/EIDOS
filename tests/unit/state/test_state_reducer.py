"""The state reducer (decisions.md D-155, D-156, D-160; V0.5 Step 3).

Written from the rules, not from the code: what each outcome means, the fixed order the checks run in, every counter rule (a carried-over node
is not a call; an unreported token count adds nothing; a missing duration adds nothing), that ordering is the sequence and never a timestamp,
and that a non-applied outcome leaves the state byte-identical.
"""

import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from eidos.contracts import AgentTaskStatus, MissionState, MissionStatus, PlanId, PlanStepKind, StepId
from eidos.runtime import AwaitingInfo, HaltInfo, NodeResult, NodeStatus
from eidos.state import (
    A2ATaskCompletedPayload,
    A2ATaskStartedPayload,
    EventLog,
    EventProposal,
    MissionCompletedPayload,
    MissionFailedPayload,
    MissionFailureCause,
    MissionPausedPayload,
    ModelCallFacts,
    ModelCallOutcome,
    NodeSettledPayload,
    NodeStartedPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    PlanRejectedPayload,
    PlanRejectionStage,
    ReduceOutcome,
    ReduceResult,
    ReplanTriggeredPayload,
    checkpoint_at,
    records_after,
    reduce,
    replay,
    resume,
)

from eidos_expansion_factories import make_plan_id
from eidos_mission_factories import make_mission, make_mission_plan
from eidos_state_factories import (
    RESEARCH_AGENT,
    LogBuilder,
    a2a_task_id,
    at,
    baseline_state_and_plan,
    created,
    make_record,
    response_call,
    verified_baseline,
    verify_result,
    work_result,
)

ROOT = Path(__file__).resolve().parents[3]


def fold(records):
    """Apply records in order, keeping the applied ids as the log will; returns the final state and every result."""
    state, applied, results = None, frozenset(), []
    for record in records:
        result = reduce(state, record, applied)
        results.append(result)
        if result.applied:
            state, applied = result.state, applied | {record.event.event_id}
    return state, results


def state_after(builder: LogBuilder) -> MissionState:
    state, results = fold(builder.records)
    assert all(r.applied for r in results), [r.reason for r in results if not r.applied]
    return state


def prefix() -> LogBuilder:
    """A mission that is created, has a plan and has compiled it: ready for node events."""
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created()
    log.generated()
    log.compiled()
    return log


def same_bytes(a, b) -> bool:
    return a is b or (a is not None and b is not None and a.model_dump_json() == b.model_dump_json())


# --- creation ---------------------------------------------------------------------------------------------------------------------


def test_the_first_event_creates_the_mission_from_its_payload_and_its_envelope():
    state, _ = baseline_state_and_plan()
    record = make_record(created(state), state=state, sequence=1, seconds=7)
    result = reduce(None, record)

    assert result.applied and result.reason is None
    made = result.state
    assert (made.tenant_id, made.mission_id, made.execution_id) == (state.tenant_id, state.mission_id, state.execution_id)
    assert made.task_genome == state.task_genome and made.reliability_contract == state.reliability_contract
    assert made.status is MissionStatus.CREATED and made.status_reason is None
    assert made.plans == () and made.active_plan_id is None and made.agent_tasks == ()
    assert made.state_version == 1 and made.created_at == at(7) and made.updated_at == at(7)
    assert (made.retries_used, made.replans_used, made.agent_calls_used, made.tool_calls_used, made.execution_time_used_ms, made.tokens_used) == (0,) * 6


def test_before_the_mission_exists_only_mission_created_at_sequence_one_is_taken():
    state, plan = baseline_state_and_plan()
    not_created = make_record(PlanGeneratedPayload(plan=plan), state=state, sequence=1)
    late_created = make_record(created(state), state=state, sequence=2)
    assert reduce(None, not_created).outcome is ReduceOutcome.INVALID_FOR_STATE
    assert reduce(None, late_created).outcome is ReduceOutcome.OUT_OF_ORDER
    for result in (reduce(None, not_created), reduce(None, late_created)):
        assert result.state is None and result.reason


def test_a_mission_cannot_be_created_twice():
    log = prefix()
    again = make_record(created(log.state), state=log.state, sequence=4, number=99)
    result = reduce(state_after(log), again)
    assert result.outcome is ReduceOutcome.INVALID_FOR_STATE and "already exists" in result.reason


def test_created_at_is_when_it_occurred_and_updated_at_is_when_it_was_recorded():
    # D-155 item 1: a timestamp on the state comes from the applied event, and the two envelope times are not the same fact.
    state, plan = baseline_state_and_plan()
    first = make_record(created(state), state=state, sequence=1)
    first = first.model_copy(update={"event": first.event.model_copy(update={"occurred_at": at(100), "recorded_at": at(200)})})
    made = reduce(None, first).state
    assert made.created_at == at(100) and made.updated_at == at(200)
    second = make_record(PlanGeneratedPayload(plan=plan), state=state, sequence=2)
    second = second.model_copy(update={"event": second.event.model_copy(update={"occurred_at": at(300), "recorded_at": at(400)})})
    assert reduce(made, second).state.updated_at == at(400)


# --- the whole baseline, with the expected state written out by hand ---------------------------------------------------------------


def test_a_recorded_verified_baseline_folds_to_exactly_this_state():
    log = verified_baseline()
    state = state_after(log)

    assert state.status is MissionStatus.COMPLETED and state.status_reason == "finished and verified"
    assert state.plans == (log.plan,) and state.active_plan_id == log.plan.plan_id
    assert state.state_version == len(log.records) == 10
    assert state.updated_at == at(10) and state.created_at == at(1)
    assert state.agent_calls_used == 2  # gather and analyse; the VERIFY node is not an agent call
    assert state.tokens_used == (160 + 977) + (322 + 2582)  # what the provider reported, prompt and output
    assert state.execution_time_used_ms == 1200 + 3400 + 5  # accumulated accounted node time, not wall-clock
    assert (state.retries_used, state.replans_used, state.tool_calls_used) == (0, 0, 0)  # nothing produces them


def test_folding_is_deterministic_and_never_changes_its_inputs():
    log = verified_baseline()
    first, second = fold(log.records)[0], fold(log.records)[0]
    assert first.model_dump_json() == second.model_dump_json()
    with pytest.raises(ValidationError):
        first.state_version = 99  # type: ignore[misc]


def test_an_unverified_finished_run_is_completed_with_verified_false_d160_item_5():
    log = prefix()
    log.started("gather")
    log.settled(work_result("gather"))
    log.completed(verified=False)
    state = state_after(log)
    assert state.status is MissionStatus.COMPLETED
    assert state.status_reason == "finished without a successful VERIFY (verified is false)"


def test_a_refused_plan_is_rejected_and_then_the_mission_fails_d160_item_5():
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created()
    log.generated()
    log.rejected(PlanRejectionStage.BINDING, ("unbound_capability", "no agent serves research"))
    log.failed(MissionFailureCause.PLAN_REJECTED, "the plan was refused at binding")
    final = state_after(log)
    assert final.status is MissionStatus.FAILED and final.status_reason == "plan_rejected: the plan was refused at binding"
    assert final.active_plan_id is None and final.plans == (plan,)  # the plan stays in the mission's history; it never became active


def test_a_failed_mission_may_name_no_plan_at_all():
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created()
    log.add(MissionFailedPayload(cause=MissionFailureCause.PLAN_REJECTED, reason="nothing was accepted"))
    assert state_after(log).status is MissionStatus.FAILED


def test_a_halted_run_pauses_the_mission_and_paused_is_terminal_d160_item_9():
    log = prefix()
    log.started("gather")
    log.settled(work_result("gather"))
    log.paused(step="analyse", level=2, reason="held for review")
    state = state_after(log)
    assert state.status is MissionStatus.PAUSED and state.status_reason == "held for review"
    after = reduce(state, make_record(created(log.state), state=log.state, sequence=state.state_version + 1, number=77))
    assert after.outcome is ReduceOutcome.POST_TERMINAL


# --- the counters ------------------------------------------------------------------------------------------------------------------


def counters(state):
    return state.agent_calls_used, state.tokens_used, state.execution_time_used_ms


def test_a_dispatched_work_node_is_one_agent_call_even_if_no_token_count_was_reported():
    log = prefix()
    log.started("gather")
    log.settled(work_result("gather"), duration_ms=10, model_calls=(ModelCallFacts(outcome=ModelCallOutcome.RESPONSE),))
    assert counters(state_after(log)) == (1, 0, 10)  # the call is counted; the unreported tokens are never guessed


def test_only_the_tokens_the_provider_reported_are_counted():
    log = prefix()
    log.started("gather")
    log.settled(
        work_result("gather"), duration_ms=1,
        model_calls=(ModelCallFacts(outcome=ModelCallOutcome.RESPONSE, prompt_tokens=40), ModelCallFacts(outcome=ModelCallOutcome.RESPONSE, output_tokens=7)),
    )
    assert state_after(log).tokens_used == 47


def test_a_failed_model_call_adds_no_tokens_but_the_node_is_still_a_call():
    log = prefix()
    log.started("gather")
    log.settled(work_result("gather", status=NodeStatus.NO_RESULT), duration_ms=5, model_calls=(ModelCallFacts(outcome=ModelCallOutcome.EMPTY_RESPONSE),))
    assert counters(state_after(log)) == (1, 0, 5)


def test_a_node_carried_over_from_prior_outcomes_is_succeeded_but_not_an_agent_call_d120():
    log = prefix()
    log.settled(work_result("gather"), dispatched=False)
    assert counters(state_after(log)) == (0, 0, 0)


def test_skipped_and_not_reached_nodes_change_no_counter():
    log = prefix()
    for status in (NodeStatus.SKIPPED, NodeStatus.NOT_REACHED):
        log.settled(NodeResult(step_id=StepId("analyse"), kind=PlanStepKind.AGENT, status=status, reason="not dispatched"), dispatched=False)
    assert counters(state_after(log)) == (0, 0, 0)


def test_a_dispatched_node_with_no_recorded_duration_adds_no_time_it_is_never_estimated_d160_item_6():
    log = prefix()
    log.started("gather")
    log.settled(work_result("gather"), duration_ms=None)
    log.started("analyse")
    log.settled(work_result("analyse"), duration_ms=250)
    assert counters(state_after(log)) == (2, 0, 250)


def test_a_verify_node_adds_its_time_but_is_not_an_agent_call():
    log = prefix()
    log.started("check")
    log.settled(verify_result("check"), duration_ms=40)
    assert counters(state_after(log)) == (0, 0, 40)


def test_durations_of_nodes_add_up_they_are_not_a_wall_clock_span():
    log = prefix()
    for step in ("gather", "analyse"):  # two nodes that a real run could have overlapped: their times still add
        log.started(step)
        log.settled(work_result(step), duration_ms=1000)
    assert state_after(log).execution_time_used_ms == 2000


# --- the outcomes and the order the checks run in ----------------------------------------------------------------------------------


def test_a_sequence_beyond_the_next_is_out_of_order_and_leaves_the_state_byte_identical():
    log = prefix()
    state = state_after(log)
    ahead = make_record(PlanCompiledPayload(plan_id=log.plan.plan_id, plan_version=1), state=log.state, sequence=state.state_version + 2, number=501)
    result = reduce(state, ahead)
    assert result.outcome is ReduceOutcome.OUT_OF_ORDER and same_bytes(result.state, state)


def test_a_sequence_already_applied_by_a_different_event_is_stale():
    log = prefix()
    state = state_after(log)
    stale = make_record(PlanCompiledPayload(plan_id=log.plan.plan_id, plan_version=1), state=log.state, sequence=2, number=502)
    result = reduce(state, stale, frozenset(r.event.event_id for r in log.records))
    assert result.outcome is ReduceOutcome.STALE and same_bytes(result.state, state)


def test_an_event_that_was_already_applied_is_a_duplicate_and_is_checked_before_anything_else():
    log = prefix()
    state = state_after(log)
    applied = frozenset(r.event.event_id for r in log.records)
    replay_of_the_last = log.records[-1]  # its sequence is stale, but its id is known, so it is a duplicate first
    result = reduce(state, replay_of_the_last, applied)
    assert result.outcome is ReduceOutcome.DUPLICATE and same_bytes(result.state, state)
    next_with_known_id = make_record(PlanCompiledPayload(plan_id=log.plan.plan_id, plan_version=1), state=log.state, sequence=state.state_version + 1, number=1)
    assert reduce(state, next_with_known_id, applied).outcome is ReduceOutcome.DUPLICATE  # even the right sequence: the id decides


def test_an_event_of_another_mission_or_tenant_is_invalid_for_the_state():
    log = prefix()
    state = state_after(log)
    other = make_mission(seed=2)
    foreign = make_record(created(other), state=other, sequence=state.state_version + 1)
    result = reduce(state, foreign)
    assert result.outcome is ReduceOutcome.INVALID_FOR_STATE and "another mission or tenant" in result.reason and same_bytes(result.state, state)


@pytest.mark.parametrize("terminal", ["completed", "failed", "paused"])
def test_after_a_terminal_event_every_later_event_is_post_terminal_and_the_state_is_untouched(terminal):
    log = prefix()
    log.started("gather")
    log.settled(work_result("gather"))
    {"completed": lambda: log.completed(), "failed": lambda: log.failed(), "paused": lambda: log.paused()}[terminal]()
    state = state_after(log)
    version = state.state_version
    later = (
        make_record(PlanCompiledPayload(plan_id=log.plan.plan_id, plan_version=1), state=log.state, sequence=version + 1, number=600),
        make_record(NodeStartedPayload(plan_id=log.plan.plan_id, step_id=StepId("check"), kind=PlanStepKind.VERIFY), state=log.state, sequence=version + 1, number=601),
    )
    for record in later:
        result = reduce(state, record)
        assert result.outcome is ReduceOutcome.POST_TERMINAL and same_bytes(result.state, state)


def test_the_checks_run_in_a_fixed_order_a_wrong_sequence_beats_a_terminal_state():
    log = prefix()
    log.completed()
    state = state_after(log)
    ahead = make_record(PlanCompiledPayload(plan_id=log.plan.plan_id, plan_version=1), state=log.state, sequence=state.state_version + 5, number=700)
    assert reduce(state, ahead).outcome is ReduceOutcome.OUT_OF_ORDER


# --- an event must fit the state it is offered to ---------------------------------------------------------------------------------


def invalid(state, log, payload):
    result = reduce(state, make_record(payload, state=log.state, sequence=state.state_version + 1, number=800))
    assert result.outcome is ReduceOutcome.INVALID_FOR_STATE, result.reason
    assert result.reason and same_bytes(result.state, state)
    return result


def test_a_plan_that_repeats_an_id_or_names_an_unknown_parent_is_invalid_for_the_state():
    log = prefix()
    state = state_after(log)
    invalid(state, log, PlanGeneratedPayload(plan=log.plan))  # the same plan_id again
    orphan = make_mission_plan(log.state, {"a": ""}, version=2, parent=make_mission_plan(log.state, {"z": ""}, plan_number=9), reason="replan")
    result = invalid(state, log, PlanGeneratedPayload(plan=orphan))
    assert "parent_plan_id" in result.reason


def test_a_compile_must_name_a_known_plan_at_its_own_version():
    log = LogBuilder(*baseline_state_and_plan())
    log.created()
    log.generated()
    state = state_after(log)
    invalid(state, log, PlanCompiledPayload(plan_id=PlanId(UUID(int=1)), plan_version=1))
    result = invalid(state, log, PlanCompiledPayload(plan_id=log.plan.plan_id, plan_version=2))
    assert "version" in result.reason


def test_a_node_event_needs_the_active_plan_and_one_of_its_steps_of_the_right_kind():
    log = LogBuilder(*baseline_state_and_plan())
    log.created()
    log.generated()  # generated but not compiled: no active plan yet
    early = state_after(log)
    result = invalid(early, log, NodeStartedPayload(plan_id=log.plan.plan_id, step_id=StepId("gather"), kind=PlanStepKind.AGENT,
                                                    capability=log.plan.steps[0].capability, agent_id=RESEARCH_AGENT))
    assert "not the active plan" in result.reason

    log.compiled()
    state = state_after(log)
    unknown = invalid(state, log, NodeStartedPayload(plan_id=log.plan.plan_id, step_id=StepId("nope"), kind=PlanStepKind.VERIFY))
    assert "is not in plan" in unknown.reason
    wrong_kind = invalid(state, log, NodeStartedPayload(plan_id=log.plan.plan_id, step_id=StepId("check"), kind=PlanStepKind.AGENT,
                                                        capability=log.plan.steps[0].capability, agent_id=RESEARCH_AGENT))
    assert "is a VERIFY step" in wrong_kind.reason
    invalid(state, log, NodeSettledPayload(plan_id=log.plan.plan_id, result=work_result("check"), dispatched=True))  # a work result for a VERIFY step


def test_a_finish_must_be_for_the_active_plan_and_a_pause_for_a_step_of_it():
    log = LogBuilder(*baseline_state_and_plan())
    log.created()
    log.generated()
    state = state_after(log)
    invalid(state, log, MissionCompletedPayload(plan_id=log.plan.plan_id, verified=True))  # never compiled, so never active
    invalid(state, log, MissionFailedPayload(plan_id=PlanId(UUID(int=1)), cause=MissionFailureCause.PLAN_REJECTED, reason="x"))
    log.compiled()
    compiled = state_after(log)
    invalid(compiled, log, MissionPausedPayload(plan_id=log.plan.plan_id, halt=HaltInfo(step_id=StepId("nope"), level=1, reason="held")))


def test_a_rejection_of_an_unknown_plan_is_invalid_for_the_state():
    log = LogBuilder(*baseline_state_and_plan())
    log.created()
    state = state_after(log)
    invalid(state, log, PlanRejectedPayload(plan_id=log.plan.plan_id, stage=PlanRejectionStage.VALIDATION))


# --- REPLAN_TRIGGERED: an accepted within-mission replan never makes the mission terminal (D-199, V1.1 Step 3) --------------------


def test_a_replan_triggered_increments_replans_used_exactly_once_and_touches_nothing_else():
    log = prefix()
    before = state_after(log)
    log.replan_triggered(make_plan_id(2), cause=MissionFailureCause.EXECUTION_FAILED, reason="the agent call failed")
    after = state_after(log)
    assert after.replans_used == before.replans_used + 1 == 1
    assert after.status is MissionStatus.CREATED  # never terminal, never paused: check 4 never engages for it
    assert after.plans == before.plans  # no plan added or removed by this event alone
    assert after.active_plan_id == before.active_plan_id  # unchanged: the next plan is not active until its own PLAN_COMPILED
    assert after.agent_calls_used == before.agent_calls_used == 0  # only replans_used moves


def test_replay_of_a_replan_triggered_log_produces_the_same_state_as_a_live_fold():
    log = prefix()
    log.replan_triggered(make_plan_id(2), reason="verification_failed: insufficient evidence", cause=MissionFailureCause.VERIFICATION_FAILED)
    live = state_after(log)
    replayed = replay(log.records)
    assert replayed.rejection is None
    assert same_bytes(replayed.state, live)


def test_a_replan_triggered_naming_an_unknown_failed_plan_id_is_invalid_for_the_state():
    log = prefix()
    state = state_after(log)
    result = invalid(state, log, ReplanTriggeredPayload(
        failed_plan_id=make_plan_id(999), cause=MissionFailureCause.EXECUTION_FAILED, reason="x", next_plan_id=make_plan_id(2),
    ))
    assert "is not in the mission" in result.reason


def test_a_duplicate_replan_triggered_event_id_is_refused_and_replans_used_increments_once():
    log = prefix()
    log.replan_triggered(make_plan_id(2))
    state = state_after(log)
    assert state.replans_used == 1
    applied = frozenset(r.event.event_id for r in log.records)
    replay_of_the_last = log.records[-1]  # the exact same record, its own event_id already in applied
    result = reduce(state, replay_of_the_last, applied)
    assert result.outcome is ReduceOutcome.DUPLICATE and same_bytes(result.state, state)
    assert result.state.replans_used == 1  # the established event-identity rule alone stops a second increment; no new one was invented


@pytest.mark.parametrize("terminal", ["completed", "failed", "paused"])
def test_a_terminal_mission_refuses_a_replan_triggered_through_ordinary_reduce(terminal):
    log = prefix()
    log.started("gather")
    log.settled(work_result("gather"))
    {"completed": lambda: log.completed(), "failed": lambda: log.failed(), "paused": lambda: log.paused()}[terminal]()
    state = state_after(log)
    later = make_record(
        ReplanTriggeredPayload(failed_plan_id=log.plan.plan_id, cause=MissionFailureCause.EXECUTION_FAILED, reason="x", next_plan_id=make_plan_id(2)),
        state=log.state, sequence=state.state_version + 1, number=900,
    )
    result = reduce(state, later)
    assert result.outcome is ReduceOutcome.POST_TERMINAL and same_bytes(result.state, state)


def test_a2a_resumed_pause_is_unaffected_reduce_resumed_still_the_only_path_past_it():
    # Guards against a regression where REPLAN_TRIGGERED's own new reducer case might accidentally bypass the
    # existing D-177 terminal-state protection for a genuinely paused mission — it does not, because check 4
    # (terminal) runs before check 5 (the event's own rule) for every payload type, this one included.
    log = prefix()
    log.paused_awaiting("gather")
    state = state_after(log)
    later = make_record(
        ReplanTriggeredPayload(failed_plan_id=log.plan.plan_id, cause=MissionFailureCause.EXECUTION_FAILED, reason="x", next_plan_id=make_plan_id(2)),
        state=log.state, sequence=state.state_version + 1, number=901,
    )
    assert reduce(state, later).outcome is ReduceOutcome.POST_TERMINAL


def test_ordinary_events_continue_normally_after_a_replan_triggered_event_the_mission_can_still_conclude():
    log = prefix()
    log.started("gather"), log.settled(work_result("gather", status=NodeStatus.FAILED, reason="model failure"))
    log.replan_triggered(make_plan_id(2), cause=MissionFailureCause.EXECUTION_FAILED, reason="the agent call failed")

    second = make_mission_plan(
        log.state, {"gather": ""}, capability_of={"gather": "research"}, version=2, parent=log.plan, reason="the agent call failed", plan_number=2,
    )
    log.add(PlanGeneratedPayload(plan=second))
    log.add(PlanCompiledPayload(plan_id=second.plan_id, plan_version=2))
    log.add(NodeStartedPayload(plan_id=second.plan_id, step_id=StepId("gather"), kind=PlanStepKind.AGENT, capability=log.plan.steps[0].capability, agent_id=RESEARCH_AGENT))
    log.add(NodeSettledPayload(plan_id=second.plan_id, result=work_result("gather"), dispatched=True, duration_ms=500, model_calls=()))
    log.add(MissionCompletedPayload(plan_id=second.plan_id, verified=False))

    state = state_after(log)
    assert state.status is MissionStatus.COMPLETED
    assert state.replans_used == 1
    assert state.active_plan_id == second.plan_id
    assert set(p.plan_id for p in state.plans) == {log.plan.plan_id, second.plan_id}  # immutable plan history: nothing removed


def test_the_next_plan_id_must_differ_from_the_failed_plan_id():
    with pytest.raises(ValidationError, match="a different plan"):
        ReplanTriggeredPayload(
            failed_plan_id=make_plan_id(1), cause=MissionFailureCause.EXECUTION_FAILED, reason="x", next_plan_id=make_plan_id(1),
        )


def test_a_replan_triggered_payload_requires_every_field():
    complete = dict(failed_plan_id=make_plan_id(1), cause=MissionFailureCause.EXECUTION_FAILED, reason="x", next_plan_id=make_plan_id(2))
    ReplanTriggeredPayload(**complete)
    for missing in ("failed_plan_id", "cause", "reason", "next_plan_id"):
        fields = {k: v for k, v in complete.items() if k != missing}
        with pytest.raises(ValidationError):
            ReplanTriggeredPayload(**fields)
    with pytest.raises(ValidationError):
        ReplanTriggeredPayload(**{**complete, "reason": ""})  # min_length=1
    with pytest.raises(ValidationError):
        ReplanTriggeredPayload(**{**complete, "cause": "not_a_real_cause"})


def test_a_replan_triggered_sequence_folds_identically_across_hash_seeds():
    script = (
        "import sys, hashlib; sys.path[:0] = ['src', 'tests/support', 'tests/unit/state']\n"
        "from eidos_state_factories import RESEARCH_AGENT, LogBuilder, baseline_state_and_plan, work_result\n"
        "from eidos_mission_factories import make_mission_plan\n"
        "from eidos_expansion_factories import make_plan_id\n"
        "from eidos.contracts import PlanStepKind, StepId\n"
        "from eidos.runtime import NodeStatus\n"
        "from eidos.state import MissionCompletedPayload, MissionFailureCause, NodeSettledPayload, NodeStartedPayload, PlanCompiledPayload, PlanGeneratedPayload, reduce\n"
        "state, plan = baseline_state_and_plan()\n"
        "log = LogBuilder(state, plan)\n"
        "log.created(), log.generated(), log.compiled()\n"
        "log.started('gather'), log.settled(work_result('gather', status=NodeStatus.FAILED, reason='x'))\n"
        "log.replan_triggered(make_plan_id(2), cause=MissionFailureCause.EXECUTION_FAILED, reason='the agent call failed')\n"
        "second = make_mission_plan(state, {'gather': ''}, capability_of={'gather': 'research'}, version=2, parent=plan, reason='r', plan_number=2)\n"
        "log.add(PlanGeneratedPayload(plan=second))\n"
        "log.add(PlanCompiledPayload(plan_id=second.plan_id, plan_version=2))\n"
        "log.add(NodeStartedPayload(plan_id=second.plan_id, step_id=StepId('gather'), kind=PlanStepKind.AGENT, capability=plan.steps[0].capability, agent_id=RESEARCH_AGENT))\n"
        "log.add(NodeSettledPayload(plan_id=second.plan_id, result=work_result('gather'), dispatched=True, duration_ms=500, model_calls=()))\n"
        "log.add(MissionCompletedPayload(plan_id=second.plan_id, verified=False))\n"
        "s = None; applied = frozenset()\n"
        "for r in log.records:\n"
        "    res = reduce(s, r, applied)\n"
        "    assert res.applied, res.reason\n"
        "    s, applied = res.state, applied | {r.event.event_id}\n"
        "print(hashlib.sha256(s.model_dump_json().encode()).hexdigest())\n"
    )
    digests = set()
    for seed in ("0", "1", "2", "12345"):
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": seed})
        assert result.returncode == 0, result.stderr
        digests.add(result.stdout.strip())
    assert len(digests) == 1 and len(next(iter(digests))) == 64


# --- ordering is the sequence and never a timestamp (D-160 item 7) -----------------------------------------------------------------


def test_events_apply_in_sequence_order_whatever_their_timestamps_say():
    log = prefix()
    log.add(NodeStartedPayload(plan_id=log.plan.plan_id, step_id=StepId("gather"), kind=PlanStepKind.AGENT,
                               capability=log.plan.steps[0].capability, agent_id=RESEARCH_AGENT), seconds=1)  # earlier than its predecessors
    state = state_after(log)
    assert state.state_version == 4
    assert state.updated_at == at(1)  # the last applied event's own recorded time, even though it is earlier than the one before


def test_parallel_nodes_may_settle_in_either_order_and_the_state_is_the_same():
    def build(order):
        log = prefix()
        for step in order:
            log.started(step)
        for step in order:
            log.settled(work_result(step), duration_ms=100 if step == "gather" else 200, model_calls=(response_call(1, 2),))
        return state_after(log)

    forward, backward = build(("gather", "analyse")), build(("analyse", "gather"))
    assert counters(forward) == counters(backward) == (2, 6, 300)


# --- V0.6 Step 4: A2A_TASK_STARTED / A2A_TASK_COMPLETED, and the D-176 exception for an awaiting-caused pause -------------------------


def test_an_a2a_task_started_folds_a_new_submitted_agent_task_and_changes_no_counter():
    log = prefix()
    before = state_after(log)
    log.a2a_started("gather", task=1)
    state = state_after(log)
    assert len(state.agent_tasks) == 1
    task = state.agent_tasks[0]
    assert task.status is AgentTaskStatus.SUBMITTED
    assert task.a2a_task_id == a2a_task_id(1) and task.a2a_context_id is None
    assert task.agent_id == RESEARCH_AGENT
    assert task.plan_id == log.plan.plan_id and task.step_id == StepId("gather")
    assert task.started_at == log.records[-1].event.occurred_at
    assert task.last_event == log.records[-1].event.event_id
    assert counters(state) == counters(before)  # no counter change: A2A_TASK_STARTED folds only agent_tasks


def test_an_a2a_task_completed_updates_the_correlated_task_in_place_not_a_duplicate_append():
    log = prefix()
    log.a2a_started("gather", task=1)
    started_at_event = log.records[-1].event.occurred_at
    log.a2a_completed("gather", task=1, outcome=AgentTaskStatus.COMPLETED)
    state = state_after(log)
    assert len(state.agent_tasks) == 1  # replaced, not appended (D-176's find-and-replace)
    task = state.agent_tasks[0]
    assert task.status is AgentTaskStatus.COMPLETED
    assert task.latest_artifact is not None
    assert task.agent_id == RESEARCH_AGENT and task.plan_id == log.plan.plan_id and task.step_id == StepId("gather")
    assert task.started_at == started_at_event  # unchanged from the STARTED event
    assert task.last_event == log.records[-1].event.event_id  # advanced to the COMPLETED event
    assert counters(state) == (0, 0, 0)  # no counter change: that is NODE_SETTLED's job, later, via existing V0.5 machinery (D-167)


def test_multiple_independent_a2a_tasks_fold_independently_and_in_order():
    log = prefix()
    log.a2a_started("gather", task=1)
    log.a2a_started("analyse", task=2)
    state = state_after(log)
    assert [t.a2a_task_id for t in state.agent_tasks] == [a2a_task_id(1), a2a_task_id(2)]
    log.a2a_completed("gather", task=1)
    state = state_after(log)
    assert [(t.a2a_task_id, t.status) for t in state.agent_tasks] == [
        (a2a_task_id(1), AgentTaskStatus.COMPLETED), (a2a_task_id(2), AgentTaskStatus.SUBMITTED),
    ]


def test_a_completed_event_for_an_a2a_task_that_never_started_is_rejected_d172():
    log = prefix()
    state = state_after(log)
    result = invalid(state, log, A2ATaskCompletedPayload(
        plan_id=log.plan.plan_id, step_id=StepId("gather"), a2a_task_id=a2a_task_id(1),
        outcome=AgentTaskStatus.COMPLETED, artifact=None, reason="x",
    ))
    assert "no recorded A2A_TASK_STARTED" in result.reason


def test_a_completed_event_naming_the_wrong_plan_step_for_a_started_task_is_rejected():
    log = prefix()
    log.a2a_started("gather", task=1)
    state = state_after(log)
    result = invalid(state, log, A2ATaskCompletedPayload(
        plan_id=log.plan.plan_id, step_id=StepId("analyse"), a2a_task_id=a2a_task_id(1),  # started for "gather", not "analyse"
        outcome=AgentTaskStatus.COMPLETED, artifact=None, reason="x",
    ))
    assert "different plan step" in result.reason


def test_an_a2a_event_needs_the_active_plan_and_one_of_its_steps_kind_agent():
    log = LogBuilder(*baseline_state_and_plan())
    log.created()
    log.generated()  # not compiled: no active plan yet
    early = state_after(log)
    result = invalid(early, log, A2ATaskStartedPayload(
        plan_id=log.plan.plan_id, step_id=StepId("gather"), agent_id=RESEARCH_AGENT, a2a_task_id=a2a_task_id(1),
    ))
    assert "not the active plan" in result.reason

    log.compiled()
    state = state_after(log)
    wrong_kind = invalid(state, log, A2ATaskStartedPayload(
        plan_id=log.plan.plan_id, step_id=StepId("check"), agent_id=RESEARCH_AGENT, a2a_task_id=a2a_task_id(1),  # "check" is VERIFY, not AGENT
    ))
    assert "is a VERIFY step" in wrong_kind.reason


def test_the_reducer_holds_no_per_task_state_so_it_never_returns_the_repeated_agent_task_outcome():
    """D-172, mirroring D-162 item 1's own reducer test: only the intake and replay refuse a repeat; the reducer, offered one directly, applies it
    again (a harmless, idempotent-looking fold, per fold_agent_task's own docstring)."""
    log = prefix()
    log.a2a_started("gather", task=1)
    log.a2a_completed("gather", task=1)
    state, applied = None, frozenset()
    for r in log.records:
        result = reduce(state, r, applied)
        state, applied = result.state, applied | {r.event.event_id}
    again = make_record(log.records[-1].payload, state=log.state, sequence=state.state_version + 1, number=999)  # the completion, once more
    result = reduce(state, again, applied)
    assert result.outcome is ReduceOutcome.APPLIED  # reapplies: only the intake stops this (agent_task_events.py, D-172)


def test_a_repeated_a2a_task_started_at_reducer_level_replaces_not_duplicates():
    """Offered directly (bypassing the intake's D-172 guard), the reducer still folds through fold_agent_task's own find-and-replace,
    never a raw append: the same D-176 primitive Step 2 built, exercised here a second time for the same a2a_task_id."""
    log = prefix()
    log.a2a_started("gather", task=1)
    state, applied = None, frozenset()
    for r in log.records:
        result = reduce(state, r, applied)
        state, applied = result.state, applied | {r.event.event_id}
    again = make_record(log.records[-1].payload, state=log.state, sequence=state.state_version + 1, number=998)  # the same start, once more
    result = reduce(state, again, applied)
    assert result.applied and len(result.state.agent_tasks) == 1  # replaced, not appended


# --- D-176: an awaiting-caused pause takes exactly one more event; an admission-halt pause is otherwise unchanged --------------------


def test_an_awaiting_paused_mission_still_accepts_the_completion_that_concludes_the_outstanding_task():
    log = prefix()
    log.a2a_started("gather", task=1)
    log.paused_awaiting("gather", reason="awaiting the remote gather task")
    state = state_after(log)
    assert state.status is MissionStatus.PAUSED
    completed = A2ATaskCompletedPayload(
        plan_id=log.plan.plan_id, step_id=StepId("gather"), a2a_task_id=a2a_task_id(1),
        outcome=AgentTaskStatus.COMPLETED, artifact=None, reason="the remote task concluded",
    )
    result = reduce(state, make_record(completed, state=log.state, sequence=state.state_version + 1, number=850))
    assert result.applied
    assert result.state.status is MissionStatus.PAUSED and result.state.status_reason == state.status_reason  # unchanged: never auto-resumed (D-170)
    assert result.state.agent_tasks[0].status is AgentTaskStatus.COMPLETED  # the bookkeeping did update


def test_an_awaiting_pauses_status_reason_is_the_awaiting_infos_own_reason():
    log = prefix()
    log.a2a_started("gather", task=1)
    log.paused_awaiting("gather", reason="awaiting the remote gather task")
    assert state_after(log).status_reason == "awaiting the remote gather task"


def test_an_awaiting_pause_must_name_a_step_of_the_active_plan_just_like_a_halt():
    log = prefix()
    state = state_after(log)
    result = invalid(state, log, MissionPausedPayload(
        plan_id=log.plan.plan_id, awaiting=(AwaitingInfo(step_id=StepId("nope"), level=1, reason="x"),)
    ))
    assert "is not in plan" in result.reason


def test_an_awaiting_paused_mission_refuses_a_completion_for_an_unrelated_task():
    log = prefix()
    log.a2a_started("gather", task=1)
    log.paused_awaiting("gather")
    state = state_after(log)
    unrelated = A2ATaskCompletedPayload(
        plan_id=log.plan.plan_id, step_id=StepId("gather"), a2a_task_id=a2a_task_id(2),  # a different task, never started
        outcome=AgentTaskStatus.COMPLETED, artifact=None, reason="x",
    )
    result = reduce(state, make_record(unrelated, state=log.state, sequence=state.state_version + 1, number=851))
    assert result.outcome is ReduceOutcome.POST_TERMINAL  # the exception is keyed to a genuinely outstanding, correlated task, not any A2A event


def test_an_awaiting_paused_mission_refuses_a_second_completion_of_the_same_already_concluded_task():
    log = prefix()
    log.a2a_started("gather", task=1)
    log.paused_awaiting("gather")
    state = state_after(log)
    completed = A2ATaskCompletedPayload(
        plan_id=log.plan.plan_id, step_id=StepId("gather"), a2a_task_id=a2a_task_id(1),
        outcome=AgentTaskStatus.COMPLETED, artifact=None, reason="the remote task concluded",
    )
    first = reduce(state, make_record(completed, state=log.state, sequence=state.state_version + 1, number=852))
    assert first.applied
    second = reduce(first.state, make_record(completed, state=log.state, sequence=first.state.state_version + 1, number=853))
    assert second.outcome is ReduceOutcome.POST_TERMINAL  # the task has already concluded: the exception no longer applies to it


def test_an_awaiting_paused_mission_otherwise_refuses_everything_exactly_like_an_admission_halt():
    log = prefix()
    log.a2a_started("gather", task=1)
    log.paused_awaiting("gather")
    state = state_after(log)
    later = make_record(PlanCompiledPayload(plan_id=log.plan.plan_id, plan_version=1), state=log.state, sequence=state.state_version + 1, number=854)
    assert reduce(state, later).outcome is ReduceOutcome.POST_TERMINAL


def test_an_admission_halt_paused_mission_refuses_a_completion_with_nothing_outstanding_for_that_task():
    log = prefix()
    log.started("gather")
    log.settled(work_result("gather"))
    log.paused(step="analyse", level=2, reason="held for review")
    state = state_after(log)
    completed = A2ATaskCompletedPayload(
        plan_id=log.plan.plan_id, step_id=StepId("gather"), a2a_task_id=a2a_task_id(1),  # no AgentTask was ever folded
        outcome=AgentTaskStatus.COMPLETED, artifact=None, reason="x",
    )
    result = reduce(state, make_record(completed, state=log.state, sequence=state.state_version + 1, number=855))
    assert result.outcome is ReduceOutcome.POST_TERMINAL  # the ordinary admission-halt case: nothing outstanding, so nothing is exempted


def test_an_admission_halt_paused_mission_still_folds_a_genuinely_outstanding_tasks_completion():
    """D-176's exception is keyed on what the state holds (an outstanding, correlated AgentTask), never on *why* the mission paused —
    MissionState records no such reason, and none is added (D-176 named only the agent_tasks fold as new). An admission-halt pause that
    happens to coexist with an independently outstanding A2A task therefore still takes that task's completion: it only updates
    agent_tasks bookkeeping and can never touch status, so the halt's own terminality is not reopened by this. This is a deliberate,
    flagged reading of an interaction D-176 did not itself spell out — not something the owner has separately ruled on."""
    log = prefix()
    log.a2a_started("gather", task=1)  # an A2A task is genuinely outstanding
    log.paused(step="analyse", level=2, reason="held for review")  # an unrelated admission halt
    state = state_after(log)
    completed = A2ATaskCompletedPayload(
        plan_id=log.plan.plan_id, step_id=StepId("gather"), a2a_task_id=a2a_task_id(1),
        outcome=AgentTaskStatus.COMPLETED, artifact=None, reason="the remote task concluded",
    )
    result = reduce(state, make_record(completed, state=log.state, sequence=state.state_version + 1, number=856))
    assert result.applied
    assert result.state.status is MissionStatus.PAUSED and result.state.status_reason == "held for review"  # the halt's own reason, untouched
    assert result.state.agent_tasks[0].status is AgentTaskStatus.COMPLETED


def test_a_completed_or_failed_mission_refuses_a_task_completion_even_for_an_outstanding_task():
    """D-176 exempts only a paused mission (the one status a later A2A completion can meaningfully still concern) — never completed or
    failed, which stay exactly as terminal as V0.5 shipped them, whatever eidos.state.agent_tasks happens to still show."""
    log = prefix()
    log.a2a_started("gather", task=1)
    log.started("analyse")
    log.settled(work_result("analyse"))
    log.started("check")
    log.settled(verify_result("check"))
    log.completed(verified=True)
    state = state_after(log)
    completed = A2ATaskCompletedPayload(
        plan_id=log.plan.plan_id, step_id=StepId("gather"), a2a_task_id=a2a_task_id(1),
        outcome=AgentTaskStatus.COMPLETED, artifact=None, reason="x",
    )
    result = reduce(state, make_record(completed, state=log.state, sequence=state.state_version + 1, number=857))
    assert result.outcome is ReduceOutcome.POST_TERMINAL


def test_a_log_with_an_awaiting_pause_and_its_completion_replays_and_checkpoints_consistently():
    log = prefix()
    log.a2a_started("gather", task=1)
    log.paused_awaiting("gather")
    log.add(A2ATaskCompletedPayload(
        plan_id=log.plan.plan_id, step_id=StepId("gather"), a2a_task_id=a2a_task_id(1),
        outcome=AgentTaskStatus.COMPLETED, artifact=None, reason="the remote task concluded",
    ))
    full = state_after(log)
    assert full.status is MissionStatus.PAUSED and full.agent_tasks[0].status is AgentTaskStatus.COMPLETED

    records = log.records
    live = EventLog()
    for r in records:
        result = live.accept(EventProposal(
            event_id=r.event.event_id, tenant_id=r.event.tenant_id, mission_id=r.event.mission_id,
            occurred_at=r.event.occurred_at, recorded_at=r.event.recorded_at, payload=r.payload,
        ))
        assert result.applied, result.reason
    assert replay(records).state == full == live.state
    for sequence in range(1, len(records) + 1):
        checkpoint = checkpoint_at(records, sequence)
        assert resume(checkpoint, records_after(records, checkpoint)).state == full


# --- the result type and the source ------------------------------------------------------------------------------------------------


def test_an_applied_result_needs_a_state_and_no_reason_and_a_non_applied_one_needs_a_reason():
    state, _ = baseline_state_and_plan()
    with pytest.raises(ValidationError):
        ReduceResult(state=None, outcome=ReduceOutcome.APPLIED)
    with pytest.raises(ValidationError):
        ReduceResult(state=state, outcome=ReduceOutcome.APPLIED, reason="why")
    for outcome in ReduceOutcome:
        if outcome is not ReduceOutcome.APPLIED:
            with pytest.raises(ValidationError):
                ReduceResult(state=state, outcome=outcome)


def test_the_outcomes_are_the_reducers_six_and_the_two_the_intake_and_replay_add():
    reducer_outcomes = {"applied", "duplicate", "out_of_order", "stale", "post_terminal", "invalid_for_state"}
    # D-155 item 2's six, D-162 item 1's repeated_step_event, and D-172's repeated_agent_task_event.
    assert {o.value for o in ReduceOutcome} == reducer_outcomes | {"repeated_step_event", "repeated_agent_task_event"}


def test_the_reducer_holds_no_per_node_state_so_it_never_returns_the_repeated_step_outcome():
    """D-162 item 1: the intake and replay refuse a repeated start or settlement; the reducer, offered one directly, judges it by its five checks."""
    log = verified_baseline()
    state, applied = None, frozenset()
    for r in log.records[:5]:  # created, generated, compiled, gather started, gather settled
        result = reduce(state, r, applied)
        state, applied = result.state, applied | {r.event.event_id}
    again = make_record(log.records[4].payload, state=log.state, sequence=6, number=999)  # gather's settlement, once more, under a new event_id
    result = reduce(state, again, applied)
    assert result.outcome is ReduceOutcome.APPLIED and result.state.agent_calls_used == 2  # the counters fold twice: only the intake stops this


def test_the_folded_state_is_identical_across_hash_seeds():
    script = (
        "import sys, hashlib; sys.path[:0] = ['src', 'tests/support', 'tests/unit/state']\n"
        "from eidos_state_factories import verified_baseline\n"
        "from eidos.state import reduce\n"
        "state, applied = None, frozenset()\n"
        "for r in verified_baseline().records:\n"
        "    res = reduce(state, r, applied)\n"
        "    assert res.applied, res.reason\n"
        "    state, applied = res.state, applied | {r.event.event_id}\n"
        "print(hashlib.sha256(state.model_dump_json().encode()).hexdigest())\n"
    )
    digests = set()
    for seed in ("0", "1", "2", "12345"):
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": seed})
        assert result.returncode == 0, result.stderr
        digests.add(result.stdout.strip())
    assert len(digests) == 1 and len(next(iter(digests))) == 64
