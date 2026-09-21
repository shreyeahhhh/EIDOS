"""The ``ExecutionRecord`` of a really recorded baseline pass (decisions.md D-159; V0.5 Step 6).

The state tests build logs by hand. Here the log is written by the recorder over the real V0.4 agents and verifier (with a scripted model), so
the record is checked against a pass as it actually happens: the bound agents, the model-call facts, and the verifier's own reason.
"""

from eidos.agents import ModelFailure, ModelFailureKind
from eidos.contracts import MissionStatus, StepId
from eidos.runtime import NodeStatus, RunOutcome, VerificationVerdict
from eidos.state import (
    ExecutionRecord,
    MissionFailureCause,
    dump_jsonl,
    execution_record,
    load_jsonl,
)

from eidos_recording_factories import baseline_mission, record, respond_with_facts
from eidos_v04_registry import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID


def project(run) -> ExecutionRecord:
    result = execution_record(run.log.records)
    assert isinstance(result, ExecutionRecord), result
    return result


def test_a_recorded_verified_baseline_projects_to_its_bound_agents_facts_and_verdict():
    state, plan = baseline_mission()
    run, _ = record(state, plan)
    result = project(run)
    assert (result.mission_status, result.run_outcome, result.verified) == (MissionStatus.COMPLETED, RunOutcome.FINISHED, True)
    assert [s.agent_id for s in result.steps] == [RESEARCH_AGENT_ID, ANALYSIS_AGENT_ID, None]
    assert [s.result.status for s in result.steps] == [NodeStatus.SUCCEEDED] * 3
    assert (result.agent_calls_used, result.tokens_used, result.execution_time_used_ms) == (2, 600, 3000)  # the fixed test values of the scripted model and clock
    assert (result.model_calls, result.responses_missing_token_counts, result.repeated_step_events) == (2, 0, 0)
    verdict = result.steps[2].verification
    assert verdict.verdict is VerificationVerdict.PASS and verdict.reason == result.steps[2].result.reason
    assert "NOT_EVALUATED: min_quality, max_risk_level" in verdict.reason  # the clauses nothing measures stay named (D-146)


def test_the_record_of_the_live_log_equals_the_record_of_the_log_replayed_from_jsonl():
    state, plan = baseline_mission()
    run, _ = record(state, plan)
    loaded = load_jsonl(dump_jsonl(run.log.records))
    assert loaded.rejection is None
    assert execution_record(loaded.records) == project(run)
    assert project(run).model_dump_json() == execution_record(loaded.records).model_dump_json()


def test_a_model_failure_is_recorded_with_its_typed_kind_and_the_cause_of_the_failed_mission():
    state, plan = baseline_mission()
    failure = ModelFailure(kind=ModelFailureKind.EMPTY_RESPONSE, message="the model returned nothing")
    run, _ = record(state, plan, respond=respond_with_facts(research=failure))
    result = project(run)
    assert (result.mission_status, result.run_outcome, result.failure_cause) == (MissionStatus.FAILED, RunOutcome.FAILED, MissionFailureCause.NO_RESULT)
    gather = next(s for s in result.steps if s.step_id == StepId("gather"))
    assert gather.result.status is NodeStatus.NO_RESULT and [c.outcome.value for c in gather.model_calls] == ["empty_response"]
    assert [s.dispatched for s in result.steps] == [True, False, False] and [s.agent_id for s in result.steps] == [RESEARCH_AGENT_ID, None, None]
    assert result.failure_reason == gather.result.reason and result.tokens_used == 0  # a failed call reported no tokens, and none are invented
