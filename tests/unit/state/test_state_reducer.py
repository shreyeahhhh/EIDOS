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

from eidos.contracts import MissionState, MissionStatus, PlanId, PlanStepKind, StepId
from eidos.runtime import HaltInfo, NodeResult, NodeStatus
from eidos.state import (
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
    reduce,
)

from eidos_mission_factories import make_mission, make_mission_plan
from eidos_state_factories import (
    RESEARCH_AGENT,
    LogBuilder,
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


def test_the_outcomes_are_the_reducers_six_and_the_one_the_intake_and_replay_add():
    reducer_outcomes = {"applied", "duplicate", "out_of_order", "stale", "post_terminal", "invalid_for_state"}
    assert {o.value for o in ReduceOutcome} == reducer_outcomes | {"repeated_step_event"}  # D-155 item 2's six, and D-162 item 1's


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
