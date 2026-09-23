"""The first controlled EIDOS benchmark (the owner's final approval, 2026-09-23; decisions.md D-196 — the
benchmark itself stays unassigned a milestone number, exactly like MCP/RAG under D-184).

**A controlled engineering/reproducibility evaluation, not a statistically significant study** (CLAUDE.md §7;
the approval's own instruction: "describe this as a controlled engineering/reproducibility evaluation... do not
claim statistical significance"). Nothing here proves EIDOS is "superior" — every assertion below checks one
narrow, already-recorded fact (was a bad plan intercepted, did insufficient evidence fail verification instead
of reporting false success, did an injected failure produce the right cause, do two identical runs serialize
identically) against a small, hand-constructed, deterministic corpus.

**Conditions** (see ``eidos_benchmark_harness``'s own module docstring for the full architecture): A (Direct
Agent Baseline — bypasses Plan/validation/compiler/runtime/EventLog/Telemetry entirely), B (Fixed Workflow — a
hand-authored Plan through the existing, unmodified execution/recording/telemetry chain), C (LLM-Generated
Workflow — a model's Plan-DSL JSON through the existing, unmodified ``validate_plan_json`` ingress), D1 (EIDOS
Validated Strategy Execution with ``DeterministicSelector``), D2 (the same chain with ``ModelAssistedSelector``,
run only where >=2 candidates give it an actual choice — a selector comparison, never an adaptive-learning
experiment).

**Task classes** (CLAUDE.md §6 already scopes ``tests/scenarios/`` to exactly this kind of case): sequential
reasoning, parallel independent subtasks, verification-heavy, constrained/failure-prone, invalid-plan
interception. Each class carries only the failure sub-cases that make semantic sense for its own topology — see
each section's own docstring for which, and why not the rest.

Every case prints its own ``BenchmarkResult`` before asserting; ``pytest -s -v`` on this file is the benchmark's
own metric-vector report. Nothing is ever combined into one score, a ranking or a tier (D-188's own "never
weighted or combined into a single number," applied one layer up, per the approval's own instruction).
"""

from eidos.agents import MeasuredFacts, ModelFailure, ModelFailureKind, ModelResponse
from eidos.planning import DeterministicSelector
from eidos.runtime import RunOutcome
from eidos.selectors import ModelAssistedSelector
from eidos.state import MissionFailureCause, PlanRejectionStage
from eidos.contracts import MissionStatus

from eidos_agents_factories import doc, make_settings
from eidos_benchmark_harness import (
    BenchmarkResult,
    Capture,
    ScriptedPort,
    run_condition_a,
    run_condition_b,
    run_condition_c,
    run_condition_d,
)
from eidos_expansion_factories import FixedPlanIdSource
from eidos_mission_factories import make_mission, make_mission_plan
from eidos_planning_factories import FixedStrategyIdSource
from eidos_runtime_factories import halt_when
from eidos_validation_factories import make_system_limits

LIMITS = make_system_limits()


def _print(result: BenchmarkResult) -> None:
    print(
        f"[{result.condition:<2}] {result.task_class:<28} {result.case_id:<26} "
        f"dispatched={result.dispatched_anything!s:<5} status={str(result.mission_status):<10} "
        f"run_outcome={str(result.run_outcome):<9} verified={str(result.verified):<5} "
        f"failure_cause={str(result.failure_cause):<20} plan_rejected_at={str(result.plan_rejected_at):<11} "
        f"exec_ms={str(result.execution_time_used_ms):<5} wall_ms={str(result.mission_wall_clock_ms):<5} "
        f"cold_ms={'' if result.cold_path_ms is None else round(result.cold_path_ms, 2):<7} "
        f"hot_ms={'' if result.hot_path_ms is None else round(result.hot_path_ms, 2):<7} "
        f"model_calls={str(result.model_call_count):<4} selector_calls={str(result.selector_model_calls):<4} "
        f"tokens={str(result.tokens_used):<5} scripted={result.tokens_are_scripted}"
    )


# --- scripted responses, shared across task classes -----------------------------------------------------------


def _three_docs():
    return tuple(doc(f"doc:{n}", f"Source document {n}.") for n in (1, 2, 3))


def _good_response(request):
    text = "Findings [[doc:1]] [[doc:2]] [[doc:3]]." if "Documents:" in request.prompt else "Analysis [[doc:1]] [[doc:2]] [[doc:3]]."
    return ModelResponse(text=text, measured=MeasuredFacts(prompt_tokens=100, output_tokens=200, elapsed_seconds=0.5))


def _insufficient_evidence_response(request):
    # Cites one source only, against the fixture contract's min_independent_evidence=3 (eidos_factories.make_reliability_contract).
    text = "Findings [[doc:1]]." if "Documents:" in request.prompt else "Analysis [[doc:1]]."
    return ModelResponse(text=text, measured=MeasuredFacts(prompt_tokens=100, output_tokens=40, elapsed_seconds=0.2))


def _failing_response(request):
    return ModelFailure(kind=ModelFailureKind.UNAVAILABLE, message="benchmark: injected provider outage")


def _cost_fails_others_succeed(request):
    if "Analyse the cost" in request.prompt:
        return ModelFailure(kind=ModelFailureKind.UNAVAILABLE, message="benchmark: injected provider outage on cost")
    return _good_response(request)


def _selector_picks_candidate_1(request):
    # Fixed, reproducible answer — never random. Candidate 1 is the RuleBasedCandidateGenerator's own
    # generation-order-first shape (the linear one), which DeterministicSelector's own tie-break rule (D-188)
    # never picks once >=2 capabilities exist (it always resolves to the parallel/flattest shape) — so D1 and D2
    # are guaranteed to disagree here, which is exactly the comparison D2 exists to make.
    return ModelResponse(text="[[CANDIDATE_1]]", measured=MeasuredFacts(prompt_tokens=80, output_tokens=5, elapsed_seconds=0.1))


def _model_assisted_selector(capture: Capture) -> ModelAssistedSelector:
    return ModelAssistedSelector(model=ScriptedPort(capture.wrap(_selector_picks_candidate_1)), settings=make_settings())


# =================================================================================================================
# Task class 1 — Sequential reasoning (one capability: research; forces the linear shape for D)
# =================================================================================================================
# Cases: valid execution; agent/model failure; verification failure (insufficient evidence). No "invalid plan"
# here (that is class 5's own defining case) and no "parallel execution" (that is class 2's).


def _tc1_state():
    return make_mission(capabilities=("research",))


def _tc1_plan(state):
    return make_mission_plan(state, {"gather": "", "check": "gather"}, verify=("check",), capability_of={"gather": "research"})


def test_tc1_valid_execution():
    state = _tc1_state()
    plan = _tc1_plan(state)

    a = run_condition_a(task_class="sequential_reasoning", case_id="valid", genome=state.task_genome, contract=state.reliability_contract,
                         tenant_id=state.tenant_id, mission_id=state.mission_id, execution_id=state.execution_id,
                         capability="research", documents=_three_docs(), respond=_good_response)
    b = run_condition_b(task_class="sequential_reasoning", case_id="valid", state=state, plan=plan, limits=LIMITS, respond=_good_response)
    c = run_condition_c(task_class="sequential_reasoning", case_id="valid", state=state, plan_json=plan.model_dump_json(),
                         limits=LIMITS, respond=_good_response)
    d1 = run_condition_d(condition="D1", task_class="sequential_reasoning", case_id="valid", state=state,
                          selector=DeterministicSelector(), limits=LIMITS, max_candidates=3, respond=_good_response)
    for result in (a, b, c, d1):
        _print(result)

    assert a.dispatched_anything is True  # A has no verification: it "succeeds" whenever the model answers
    for result in (b, c, d1):
        assert result.dispatched_anything is True
        assert result.mission_status == MissionStatus.COMPLETED.value
        assert result.verified is True
        assert result.failure_cause is None
        assert result.plan_rejected_at is None

    # Cold path (candidate generation/feasibility/selection/expansion) is timed separately, and only exists for
    # D — B/C never run it, and A never runs any of this pipeline at all (Section 6 of the approval).
    assert d1.cold_path_ms is not None
    for result in (a, b, c):
        assert result.cold_path_ms is None
    for result in (a, b, c, d1):
        assert result.hot_path_ms is not None


def test_tc1_agent_model_failure():
    state = _tc1_state()
    plan = _tc1_plan(state)

    a = run_condition_a(task_class="sequential_reasoning", case_id="agent_failure", genome=state.task_genome, contract=state.reliability_contract,
                         tenant_id=state.tenant_id, mission_id=state.mission_id, execution_id=state.execution_id,
                         capability="research", documents=_three_docs(), respond=_failing_response)
    b = run_condition_b(task_class="sequential_reasoning", case_id="agent_failure", state=state, plan=plan, limits=LIMITS, respond=_failing_response)
    c = run_condition_c(task_class="sequential_reasoning", case_id="agent_failure", state=state, plan_json=plan.model_dump_json(),
                         limits=LIMITS, respond=_failing_response)
    d1 = run_condition_d(condition="D1", task_class="sequential_reasoning", case_id="agent_failure", state=state,
                          selector=DeterministicSelector(), limits=LIMITS, max_candidates=3, respond=_failing_response)
    for result in (a, b, c, d1):
        _print(result)

    assert a.dispatched_anything is True  # A has no failure classification beyond the raw WorkResult it returns
    for result in (b, c, d1):
        assert result.dispatched_anything is True
        assert result.mission_status == MissionStatus.FAILED.value
        assert result.failure_cause == MissionFailureCause.EXECUTION_FAILED.value
        assert result.verified is not True
        assert result.plan_rejected_at is None


def test_tc1_verification_failure_from_insufficient_evidence():
    state = _tc1_state()
    plan = _tc1_plan(state)

    a = run_condition_a(task_class="sequential_reasoning", case_id="insufficient_evidence", genome=state.task_genome,
                         contract=state.reliability_contract, tenant_id=state.tenant_id, mission_id=state.mission_id,
                         execution_id=state.execution_id, capability="research", documents=_three_docs(), respond=_insufficient_evidence_response)
    b = run_condition_b(task_class="sequential_reasoning", case_id="insufficient_evidence", state=state, plan=plan,
                         limits=LIMITS, respond=_insufficient_evidence_response)
    c = run_condition_c(task_class="sequential_reasoning", case_id="insufficient_evidence", state=state, plan_json=plan.model_dump_json(),
                         limits=LIMITS, respond=_insufficient_evidence_response)
    d1 = run_condition_d(condition="D1", task_class="sequential_reasoning", case_id="insufficient_evidence", state=state,
                          selector=DeterministicSelector(), limits=LIMITS, max_candidates=3, respond=_insufficient_evidence_response)
    for result in (a, b, c, d1):
        _print(result)

    # The central false-success finding: A reports "produced" with no verification concept at all — it cannot
    # distinguish this from test_tc1_valid_execution's own good case. B/C/D1 all correctly refuse to call this a
    # success: a VERIFY node that FAILs is itself not SUCCEEDED, so the whole run is FAILED (not FINISHED) —
    # the mission never reaches MISSION_COMPLETED at all, and carries the precise, distinct
    # VERIFICATION_FAILED cause rather than a bare "did not verify" footnote.
    assert a.dispatched_anything is True
    for result in (b, c, d1):
        assert result.dispatched_anything is True
        assert result.mission_status == MissionStatus.FAILED.value
        assert result.failure_cause == MissionFailureCause.VERIFICATION_FAILED.value
        assert result.verified is not True  # never a false success
        assert result.plan_rejected_at is None


# =================================================================================================================
# Task class 2 — Parallel independent subtasks (research, cost, security in one stage)
# =================================================================================================================
# Cases: valid execution; a failure on one of the parallel branches while the others succeed. Condition A does
# not apply here: a direct single-agent call has no way to represent a multi-branch task at all (its own
# limitation is the finding, not a case to force).


def _tc2_state():
    return make_mission(capabilities=("research", "cost", "security"))


def _tc2_plan(state):
    return make_mission_plan(
        state, {"gather": "", "cost": "", "security": "", "check": "gather cost security"},
        verify=("check",), capability_of={"gather": "research", "cost": "cost", "security": "security"},
    )


def test_tc2_valid_parallel_execution():
    state = _tc2_state()
    plan = _tc2_plan(state)
    capture = Capture()

    b = run_condition_b(task_class="parallel_independent_subtasks", case_id="valid", state=state, plan=plan, limits=LIMITS, respond=_good_response)
    c = run_condition_c(task_class="parallel_independent_subtasks", case_id="valid", state=state, plan_json=plan.model_dump_json(),
                         limits=LIMITS, respond=_good_response)
    d1 = run_condition_d(condition="D1", task_class="parallel_independent_subtasks", case_id="valid", state=state,
                          selector=DeterministicSelector(), limits=LIMITS, max_candidates=3, respond=_good_response)
    d2 = run_condition_d(condition="D2", task_class="parallel_independent_subtasks", case_id="valid", state=state,
                          selector=_model_assisted_selector(capture), limits=LIMITS, max_candidates=3, respond=_good_response,
                          selector_capture=capture)
    for result in (b, c, d1, d2):
        _print(result)
        assert result.dispatched_anything is True
        assert result.mission_status == MissionStatus.COMPLETED.value
        assert result.verified is True
        assert result.failure_cause is None

    assert d2.selector_model_calls == 1  # the cold-path selector call: never visible to TelemetryRecord


def test_tc2_one_branch_fails_others_succeed():
    state = _tc2_state()
    plan = _tc2_plan(state)
    capture = Capture()

    b = run_condition_b(task_class="parallel_independent_subtasks", case_id="one_branch_fails", state=state, plan=plan,
                         limits=LIMITS, respond=_cost_fails_others_succeed)
    c = run_condition_c(task_class="parallel_independent_subtasks", case_id="one_branch_fails", state=state, plan_json=plan.model_dump_json(),
                         limits=LIMITS, respond=_cost_fails_others_succeed)
    d1 = run_condition_d(condition="D1", task_class="parallel_independent_subtasks", case_id="one_branch_fails", state=state,
                          selector=DeterministicSelector(), limits=LIMITS, max_candidates=3, respond=_cost_fails_others_succeed)
    d2 = run_condition_d(condition="D2", task_class="parallel_independent_subtasks", case_id="one_branch_fails", state=state,
                          selector=_model_assisted_selector(capture), limits=LIMITS, max_candidates=3, respond=_cost_fails_others_succeed,
                          selector_capture=capture)
    for result in (b, c, d1, d2):
        _print(result)
        assert result.dispatched_anything is True
        assert result.mission_status == MissionStatus.FAILED.value
        assert result.failure_cause == MissionFailureCause.EXECUTION_FAILED.value
        # VERIFY depends on all three branches; one failed predecessor means VERIFY is never dispatched at all.
        assert result.verified is not True


# =================================================================================================================
# Task class 3 — Verification-heavy (single capability, focused purely on the verify gate)
# =================================================================================================================
# Cases: valid execution (passes verification); missing/insufficient evidence (the class's own defining case).
# No "agent failure"/"constraint violation" here — those belong to class 4, which is about execution-layer
# failure, not verification content.


def _tc3_state():
    return make_mission(capabilities=("research",))


def _tc3_plan(state):
    return make_mission_plan(state, {"gather": "", "check": "gather"}, verify=("check",), capability_of={"gather": "research"})


def test_tc3_valid_execution_passes_verification():
    state = _tc3_state()
    plan = _tc3_plan(state)

    a = run_condition_a(task_class="verification_heavy", case_id="valid", genome=state.task_genome, contract=state.reliability_contract,
                         tenant_id=state.tenant_id, mission_id=state.mission_id, execution_id=state.execution_id,
                         capability="research", documents=_three_docs(), respond=_good_response)
    b = run_condition_b(task_class="verification_heavy", case_id="valid", state=state, plan=plan, limits=LIMITS, respond=_good_response)
    c = run_condition_c(task_class="verification_heavy", case_id="valid", state=state, plan_json=plan.model_dump_json(),
                         limits=LIMITS, respond=_good_response)
    d1 = run_condition_d(condition="D1", task_class="verification_heavy", case_id="valid", state=state,
                          selector=DeterministicSelector(), limits=LIMITS, max_candidates=3, respond=_good_response)
    for result in (a, b, c, d1):
        _print(result)

    assert a.dispatched_anything is True
    for result in (b, c, d1):
        assert result.mission_status == MissionStatus.COMPLETED.value
        assert result.verified is True


def test_tc3_insufficient_evidence_fails_verification_not_false_success():
    state = _tc3_state()
    plan = _tc3_plan(state)

    a = run_condition_a(task_class="verification_heavy", case_id="insufficient_evidence", genome=state.task_genome,
                         contract=state.reliability_contract, tenant_id=state.tenant_id, mission_id=state.mission_id,
                         execution_id=state.execution_id, capability="research", documents=_three_docs(), respond=_insufficient_evidence_response)
    b = run_condition_b(task_class="verification_heavy", case_id="insufficient_evidence", state=state, plan=plan,
                         limits=LIMITS, respond=_insufficient_evidence_response)
    c = run_condition_c(task_class="verification_heavy", case_id="insufficient_evidence", state=state, plan_json=plan.model_dump_json(),
                         limits=LIMITS, respond=_insufficient_evidence_response)
    d1 = run_condition_d(condition="D1", task_class="verification_heavy", case_id="insufficient_evidence", state=state,
                          selector=DeterministicSelector(), limits=LIMITS, max_candidates=3, respond=_insufficient_evidence_response)
    for result in (a, b, c, d1):
        _print(result)

    # A has no verification concept: it reports a produced artifact regardless of how thin the evidence is.
    assert a.dispatched_anything is True
    for result in (b, c, d1):
        assert result.mission_status == MissionStatus.FAILED.value
        assert result.failure_cause == MissionFailureCause.VERIFICATION_FAILED.value
        assert result.verified is not True


# =================================================================================================================
# Task class 4 — Constrained/failure-prone (single capability, execution-layer failure)
# =================================================================================================================
# Cases: agent/model failure; constraint violation (a deterministic AdmissionGuard halting the run). Condition A
# has agent/model failure (it can still call one agent and receive a ModelFailure) but no constraint-violation
# case: there is no AdmissionGuard, no runtime, nothing to halt.


def _tc4_state():
    return make_mission(capabilities=("research",))


def _tc4_plan(state):
    return make_mission_plan(state, {"gather": "", "check": "gather"}, verify=("check",), capability_of={"gather": "research"})


def test_tc4_agent_model_failure():
    state = _tc4_state()
    plan = _tc4_plan(state)

    a = run_condition_a(task_class="constrained_failure_prone", case_id="agent_failure", genome=state.task_genome,
                         contract=state.reliability_contract, tenant_id=state.tenant_id, mission_id=state.mission_id,
                         execution_id=state.execution_id, capability="research", documents=_three_docs(), respond=_failing_response)
    b = run_condition_b(task_class="constrained_failure_prone", case_id="agent_failure", state=state, plan=plan, limits=LIMITS, respond=_failing_response)
    c = run_condition_c(task_class="constrained_failure_prone", case_id="agent_failure", state=state, plan_json=plan.model_dump_json(),
                         limits=LIMITS, respond=_failing_response)
    d1 = run_condition_d(condition="D1", task_class="constrained_failure_prone", case_id="agent_failure", state=state,
                          selector=DeterministicSelector(), limits=LIMITS, max_candidates=3, respond=_failing_response)
    for result in (a, b, c, d1):
        _print(result)

    assert a.dispatched_anything is True
    for result in (b, c, d1):
        assert result.mission_status == MissionStatus.FAILED.value
        assert result.failure_cause == MissionFailureCause.EXECUTION_FAILED.value


def test_tc4_constraint_violation_halts_the_run():
    state = _tc4_state()
    plan = _tc4_plan(state)
    guard = halt_when(lambda request: True, "benchmark: constraint violation")

    b = run_condition_b(task_class="constrained_failure_prone", case_id="constraint_violation", state=state, plan=plan,
                         limits=LIMITS, respond=_good_response, guard=guard)
    c = run_condition_c(task_class="constrained_failure_prone", case_id="constraint_violation", state=state, plan_json=plan.model_dump_json(),
                         limits=LIMITS, respond=_good_response, guard=halt_when(lambda request: True, "benchmark: constraint violation"))
    d1 = run_condition_d(condition="D1", task_class="constrained_failure_prone", case_id="constraint_violation", state=state,
                          selector=DeterministicSelector(), limits=LIMITS, max_candidates=3, respond=_good_response,
                          guard=halt_when(lambda request: True, "benchmark: constraint violation"))
    for result in (b, c, d1):
        _print(result)
        assert result.dispatched_anything is False  # the guard halts before the one node is ever dispatched
        assert result.mission_status == MissionStatus.PAUSED.value
        assert result.run_outcome == RunOutcome.HALTED.value
        assert result.verified is None
        assert result.model_call_count == 0  # nothing was ever dispatched, so no model call was ever made


# =================================================================================================================
# Task class 5 — Invalid-plan interception (B and C only; D always produces a valid Plan by construction)
# =================================================================================================================
# Cases: a valid plan (the companion sanity case, proving the same mechanism accepts good input); an invalid
# plan requesting a capability the mission never declared; for C only, a syntactically malformed JSON document
# (the ingress-specific case B cannot even express, since B never starts from untrusted text). Condition A does
# not apply: there is no Plan concept to be invalid. Condition D does not apply: expand_strategy only ever
# produces a Plan that validate_plan already accepts (D-183) — D structurally cannot exercise this class, which
# is itself a reportable finding, not a gap.


def _tc5_state():
    return make_mission(capabilities=("research",))


def test_tc5_valid_plan_is_accepted():
    state = _tc5_state()
    plan = make_mission_plan(state, {"gather": "", "check": "gather"}, verify=("check",), capability_of={"gather": "research"})

    b = run_condition_b(task_class="invalid_plan_interception", case_id="valid_plan", state=state, plan=plan, limits=LIMITS, respond=_good_response)
    c = run_condition_c(task_class="invalid_plan_interception", case_id="valid_plan", state=state, plan_json=plan.model_dump_json(),
                         limits=LIMITS, respond=_good_response)
    for result in (b, c):
        _print(result)
        assert result.dispatched_anything is True
        assert result.plan_rejected_at is None


def test_tc5_plan_requesting_an_undeclared_capability_is_intercepted():
    state = _tc5_state()  # declares only "research"
    plan = make_mission_plan(state, {"gather": "", "check": "gather"}, verify=("check",), capability_of={"gather": "security"})

    b = run_condition_b(task_class="invalid_plan_interception", case_id="undeclared_capability", state=state, plan=plan,
                         limits=LIMITS, respond=_good_response)
    c = run_condition_c(task_class="invalid_plan_interception", case_id="undeclared_capability", state=state, plan_json=plan.model_dump_json(),
                         limits=LIMITS, respond=_good_response)
    for result in (b, c):
        _print(result)
        assert result.dispatched_anything is False  # intercepted before anything ran
        assert result.plan_rejected_at == PlanRejectionStage.VALIDATION.value
        assert result.mission_status is None or result.mission_status == MissionStatus.FAILED.value


def test_tc5_malformed_json_is_intercepted_at_the_untrusted_ingress():
    state = _tc5_state()
    broken_json = '{"tenant_id": "not-real", this-is-not-valid-json'

    c = run_condition_c(task_class="invalid_plan_interception", case_id="malformed_json", state=state, plan_json=broken_json,
                         limits=LIMITS, respond=_good_response)
    _print(c)
    assert c.dispatched_anything is False
    assert c.plan_rejected_at == PlanRejectionStage.VALIDATION.value


# =================================================================================================================
# Reproducibility — repeated deterministic executions must serialize identically (Section 8 of the approval)
# =================================================================================================================


def test_reproducibility_repeated_deterministic_runs_produce_identical_digests():
    """Mirrors tests/scenarios/test_v03_determinism.py's own hash-of-serialized-output technique, applied to
    this benchmark's own conditions: two independent runs of the identical condition+case, same scripted
    inputs, must serialize byte-identically. Never claims statistical significance — this proves determinism,
    not variance."""
    cases = []

    state = _tc1_state()
    plan = _tc1_plan(state)
    cases.append(("B/sequential/valid", lambda: run_condition_b(
        task_class="reproducibility", case_id="B_sequential_valid", state=state, plan=plan, limits=LIMITS, respond=_good_response)))
    cases.append(("C/sequential/valid", lambda: run_condition_c(
        task_class="reproducibility", case_id="C_sequential_valid", state=state, plan_json=plan.model_dump_json(),
        limits=LIMITS, respond=_good_response)))
    # D1/D2 draw genuinely fresh strategy_id/plan_id per call by design (proven in
    # tests/integration/planning/test_strategy_to_telemetry_integration.py's own
    # test_each_run_of_the_same_genome_draws_fresh_unique_strategy_and_plan_ids) — a fresh id differing between
    # two runs is not a reproducibility failure, so this case fixes both id sources to isolate the property
    # actually under test: everything ELSE about the outcome is byte-identical across repeats.
    cases.append(("D1/sequential/valid", lambda: run_condition_d(
        condition="D1", task_class="reproducibility", case_id="D1_sequential_valid", state=state,
        selector=DeterministicSelector(), limits=LIMITS, max_candidates=3, respond=_good_response,
        strategy_ids=FixedStrategyIdSource(), plan_ids=FixedPlanIdSource())))

    parallel_state = _tc2_state()
    parallel_plan = _tc2_plan(parallel_state)
    cases.append(("B/parallel/valid", lambda: run_condition_b(
        task_class="reproducibility", case_id="B_parallel_valid", state=parallel_state, plan=parallel_plan, limits=LIMITS, respond=_good_response)))

    for label, run in cases:
        first = run()
        second = run()
        _print(first)
        assert first.digest == second.digest, f"{label}: digests diverged across two identical runs"
        assert first.digest != "", f"{label}: digest was never computed"
