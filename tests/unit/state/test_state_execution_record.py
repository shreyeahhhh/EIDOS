"""``ExecutionRecord``: the derived, read-only record of one execution (decisions.md D-159; V0.5 Step 6).

It is a projection of the event log and nothing else. These tests pin what it says for every way an execution can end, that it is the same
record whether it is projected from a live log or from one replayed from JSONL, that a prefix of a log projects too, that it never carries a
quality, and that nothing is dropped silently.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from eidos.contracts import CapabilityId, MissionStatus, PlanStepKind, StepId
from eidos.runtime import HaltInfo, NodeStatus, RunOutcome, VerificationVerdict
from eidos.state import (
    EventLog,
    ExecutionRecord,
    MissionFailureCause,
    ModelCallFacts,
    ModelCallOutcome,
    NodeSettledPayload,
    NodeStartedPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    PlanRejectionStage,
    ReduceOutcome,
    ReplayRejection,
    ReplayRejectionCode,
    StepRecord,
    VerificationFacts,
    dump_jsonl,
    execution_record,
    load_jsonl,
)

from eidos_mission_factories import make_mission_plan
from eidos_state_factories import (
    ANALYSIS_AGENT,
    RESEARCH_AGENT,
    LogBuilder,
    baseline_state_and_plan,
    response_call,
    verified_baseline,
    verify_result,
    work_result,
)

ROOT = Path(__file__).resolve().parents[3]
PASS = VerificationFacts(verdict=VerificationVerdict.PASS, reason="the supported rules were satisfied")


def project(log: LogBuilder) -> ExecutionRecord:
    record = execution_record(log.records)
    assert isinstance(record, ExecutionRecord), record
    return record


def step(record: ExecutionRecord, name: str) -> StepRecord:
    return next(s for s in record.steps if s.step_id == name)


# --- a verified baseline ---------------------------------------------------------------------------------------------------------------


def test_a_verified_baseline_is_projected_with_identity_structure_and_every_recorded_fact():
    log = verified_baseline()
    record = project(log)
    state, plan = log.state, log.plan
    assert (record.tenant_id, record.mission_id, record.execution_id) == (state.tenant_id, state.mission_id, state.execution_id)
    assert (record.plan_id, record.plan_version) == (plan.plan_id, plan.version)
    assert [(s.step_id, s.kind, s.capability, s.depends_on) for s in record.steps] == [
        ("gather", PlanStepKind.AGENT, "research", ()),
        ("analyse", PlanStepKind.AGENT, "analysis", ("gather",)),
        ("check", PlanStepKind.VERIFY, None, ("analyse",)),
    ]
    assert [s.agent_id for s in record.steps] == [RESEARCH_AGENT, ANALYSIS_AGENT, None]  # the binding, as NODE_STARTED recorded it
    assert all(s.started and s.dispatched for s in record.steps)
    assert [s.result.status for s in record.steps] == [NodeStatus.SUCCEEDED] * 3
    assert [s.result.artifact for s in record.steps[:2]] == ["artifact:gather", "artifact:analyse"]
    assert [s.duration_ms for s in record.steps] == [1200, 3400, 5]
    assert step(record, "gather").model_calls == (response_call(160, 977, 53.0),)
    assert step(record, "analyse").model_calls == (response_call(322, 2582, 154.2),)
    assert step(record, "check").verification == PASS and step(record, "gather").verification is None
    assert (record.mission_status, record.run_outcome, record.verified) == (MissionStatus.COMPLETED, RunOutcome.FINISHED, True)
    assert (record.failure_cause, record.failure_reason, record.halt) == (None, None, None)
    assert (record.plan_rejected_at, record.plan_rejection_reasons) == (None, ())


def test_the_counters_are_the_folded_ones_and_the_counts_are_of_recorded_things():
    log = verified_baseline()
    record = project(log)
    state = EventLog.restore(log.records).state
    assert record.agent_calls_used == state.agent_calls_used == 2
    assert record.tokens_used == state.tokens_used == (160 + 977) + (322 + 2582)
    assert record.execution_time_used_ms == state.execution_time_used_ms == 1200 + 3400 + 5
    assert (record.tool_calls_used, record.retries_used, record.replans_used) == (0, 0, 0)
    assert (record.model_calls, record.responses_missing_token_counts) == (2, 0)
    assert record.status_reason == state.status_reason


def test_the_log_bounds_are_the_first_and_last_records_by_sequence():
    log = verified_baseline()
    record = project(log)
    assert record.event_count == len(log.records) == 10
    assert (record.first_occurred_at, record.last_occurred_at) == (log.records[0].event.occurred_at, log.records[-1].event.occurred_at)


# --- every way an execution ends ---------------------------------------------------------------------------------------------------


def unfinished() -> LogBuilder:
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created(), log.generated(), log.compiled()
    return log


def test_a_failed_verification_is_a_failed_run_with_the_verdict_and_the_cause_recorded():
    log = unfinished()
    log.started("gather"), log.settled(work_result("gather"), model_calls=(response_call(),))
    log.started("analyse"), log.settled(work_result("analyse"), model_calls=(response_call(),))
    fail = VerificationFacts(verdict=VerificationVerdict.FAIL, reason="a citation is unsupported")
    log.started("check")
    log.settled(verify_result("check", status=NodeStatus.VERIFICATION_FAILED, reason=fail.reason), verification=fail)
    log.failed(MissionFailureCause.VERIFICATION_FAILED, fail.reason)
    record = project(log)
    assert (record.mission_status, record.run_outcome, record.verified) == (MissionStatus.FAILED, RunOutcome.FAILED, None)
    assert (record.failure_cause, record.failure_reason) == (MissionFailureCause.VERIFICATION_FAILED, "a citation is unsupported")
    assert step(record, "check").verification == fail and step(record, "check").result.status is NodeStatus.VERIFICATION_FAILED


def test_a_work_node_that_produced_nothing_leaves_the_rest_skipped_and_never_dispatched():
    log = unfinished()
    log.started("gather")
    log.settled(work_result("gather", status=NodeStatus.NO_RESULT, reason="empty_response"), model_calls=(ModelCallFacts(outcome=ModelCallOutcome.EMPTY_RESPONSE),))
    log.settled(work_result("analyse", status=NodeStatus.SKIPPED, reason="a predecessor did not succeed"), dispatched=False)
    log.settled(verify_result("check", status=NodeStatus.SKIPPED, reason="a predecessor did not succeed"), dispatched=False)
    log.failed(MissionFailureCause.NO_RESULT, "empty_response")
    record = project(log)
    assert (record.run_outcome, record.failure_cause) == (RunOutcome.FAILED, MissionFailureCause.NO_RESULT)
    skipped = step(record, "analyse")
    assert (skipped.started, skipped.dispatched, skipped.duration_ms, skipped.model_calls, skipped.agent_id) == (False, False, None, (), None)
    assert skipped.result.status is NodeStatus.SKIPPED
    assert (record.model_calls, record.responses_missing_token_counts) == (1, 0)  # a failed call is a call, and not a response that lacked tokens
    assert record.agent_calls_used == 1


def test_a_finished_run_without_a_verify_verdict_is_completed_and_says_it_is_not_verified():
    log = unfinished()
    log.started("gather"), log.settled(work_result("gather"), model_calls=(response_call(),))
    log.started("analyse"), log.settled(work_result("analyse"), model_calls=(response_call(),))
    log.settled(verify_result("check", status=NodeStatus.SKIPPED, reason="not run"), dispatched=False)
    log.completed(verified=False)
    record = project(log)
    assert (record.mission_status, record.run_outcome, record.verified) == (MissionStatus.COMPLETED, RunOutcome.FINISHED, False)
    assert step(record, "check").verification is None


def test_a_paused_mission_carries_the_halt_and_the_nodes_that_were_not_reached():
    log = unfinished()
    log.started("gather"), log.settled(work_result("gather"), model_calls=(response_call(),))
    log.settled(work_result("analyse", status=NodeStatus.NOT_REACHED, reason="halted before this node"), dispatched=False)
    log.settled(verify_result("check", status=NodeStatus.NOT_REACHED, reason="halted before this node"), dispatched=False)
    log.paused("analyse", 2, "held for review")
    record = project(log)
    assert (record.mission_status, record.run_outcome, record.verified) == (MissionStatus.PAUSED, RunOutcome.HALTED, None)
    assert record.halt == HaltInfo(step_id=StepId("analyse"), level=2, reason="held for review")
    assert step(record, "analyse").result.status is NodeStatus.NOT_REACHED and record.status_reason == "held for review"


def test_a_refused_plan_records_the_stage_and_reasons_and_no_run():
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created(), log.generated()
    log.rejected(PlanRejectionStage.BINDING, ("no_agent", "no agent offers 'analysis'"))
    log.failed(MissionFailureCause.PLAN_REJECTED, "the plan was refused at the binding gate")
    record = project(log)
    assert (record.plan_rejected_at, [(r.code, r.message) for r in record.plan_rejection_reasons]) == (PlanRejectionStage.BINDING, [("no_agent", "no agent offers 'analysis'")])
    assert (record.mission_status, record.run_outcome, record.failure_cause) == (MissionStatus.FAILED, None, MissionFailureCause.PLAN_REJECTED)
    assert record.plan_id == plan.plan_id and all(not s.started and s.result is None for s in record.steps)  # the plan is shown; nothing ran


def test_a_run_the_executor_refused_is_a_failure_with_no_run_outcome():
    log = unfinished()
    log.failed(MissionFailureCause.RUN_REJECTED, "invalid_prior_state: the prior belongs to another plan version")
    record = project(log)
    assert (record.run_outcome, record.failure_cause) == (None, MissionFailureCause.RUN_REJECTED) and record.plan_rejected_at is None


def test_a_mission_with_no_plan_yet_projects_to_a_record_with_no_plan():
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created()
    record = project(log)
    assert (record.plan_id, record.plan_version, record.steps) == (None, None, ())
    assert (record.mission_status, record.run_outcome, record.event_count) == (MissionStatus.CREATED, None, 1)


# --- a log is projectable at every point, and a live log and a replayed one give the same record ---------------------------------------


def test_every_prefix_of_a_log_projects_and_a_step_carries_nothing_until_it_has_settled():
    log = verified_baseline()
    seen = []
    for n in range(1, len(log.records) + 1):
        record = execution_record(log.records[:n])
        assert isinstance(record, ExecutionRecord) and record.event_count == n
        seen.append(tuple((s.started, s.result is not None) for s in record.steps))
    assert seen[0] == ()  # one record: the mission exists, no plan yet
    assert seen[1] == seen[2] == ((False, False),) * 3  # the plan is generated, then compiled: nothing has started
    assert seen[3] == ((True, False), (False, False), (False, False))  # gather started, not settled: no settlement facts
    assert seen[4] == ((True, True), (False, False), (False, False))
    assert seen[-1] == ((True, True),) * 3


def test_the_record_of_a_live_log_equals_the_record_of_the_same_log_replayed_from_jsonl():
    log = verified_baseline()
    live = execution_record(EventLog.restore(log.records).records)
    loaded = load_jsonl(dump_jsonl(log.records))
    assert loaded.rejection is None
    replayed = execution_record(loaded.records)
    assert live == replayed and live.model_dump_json() == replayed.model_dump_json()


def test_projecting_is_pure_it_does_not_change_the_log_and_gives_the_same_record_every_time():
    log = verified_baseline()
    before = tuple(log.records)
    first, second = execution_record(log.records), execution_record(iter(log.records))  # any iterable of records will do
    assert first == second and tuple(log.records) == before


def test_a_record_is_immutable():
    record = project(verified_baseline())
    with pytest.raises(ValidationError):
        record.verified = False  # type: ignore[misc]
    with pytest.raises(ValidationError):
        record.steps[0].agent_id = None  # type: ignore[misc]


def test_a_step_that_has_not_settled_cannot_carry_settlement_facts_and_a_settled_one_says_whether_it_was_dispatched():
    base = {"step_id": StepId("gather"), "kind": PlanStepKind.AGENT, "depends_on": (), "started": True}
    StepRecord(**base)  # an unsettled step carrying nothing is fine
    for extra in ({"dispatched": True}, {"duration_ms": 5}, {"model_calls": (response_call(),)}, {"verification": PASS}):
        with pytest.raises(ValidationError, match="has not settled"):
            StepRecord(**base, **extra)
    with pytest.raises(ValidationError, match="whether it was dispatched"):
        StepRecord(**base, result=work_result("gather"))
    assert StepRecord(**base, result=work_result("gather"), dispatched=True).dispatched is True


# --- what it will not say ---------------------------------------------------------------------------------------------------------


FORBIDDEN_WORDS = ("quality", "confidence", "score", "rate", "signature", "risk", "estimate", "predicted", "success")


def test_no_field_of_the_record_is_a_quality_a_confidence_a_score_a_rate_a_signature_or_an_estimate():
    names = [*ExecutionRecord.model_fields, *StepRecord.model_fields]
    assert [n for n in names if any(word in n for word in FORBIDDEN_WORDS)] == []


def test_what_the_verifier_did_not_evaluate_stays_named_in_its_reason_and_is_not_turned_into_anything_else():
    reason = "all rules held. NOT_EVALUATED: min_quality, max_risk_level (no defined deterministic measurement)."
    log = unfinished()
    log.started("gather"), log.settled(work_result("gather"), model_calls=(response_call(),))
    log.started("analyse"), log.settled(work_result("analyse"), model_calls=(response_call(),))
    log.started("check")
    log.settled(verify_result("check", reason=reason), verification=VerificationFacts(verdict=VerificationVerdict.PASS, reason=reason))
    log.completed(verified=True)
    record = project(log)
    assert step(record, "check").verification.reason == reason == step(record, "check").result.reason  # word for word, in both places


def test_a_response_that_reported_no_token_counts_is_counted_so_the_lower_bound_is_visible():
    log = unfinished()
    log.started("gather")
    log.settled(work_result("gather"), model_calls=(response_call(10, 20), ModelCallFacts(outcome=ModelCallOutcome.RESPONSE, prompt_tokens=5), ModelCallFacts(outcome=ModelCallOutcome.RESPONSE)))
    log.started("analyse"), log.settled(work_result("analyse"), model_calls=(ModelCallFacts(outcome=ModelCallOutcome.TIMEOUT),))
    log.settled(verify_result("check", status=NodeStatus.SKIPPED, reason="a predecessor did not succeed"), dispatched=False)
    log.completed(verified=False)
    record = project(log)
    assert record.model_calls == 4  # every call the log recorded, response or failure
    assert record.responses_missing_token_counts == 2  # the response with only a prompt count, and the one with none; the timeout had nothing to report
    assert record.tokens_used == 10 + 20 + 5  # only what a provider reported, and it says by how many calls that may fall short


# --- nothing is dropped silently -----------------------------------------------------------------------------------------------------


def test_a_log_the_reducer_would_refuse_is_a_typed_rejection_and_never_a_record():
    log = verified_baseline()
    gap = execution_record(log.records[:3] + log.records[4:])  # the fourth record is missing, so the fifth is out of order
    assert isinstance(gap, ReplayRejection) and gap.code is ReplayRejectionCode.NOT_APPLICABLE and gap.sequence == 5
    empty = execution_record(())
    assert isinstance(empty, ReplayRejection)


def test_a_log_that_repeats_a_steps_settlement_or_start_is_a_typed_rejection_and_never_a_record():
    """A record has at most one start and one settlement per step because the replay it starts with refuses a repeat (D-162 item 1)."""
    for index, changed in ((4, {"duration_ms": 9999}), (3, {"agent_id": ANALYSIS_AGENT})):  # gather's NODE_SETTLED, then its NODE_STARTED, again
        log = verified_baseline()
        again = log.records[index].payload.model_copy(update=changed)
        log.records.pop()  # drop the terminal event so the mission is still open
        log.add(again)
        rejected = execution_record(log.records)
        assert isinstance(rejected, ReplayRejection) and rejected.code is ReplayRejectionCode.NOT_APPLICABLE
        assert rejected.outcome is ReduceOutcome.REPEATED_STEP_EVENT and rejected.sequence == len(log.records)


# --- a replanned mission: the record is of the active plan and of its nodes only ---------------------------------------------------


def with_a_second_plan(compiled: bool) -> LogBuilder:
    log = verified_baseline()
    log.records.pop()  # the first plan did not finish: it is being replaced
    second = make_mission_plan(
        log.state, {"gather": "", "check": "gather"}, verify=("check",), capability_of={"gather": "research"},
        version=2, parent=log.plan, reason="the first plan's analysis was unsupported", plan_number=2,
    )
    log.add(PlanGeneratedPayload(plan=second))
    if compiled:
        log.add(PlanCompiledPayload(plan_id=second.plan_id, plan_version=2))
        log.add(NodeStartedPayload(plan_id=second.plan_id, step_id=StepId("gather"), kind=PlanStepKind.AGENT, capability=CapabilityId("research"), agent_id=ANALYSIS_AGENT))
        log.add(NodeSettledPayload(plan_id=second.plan_id, result=work_result("gather"), dispatched=True, duration_ms=777, model_calls=()))
    log.second = second
    return log


def test_the_record_is_of_the_active_plan_and_takes_only_that_plans_node_events():
    log = with_a_second_plan(compiled=True)
    record = project(log)
    assert (record.plan_id, record.plan_version) == (log.second.plan_id, 2)
    assert [s.step_id for s in record.steps] == ["gather", "check"]
    gather = step(record, "gather")
    assert (gather.duration_ms, gather.agent_id, gather.model_calls) == (777, ANALYSIS_AGENT, ())  # the second plan's node, not the first plan's gather
    assert not step(record, "check").started
    # the same step name settled in the first plan too, and that is not a repeat: a step is identified by its plan and its step id
    assert step(record, "gather").result is not None


def test_a_plan_generated_but_not_yet_compiled_does_not_displace_the_active_plan():
    log = with_a_second_plan(compiled=False)
    record = project(log)
    assert (record.plan_id, record.plan_version) == (log.plan.plan_id, 1)
    assert [s.step_id for s in record.steps] == ["gather", "analyse", "check"]


# --- determinism ------------------------------------------------------------------------------------------------------------------


def test_the_record_is_identical_across_hash_seeds():
    script = (
        "import sys, hashlib; sys.path[:0] = ['src', 'tests/support']\n"
        "from eidos_state_factories import verified_baseline\n"
        "from eidos.state import execution_record\n"
        "print(hashlib.sha256(execution_record(verified_baseline().records).model_dump_json().encode()).hexdigest())\n"
    )
    seen = set()
    for seed in ("0", "1", "2", "12345"):
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": seed})
        assert result.returncode == 0, result.stderr
        seen.add(result.stdout.strip())
    assert len(seen) == 1 and len(next(iter(seen))) == 64
    in_process = hashlib.sha256(execution_record(verified_baseline().records).model_dump_json().encode()).hexdigest()
    assert seen == {in_process}
