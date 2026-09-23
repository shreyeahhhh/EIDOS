"""``project`` (decisions.md D-159, D-196; V0.9 Steps 2 and 4).

Logs are built by hand with ``LogBuilder`` (``eidos_state_factories.py``), mirroring
``tests/unit/state/test_state_execution_record.py``'s own established discipline: no agent, backend or provider
import, so this package's own unit tests stay independent of everything above ``eidos.state``.
"""

from eidos.contracts import MissionStatus
from eidos.runtime import NodeStatus, RunOutcome, VerificationVerdict
from eidos.state import (
    MissionFailureCause,
    ModelCallOutcome,
    PlanRejectionStage,
    ReplayRejection,
    VerificationFacts,
    dump_jsonl,
    execution_record,
    load_jsonl,
)
from eidos.telemetry import TelemetryRecord, project

from eidos_mission_factories import make_mission, make_mission_plan
from eidos_state_factories import (
    ANALYSIS_AGENT,
    LogBuilder,
    ModelCallFacts,
    at,
    baseline_state_and_plan,
    verified_baseline,
    verify_result,
    work_result,
)


# --- a verified baseline: every copied field matches execution_record exactly ------------------------------------


def test_projects_a_verified_baseline_matching_execution_record_field_for_field():
    log = verified_baseline()
    result = project(log.records)
    assert isinstance(result, TelemetryRecord)
    record = execution_record(log.records)
    assert not isinstance(record, ReplayRejection)

    assert (result.tenant_id, result.mission_id, result.execution_id) == (record.tenant_id, record.mission_id, record.execution_id)
    assert (result.plan_id, result.plan_version) == (record.plan_id, record.plan_version)
    assert (result.agent_calls_used, result.tool_calls_used) == (record.agent_calls_used, record.tool_calls_used)
    assert (result.retries_used, result.replans_used) == (record.retries_used, record.replans_used)
    assert (result.tokens_used, result.responses_missing_token_counts) == (record.tokens_used, record.responses_missing_token_counts)
    assert result.execution_time_used_ms == record.execution_time_used_ms
    assert (result.mission_status, result.run_outcome) == (record.mission_status, record.run_outcome)
    assert (result.failure_cause, result.verified) == (record.failure_cause, record.verified)
    assert result.plan_rejected_at == record.plan_rejected_at
    assert result.model_call_count == record.model_calls
    assert result.event_count == record.event_count
    assert (result.first_occurred_at, result.last_occurred_at) == (record.first_occurred_at, record.last_occurred_at)


def test_verified_baseline_facts_are_the_fixed_test_values():
    log = verified_baseline()
    result = project(log.records)
    assert result.mission_status is MissionStatus.COMPLETED
    assert result.run_outcome is RunOutcome.FINISHED
    assert result.verified is True
    assert result.failure_cause is None
    assert result.plan_rejected_at is None  # nothing was ever rejected in a verified baseline
    assert (result.agent_calls_used, result.tokens_used, result.model_call_count) == (2, 977 + 160 + 2582 + 322, 2)
    assert result.execution_time_used_ms == 1200 + 3400 + 5  # gather + analyse + check's own recorded durations


# --- determinism -----------------------------------------------------------------------------------------------


def test_deterministic_across_repeated_calls():
    log = verified_baseline()
    first = project(log.records)
    second = project(tuple(log.records))  # a fresh tuple, not the same object
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_project_accepts_a_plain_generator_not_only_a_concrete_sequence():
    log = verified_baseline()
    result = project(r for r in log.records)  # nothing here needs a file, a log object, or a concrete sequence
    assert isinstance(result, TelemetryRecord)


# --- reconstruction from recorded events, without rerunning anything -----------------------------------------


def test_reconstructed_from_a_jsonl_round_trip_equals_the_live_projection():
    log = verified_baseline()
    live = project(log.records)
    loaded = load_jsonl(dump_jsonl(log.records))
    assert loaded.rejection is None
    replayed = project(loaded.records)
    assert replayed == live
    assert replayed.model_dump_json() == live.model_dump_json()


# --- node status counts -----------------------------------------------------------------------------------------


def test_node_status_counts_for_a_fully_succeeded_mission():
    log = verified_baseline()
    result = project(log.records)
    assert result.succeeded_count == 3  # gather, analyse, check
    assert (result.failed_count, result.no_result_count, result.verification_failed_count) == (0, 0, 0)
    assert (result.verification_inconclusive_count, result.skipped_count, result.not_reached_count, result.awaiting_count) == (0, 0, 0, 0)


def test_node_status_counts_for_a_halted_mission_with_not_reached_nodes():
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created()
    log.generated()
    log.compiled()
    log.started("gather")
    log.settled(work_result("gather"), duration_ms=1200, model_calls=(ModelCallFacts(outcome=ModelCallOutcome.RESPONSE, prompt_tokens=100, output_tokens=200, elapsed_seconds=1.0),))
    log.settled(work_result("analyse", status=NodeStatus.NOT_REACHED, reason="the run halted"), dispatched=False)
    log.settled(verify_result("check", status=NodeStatus.NOT_REACHED, reason="the run halted"), dispatched=False)
    log.paused(step="analyse")
    result = project(log.records)
    assert result.run_outcome is RunOutcome.HALTED
    assert result.succeeded_count == 1
    assert result.not_reached_count == 2
    assert (result.failed_count, result.skipped_count, result.awaiting_count) == (0, 0, 0)


def test_node_status_counts_for_a_mission_with_no_steps_at_all_after_a_plan_rejection():
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created()
    log.generated()
    log.rejected()  # defaults to PlanRejectionStage.VALIDATION
    log.failed(cause=MissionFailureCause.PLAN_REJECTED, reason="the plan was refused at the validation gate")
    result = project(log.records)
    assert result.mission_status is MissionStatus.FAILED
    assert result.failure_cause is MissionFailureCause.PLAN_REJECTED
    assert result.plan_rejected_at is PlanRejectionStage.VALIDATION
    total = (
        result.succeeded_count + result.failed_count + result.no_result_count + result.verification_failed_count
        + result.verification_inconclusive_count + result.skipped_count + result.not_reached_count + result.awaiting_count
    )
    assert total == 0  # no node ever started or settled for a plan that was rejected


def test_plan_rejected_at_reflects_the_actual_recorded_gate_not_a_hardcoded_default():
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created()
    log.generated()
    log.rejected(PlanRejectionStage.COMPILATION)
    log.failed(cause=MissionFailureCause.PLAN_REJECTED, reason="the plan was refused at the compilation gate")
    result = project(log.records)
    assert result.plan_rejected_at is PlanRejectionStage.COMPILATION


# --- remote-task (A2A) count -----------------------------------------------------------------------------------


def test_remote_task_count_counts_remote_task_started_events():
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created()
    log.generated()
    log.compiled()
    log.a2a_started("gather", task=1)
    log.a2a_completed("gather", task=1)
    log.started("analyse")
    log.settled(work_result("analyse"), duration_ms=3400)
    log.started("check")
    log.settled(
        verify_result("check"), duration_ms=5,
        verification=VerificationFacts(verdict=VerificationVerdict.PASS, reason="the supported rules were satisfied"),
    )
    log.completed(verified=True)
    result = project(log.records)
    assert result.remote_task_count == 1


def test_remote_task_count_is_zero_when_no_remote_task_was_ever_submitted():
    result = project(verified_baseline().records)
    assert result.remote_task_count == 0


# --- missing optional provider facts stay missing, never guessed ------------------------------------------------


def test_a_failed_model_call_leaves_tokens_unmeasured_not_guessed_at_zero():
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created()
    log.generated()
    log.compiled()
    log.started("gather")
    log.settled(
        work_result("gather", status=NodeStatus.FAILED, reason="the model call failed (timeout): no answer"),
        duration_ms=1000,
        model_calls=(ModelCallFacts(outcome=ModelCallOutcome.TIMEOUT),),
    )
    log.settled(work_result("analyse", status=NodeStatus.SKIPPED, reason="a predecessor did not succeed"), dispatched=False)
    log.settled(verify_result("check", status=NodeStatus.SKIPPED, reason="a predecessor did not succeed"), dispatched=False)
    log.failed(cause=MissionFailureCause.EXECUTION_FAILED, reason="failed: the model call failed (timeout): no answer")
    result = project(log.records)
    assert result.tokens_used == 0  # a failed call reports no tokens; none are invented (D-150)
    assert result.model_call_count == 1
    assert result.responses_missing_token_counts == 0  # the one call was a TIMEOUT, not an unmeasured RESPONSE
    assert result.skipped_count == 2


# --- timing fields preserve their own source semantics, never combined -----------------------------------------


def test_mission_wall_clock_ms_is_the_event_log_span_not_accumulated_node_time():
    log = verified_baseline()
    result = project(log.records)
    # 10 records, occurred_at = T0 + sequence seconds each (eidos_state_factories.make_record's own default): span is 9 seconds.
    assert result.mission_wall_clock_ms == 9000
    assert result.first_occurred_at == at(1)
    assert result.last_occurred_at == at(10)
    # Distinct from accumulated node duration (1200 + 3400 + 5 = 4605 ms) -- never combined (D-158 item 4).
    assert result.mission_wall_clock_ms != 1200 + 3400 + 5


def test_mission_wall_clock_ms_for_a_single_instant_log_is_zero():
    state, plan = baseline_state_and_plan()
    log = LogBuilder(state, plan)
    log.created()
    log.generated()
    log.rejected()
    log.failed(cause=MissionFailureCause.PLAN_REJECTED, reason="refused")
    result = project(log.records)
    assert result.mission_wall_clock_ms == (result.event_count - 1) * 1000  # sequence-derived, exactly as make_record produces it


def test_execution_time_used_ms_matches_execution_record_exactly():
    log = verified_baseline()
    result = project(log.records)
    record = execution_record(log.records)
    assert not isinstance(record, ReplayRejection)
    assert result.execution_time_used_ms == record.execution_time_used_ms


def test_execution_time_used_ms_can_exceed_mission_wall_clock_ms_for_a_parallel_topology():
    # "gather" and "analyse" are both roots (independent, no dependency edge between them) -- a genuinely
    # parallel topology, unlike verified_baseline()'s own linear gather -> analyse -> check chain. duration_ms
    # is a recorder-observed fact about each node's OWN dispatch, not derived from wall-clock event timing
    # (D-158 item 3), so two large, independently-recorded durations legitimately sum past the event-log span.
    state = make_mission(seed=2)
    plan = make_mission_plan(
        state, {"gather": "", "analyse": "", "check": "gather analyse"}, verify=("check",),
        capability_of={"gather": "research", "analyse": "cost"},
    )
    log = LogBuilder(state, plan)
    log.created()
    log.generated()
    log.compiled()
    log.started("gather")
    log.settled(work_result("gather"), duration_ms=6000, model_calls=(ModelCallFacts(outcome=ModelCallOutcome.RESPONSE, prompt_tokens=100, output_tokens=200, elapsed_seconds=1.0),))
    log.started("analyse")
    log.settled(work_result("analyse"), duration_ms=6000, model_calls=(ModelCallFacts(outcome=ModelCallOutcome.RESPONSE, prompt_tokens=100, output_tokens=200, elapsed_seconds=1.0),))
    log.started("check")
    log.settled(
        verify_result("check"), duration_ms=5,
        verification=VerificationFacts(verdict=VerificationVerdict.PASS, reason="the supported rules were satisfied"),
    )
    log.completed(verified=True)
    result = project(log.records)

    # 10 records, occurred_at = T0 + sequence seconds each: wall-clock span is 9 seconds regardless of duration_ms.
    assert result.mission_wall_clock_ms == 9000
    assert result.execution_time_used_ms == 6000 + 6000 + 5  # both nodes' own recorded durations, summed, never merged
    assert result.execution_time_used_ms > result.mission_wall_clock_ms
    assert result.succeeded_count == 3  # gather, analyse and check all succeeded despite the inflated durations


# --- purity: no mutation, no I/O -----------------------------------------------------------------------------


def test_project_does_not_mutate_its_input():
    log = verified_baseline()
    before = tuple(log.records)
    project(log.records)
    assert tuple(log.records) == before


def test_project_returns_the_same_typed_rejection_execution_record_gives_for_an_empty_log():
    result = project(())
    reference = execution_record(())
    assert isinstance(result, ReplayRejection)
    assert result == reference
