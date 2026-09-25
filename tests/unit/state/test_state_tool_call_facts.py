"""Tool-call facts on ``NODE_SETTLED``, the reducer's ``tool_calls_used`` fold and ``StepRecord.tool_calls`` (decisions.md D-203, D-204 item 2;
V1.2 Step 3).

The fact type refuses a mislabelled call; the payload carries facts only for a dispatched work node and only additively; the reducer counts exactly
the calls that reached a tool; and the execution record shows each step's calls without changing what ``tool_calls_used`` means.
"""

import json

import pytest
from pydantic import ValidationError

from eidos.agents import ToolFailureKind
from eidos.contracts import CapabilityId, PlanStepKind, StepId
from eidos.policy import ToolDenialCode
from eidos.runtime import NodeStatus
from eidos.state import (
    EventRecord,
    NodeSettledPayload,
    NodeStartedPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    ReduceOutcome,
    StepRecord,
    ToolCallFacts,
    ToolCallOutcome,
    ToolDenialReason,
    execution_record,
    reduce,
    replay,
)

from eidos_mission_factories import make_mission_plan
from eidos_state_factories import (
    RESEARCH_AGENT,
    LogBuilder,
    baseline_state_and_plan,
    response_call,
    verified_baseline,
    verify_result,
    work_result,
)
from eidos_tool_fact_factories import (
    INVOCATIONS,
    NOT_INVOCATIONS,
    TOOL_ID,
    artifact_refs,
    denied_call,
    digest,
    failed_call,
    result_call,
    served_call,
    settle_with_tools,
)

FAILURES = [o for o in ToolCallOutcome if o not in (ToolCallOutcome.RESULT, ToolCallOutcome.SERVED_STORED, ToolCallOutcome.DENIED)]


def open_log() -> LogBuilder:
    """A mission whose plan is compiled and whose nodes have not started."""
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created(), log.generated(), log.compiled()
    return log


# --- the fact type: every kind carries exactly what can be true of it -------------------------------------------------------------


def test_each_kind_of_call_constructs_with_exactly_the_fields_that_can_be_true_of_it():
    invoked = result_call(number=1, documents=3, result_bytes=900, elapsed_ms=12)
    assert (invoked.outcome, invoked.args_digest, len(invoked.result_refs), invoked.result_bytes, invoked.elapsed_ms) == (
        ToolCallOutcome.RESULT, digest(1), 3, 900, 12,
    )
    for outcome in FAILURES:
        failure = failed_call(outcome, number=2)
        assert failure.outcome is outcome and failure.result_refs == () and failure.result_bytes is None and failure.denial is None
    served = served_call(number=1, documents=3, result_bytes=900)
    assert (served.outcome, served.result_refs, served.result_bytes, served.elapsed_ms) == (ToolCallOutcome.SERVED_STORED, artifact_refs(1, 3), 900, None)
    denied = denied_call(ToolDenialReason.UNKNOWN_TOOL)
    assert (denied.outcome, denied.denial, denied.args_digest, denied.result_refs) == (ToolCallOutcome.DENIED, ToolDenialReason.UNKNOWN_TOOL, None, ())


@pytest.mark.parametrize("outcome", list(ToolCallOutcome), ids=lambda o: o.value)
def test_only_a_call_that_reached_a_tool_is_an_invocation(outcome):
    facts = {
        ToolCallOutcome.DENIED: denied_call(),
        ToolCallOutcome.SERVED_STORED: served_call(),
        ToolCallOutcome.RESULT: result_call(),
    }.get(outcome) or failed_call(outcome)
    assert facts.invoked is (outcome not in (ToolCallOutcome.SERVED_STORED, ToolCallOutcome.DENIED))


def test_the_invocations_and_the_calls_that_are_not_partition_the_fixture_vocabulary():
    assert {c.outcome for c in INVOCATIONS} | {c.outcome for c in NOT_INVOCATIONS} == set(ToolCallOutcome)
    assert all(c.invoked for c in INVOCATIONS) and not any(c.invoked for c in NOT_INVOCATIONS)


@pytest.mark.parametrize("extra", [
    dict(args_digest=digest()), dict(result_refs=artifact_refs(1, 1)), dict(result_bytes=1), dict(elapsed_ms=1),
], ids=["digest", "refs", "bytes", "elapsed"])
def test_a_denied_call_reached_no_tool_it_carries_its_reason_and_nothing_else(extra):
    with pytest.raises(ValidationError):
        ToolCallFacts(tool_id=TOOL_ID, outcome=ToolCallOutcome.DENIED, denial=ToolDenialReason.NOT_READ_ONLY, **extra)


def test_a_denial_reason_belongs_to_a_denied_call_and_a_denied_call_needs_one():
    with pytest.raises(ValidationError):
        ToolCallFacts(tool_id=TOOL_ID, outcome=ToolCallOutcome.DENIED)
    for outcome in (ToolCallOutcome.RESULT, ToolCallOutcome.SERVED_STORED, ToolCallOutcome.TIMEOUT):
        with pytest.raises(ValidationError):
            ToolCallFacts(tool_id=TOOL_ID, outcome=outcome, denial=ToolDenialReason.UNKNOWN_TOOL, args_digest=digest())


@pytest.mark.parametrize("outcome", [o for o in ToolCallOutcome if o is not ToolCallOutcome.DENIED], ids=lambda o: o.value)
def test_a_call_that_passed_the_argument_check_carries_a_well_formed_request_digest(outcome):
    with pytest.raises(ValidationError):
        ToolCallFacts(tool_id=TOOL_ID, outcome=outcome)
    for bad in ("", "xyz", "A" * 64, "a" * 63, "a" * 65, " " + "a" * 63):
        with pytest.raises(ValidationError):
            ToolCallFacts(tool_id=TOOL_ID, outcome=outcome, args_digest=bad)


@pytest.mark.parametrize("outcome", FAILURES, ids=lambda o: o.value)
@pytest.mark.parametrize("extra", [dict(result_refs=artifact_refs(1, 1)), dict(result_bytes=1)], ids=["refs", "bytes"])
def test_a_failed_invocation_has_no_answer_to_reference_or_measure(outcome, extra):
    with pytest.raises(ValidationError):
        ToolCallFacts(tool_id=TOOL_ID, outcome=outcome, args_digest=digest(), **extra)


def test_a_failed_invocation_may_still_say_how_long_it_took():
    assert failed_call(ToolCallOutcome.TIMEOUT, elapsed_ms=5000).elapsed_ms == 5000


def test_a_served_duplicate_invoked_nothing_so_it_has_no_elapsed_time():
    with pytest.raises(ValidationError):
        ToolCallFacts(tool_id=TOOL_ID, outcome=ToolCallOutcome.SERVED_STORED, args_digest=digest(), elapsed_ms=0)


def test_a_result_may_be_empty_nothing_matched_and_that_is_not_a_failure():
    nothing = result_call(documents=0, result_bytes=0)
    assert nothing.result_refs == () and nothing.result_bytes == 0 and nothing.invoked


def test_a_call_lists_each_artifact_it_produced_at_most_once():
    refs = artifact_refs(1, 1)
    for outcome in (ToolCallOutcome.RESULT, ToolCallOutcome.SERVED_STORED):
        with pytest.raises(ValidationError):
            ToolCallFacts(tool_id=TOOL_ID, outcome=outcome, args_digest=digest(), result_refs=refs + refs)


@pytest.mark.parametrize("bad", [dict(result_bytes=-1), dict(elapsed_ms=-1)])
def test_a_measurement_is_never_negative(bad):
    with pytest.raises(ValidationError):
        ToolCallFacts(tool_id=TOOL_ID, outcome=ToolCallOutcome.RESULT, args_digest=digest(), **bad)


def test_the_tool_id_is_recorded_verbatim_so_a_call_that_named_nothing_valid_is_still_recordable():
    assert denied_call(ToolDenialReason.UNKNOWN_TOOL, tool_id="").tool_id == ""
    assert denied_call(ToolDenialReason.UNKNOWN_TOOL, tool_id=" Not/A Tool ").tool_id == " Not/A Tool "


def test_a_fact_is_immutable_and_strict():
    fact = result_call()
    with pytest.raises(ValidationError):
        fact.result_bytes = 1
    with pytest.raises(ValidationError):
        ToolCallFacts(tool_id=TOOL_ID, outcome="result", args_digest=digest(), quality=1)  # type: ignore[call-arg]


def test_the_recorded_tool_outcomes_are_the_agents_failure_kinds_plus_result_served_and_denied():
    assert {o.value for o in ToolCallOutcome} == {"result", "served_stored", "denied"} | {k.value for k in ToolFailureKind}


def test_the_recorded_denial_reasons_are_the_admission_codes_value_for_value():
    assert {r.value for r in ToolDenialReason} == {c.value for c in ToolDenialCode}


def test_the_fact_has_exactly_these_fields_and_none_that_judges_the_call():
    assert set(ToolCallFacts.model_fields) == {"tool_id", "outcome", "denial", "args_digest", "result_refs", "result_bytes", "elapsed_ms"}
    forbidden = ("quality", "confidence", "score", "rate", "signature", "estimate", "predicted", "success")
    assert [name for name in ToolCallFacts.model_fields if any(word in name for word in forbidden)] == []


# --- the payload: additive, and only for a dispatched work node ----------------------------------------------------------------


def settled_payload(log: LogBuilder, result=None, **fields) -> NodeSettledPayload:
    return NodeSettledPayload(plan_id=log.plan.plan_id, result=result or work_result("gather"), dispatched=True, duration_ms=5, **fields)


def test_a_settlement_without_tool_calls_is_what_it_always_was_the_field_defaults_to_empty():
    log = open_log()
    assert settled_payload(log).tool_calls == ()


def test_a_dispatched_work_node_carries_its_tool_calls_in_call_order():
    log = open_log()
    calls = (result_call(number=1), denied_call(), served_call(number=1), failed_call(number=2))
    assert settled_payload(log, tool_calls=calls).tool_calls == calls


def test_a_node_that_was_not_dispatched_has_no_tool_calls():
    log = open_log()
    with pytest.raises(ValidationError):
        NodeSettledPayload(plan_id=log.plan.plan_id, result=work_result("gather", status=NodeStatus.SUCCEEDED), dispatched=False, tool_calls=(result_call(),))


def test_only_a_work_node_makes_tool_calls_a_verify_node_makes_none():
    log = open_log()
    with pytest.raises(ValidationError):
        settled_payload(log, result=verify_result("check"), tool_calls=(result_call(),))


def test_tool_facts_survive_the_json_round_trip_of_the_record_exactly():
    log = open_log()
    log.started("gather")
    record = settle_with_tools(log, work_result("gather"), (result_call(number=1), denied_call(), served_call(number=1)))
    parsed = EventRecord.model_validate_json(record.model_dump_json())
    assert parsed == record and parsed.payload.tool_calls == record.payload.tool_calls


def test_a_settlement_written_before_the_field_existed_reads_back_with_no_tool_calls():
    log = open_log()
    log.started("gather")
    record = log.settled(work_result("gather"))
    written = json.loads(record.model_dump_json())
    assert written["payload"]["tool_calls"] == []
    del written["payload"]["tool_calls"]  # the shape of a record written before V1.2 Step 3
    assert EventRecord.model_validate_json(json.dumps(written)) == record


# --- the reducer: tool_calls_used counts the calls that reached a tool, and only those -----------------------------------------


def state_after(log: LogBuilder):
    replayed = replay(log.records)
    assert replayed.state is not None, replayed.rejection
    return replayed.state


def test_a_call_that_reached_a_tool_is_counted_whatever_it_came_to():
    for call in INVOCATIONS:
        log = open_log()
        log.started("gather")
        settle_with_tools(log, work_result("gather"), (call,))
        assert state_after(log).tool_calls_used == 1, call.outcome


def test_a_served_duplicate_and_a_denial_reached_no_tool_and_count_for_nothing():
    for call in NOT_INVOCATIONS:
        log = open_log()
        log.started("gather")
        settle_with_tools(log, work_result("gather"), (call,))
        assert state_after(log).tool_calls_used == 0, call.outcome


def test_multiple_calls_in_one_node_are_each_counted_once_and_only_the_invocations():
    log = open_log()
    log.started("gather")
    settle_with_tools(log, work_result("gather"), (
        result_call(number=1), served_call(number=1), failed_call(number=2), denied_call(), result_call(number=3), denied_call(ToolDenialReason.UNKNOWN_TOOL),
    ))
    assert state_after(log).tool_calls_used == 3


def test_the_counter_accumulates_across_nodes_as_a_whole_mission_running_total():
    log = open_log()
    log.started("gather")
    settle_with_tools(log, work_result("gather"), (result_call(number=1), result_call(number=2)))
    log.started("analyse")
    settle_with_tools(log, work_result("analyse"), (failed_call(number=3), served_call(number=1)))
    log.started("check")
    log.settled(verify_result("check"))
    assert state_after(log).tool_calls_used == 3


def test_recording_tool_calls_changes_no_other_counter_and_no_other_part_of_the_state():
    plain, with_tools = open_log(), open_log()
    for log, calls in ((plain, ()), (with_tools, (result_call(), failed_call(number=2), served_call(), denied_call()))):
        log.started("gather")
        settle_with_tools(log, work_result("gather"), calls, duration_ms=250, model_calls=(response_call(10, 20, 0.5),))
    before, after = state_after(plain), state_after(with_tools)
    assert before.tool_calls_used == 0 and after.tool_calls_used == 2
    assert after.model_copy(update={"tool_calls_used": 0}) == before  # nothing else about the state moved


def test_the_tool_counter_is_independent_of_the_agent_call_the_token_and_the_time_counters():
    log = open_log()
    log.started("gather")
    settle_with_tools(log, work_result("gather"), (result_call(),), duration_ms=1234, model_calls=(response_call(7, 11, 0.25),))
    state = state_after(log)
    assert (state.agent_calls_used, state.tokens_used, state.execution_time_used_ms, state.tool_calls_used) == (1, 18, 1234, 1)


def test_a_settlement_is_folded_once_the_duplicate_of_an_applied_event_adds_nothing():
    log = open_log()
    log.started("gather")
    record = settle_with_tools(log, work_result("gather"), (result_call(), result_call(number=2)))
    state = state_after(log)
    again = reduce(state, record, frozenset(r.event.event_id for r in log.records))
    assert again.outcome is ReduceOutcome.DUPLICATE and again.state == state and again.state.tool_calls_used == 2


def test_a_log_with_no_tool_calls_folds_to_zero_as_every_earlier_log_did():
    assert state_after(verified_baseline()).tool_calls_used == 0


# --- the execution record: each step's calls, and the whole-mission meaning of the counter (D-204 item 2) ---------------------


def step_of(record, name: str) -> StepRecord:
    return next(s for s in record.steps if s.step_id == name)


def test_each_settled_step_shows_the_tool_calls_it_made_in_call_order():
    log = open_log()
    log.started("gather")
    gather_calls = (result_call(number=1), denied_call(), failed_call(number=2))
    settle_with_tools(log, work_result("gather"), gather_calls)
    log.started("analyse")
    settle_with_tools(log, work_result("analyse"), (served_call(number=1),))
    log.started("check")
    log.settled(verify_result("check"))
    record = execution_record(log.records)
    assert step_of(record, "gather").tool_calls == gather_calls
    assert step_of(record, "analyse").tool_calls == (served_call(number=1),)
    assert step_of(record, "check").tool_calls == ()
    assert record.tool_calls_used == 2 == sum(c.invoked for s in record.steps for c in s.tool_calls)


def test_a_step_that_has_not_settled_carries_no_tool_calls():
    log = open_log()
    log.started("gather")
    record = execution_record(log.records)
    assert step_of(record, "gather").tool_calls == ()
    step = step_of(record, "gather")
    with pytest.raises(ValidationError):
        StepRecord(step_id=step.step_id, kind=step.kind, depends_on=step.depends_on, started=True, tool_calls=(result_call(),))


def test_a_step_not_dispatched_in_this_run_shows_none():
    log = open_log()
    log.started("gather")
    log.settled(work_result("gather", status=NodeStatus.FAILED))
    log.settled(work_result("analyse", status=NodeStatus.SKIPPED, reason="a predecessor failed"), dispatched=False)
    record = execution_record(log.records)
    assert step_of(record, "analyse").tool_calls == () and step_of(record, "analyse").dispatched is False


def test_the_records_own_field_names_still_pass_the_no_judgement_guard():
    from eidos.state import ExecutionRecord

    forbidden = ("quality", "confidence", "score", "rate", "signature", "risk", "estimate", "predicted", "success")
    names = [*ExecutionRecord.model_fields, *StepRecord.model_fields]
    assert [n for n in names if any(word in n for word in forbidden)] == []


def test_a_scoped_projection_keeps_the_mission_total_and_the_scoped_steps_give_the_per_attempt_count():
    # D-204 item 2: ``tool_calls_used`` stays the whole-mission running total; the per-step facts carry each attempt's own calls.
    log = open_log()
    log.started("gather")
    settle_with_tools(log, work_result("gather"), (result_call(number=1), failed_call(number=2), denied_call()))
    second = make_mission_plan(
        log.state, {"gather": "", "check": "gather"}, verify=("check",), capability_of={"gather": "research"},
        version=2, parent=log.plan, reason="the first plan did not conclude", plan_number=2,
    )
    log.add(PlanGeneratedPayload(plan=second))
    log.add(PlanCompiledPayload(plan_id=second.plan_id, plan_version=2))
    log.add(NodeStartedPayload(plan_id=second.plan_id, step_id=StepId("gather"), kind=PlanStepKind.AGENT, capability=CapabilityId("research"), agent_id=RESEARCH_AGENT))
    log.add(NodeSettledPayload(plan_id=second.plan_id, result=work_result("gather"), dispatched=True, duration_ms=9, tool_calls=(result_call(number=3),)))

    whole = execution_record(log.records)
    first_attempt = execution_record(log.records, plan_id=log.plan.plan_id)
    second_attempt = execution_record(log.records, plan_id=second.plan_id)
    assert whole.tool_calls_used == first_attempt.tool_calls_used == second_attempt.tool_calls_used == 3  # the whole-mission total, however scoped
    per_attempt = lambda record: sum(c.invoked for s in record.steps for c in s.tool_calls)  # noqa: E731
    assert (per_attempt(first_attempt), per_attempt(second_attempt)) == (2, 1)
    assert step_of(first_attempt, "gather").tool_calls == (result_call(number=1), failed_call(number=2), denied_call())
    assert step_of(second_attempt, "gather").tool_calls == (result_call(number=3),)
