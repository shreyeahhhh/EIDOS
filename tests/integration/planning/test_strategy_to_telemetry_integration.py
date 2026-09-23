"""The complete live composition, one real mission, start to finish (decisions.md D-183; V0.9 Step 3):

    TaskGenome/MissionState
      -> candidate generation (eidos.planning, RuleBasedCandidateGenerator)
      -> feasibility (eidos.planning.feasibility, inside generate_candidate_strategies)
      -> deterministic strategy selection (eidos.planning, DeterministicSelector + select_strategy)
      -> Strategy-to-Plan expansion (eidos.expansion.expand_strategy)
      -> the existing, unmodified full Plan validation (eidos.validation.validate_plan)
      -> the existing baseline execution/recording (eidos.recording.record_baseline, over real V0.4 agents)
      -> EventLog
      -> Telemetry projection (eidos.telemetry.project)

Every stage is the real, already-shipped implementation. The only things standing in for anything are the model
(a scripted response, D-136's own established substitution point — the model is the one thing this project never
calls for real in the default suite) and, for the recording layer only, the existing deterministic `FixedClock`/
`SequentialIds` test doubles (unrelated to what this step adds, and reused rather than duplicated). The two
sources this step actually adds — `UuidStrategyIds`, `UuidPlanIds` — are used for real: every `StrategyId` and
`PlanId` below is a genuine, randomly-drawn UUID, never one of the fixed sentinel values `FixedStrategyIdSource`/
`FixedPlanIdSource` produce in the rest of the suite.
"""

from eidos.agents import MeasuredFacts, ModelResponse
from eidos.contracts import MissionStatus, PlanStepKind
from eidos.expansion import expand_strategy
from eidos.planning import (
    DeterministicSelector,
    RuleBasedCandidateGenerator,
    SelectionOutcome,
    generate_candidate_strategies,
    select_strategy,
)
from eidos.recording import UuidPlanIds, UuidStrategyIds
from eidos.runtime import NodeStatus, RunResult
from eidos.telemetry import TelemetryRecord, project
from eidos.validation import validate_plan

from eidos_mission_factories import make_mission
from eidos_planning_factories import GENEROUS_LIMITS
from eidos_recording_factories import FixedClock, SequentialIds, record
from eidos_v04_registry import make_registry

# Fixed sentinel ranges FixedStrategyIdSource/FixedPlanIdSource draw from (eidos_planning_factories.make_strategy_id,
# eidos_expansion_factories.make_plan_id) — a real UUID from UuidStrategyIds/UuidPlanIds must never fall in either,
# proving these are genuine draws, not accidentally the fixed test doubles.
_FIXED_STRATEGY_ID_RANGE = range(900_001, 900_101)
_FIXED_PLAN_ID_RANGE = range(800_001, 800_101)


def _respond(request):
    # Cites only the supplied documents (doc:1..3), never a step-specific artifact ref: correct regardless of
    # which topology the selector picks, and satisfies citation_coverage/minimum_distinct_sources (contract
    # default min_independent_evidence=3) for both Research's and Analysis's own prompts alike.
    text = "Findings [[doc:1]] [[doc:2]] [[doc:3]]." if "Documents:" in request.prompt else "Analysis [[doc:1]] [[doc:2]] [[doc:3]]."
    return ModelResponse(text=text, measured=MeasuredFacts(prompt_tokens=100, output_tokens=200, elapsed_seconds=0.5))


def test_the_complete_composition_from_a_task_genome_to_a_projected_telemetry_record():
    # --- TaskGenome / MissionState -----------------------------------------------------------------------------
    state = make_mission(capabilities=("research", "cost", "security"))
    genome = state.task_genome

    # --- candidate generation + feasibility, with the real (not fixed) StrategyIdSource -----------------------
    generation = generate_candidate_strategies(
        RuleBasedCandidateGenerator(), genome, mission_id=state.mission_id, reliability_contract=state.reliability_contract,
        limits=GENEROUS_LIMITS, max_candidates=3, ids=UuidStrategyIds(),
    )
    assert len(generation.candidates) >= 2, "the selector must have more than one real candidate to choose between"
    for candidate in generation.candidates:
        assert candidate.strategy_id.int not in _FIXED_STRATEGY_ID_RANGE
    strategy_ids = {c.strategy_id for c in generation.candidates}
    assert len(strategy_ids) == len(generation.candidates)  # every draw is unique

    # --- deterministic strategy selection -----------------------------------------------------------------------
    selection = select_strategy(DeterministicSelector(), generation.candidates, genome)
    assert selection.outcome is SelectionOutcome.SELECTED
    selected = selection.selected
    assert selected in generation.candidates  # the exact object, never reconstructed (select_strategy's own guarantee)
    assert selected.tenant_id == state.tenant_id
    assert selected.mission_id == state.mission_id

    # --- Strategy-to-Plan expansion, with the real (not fixed) PlanIdSource --------------------------------------
    plan = expand_strategy(selected, ids=UuidPlanIds())
    assert plan.plan_id.int not in _FIXED_PLAN_ID_RANGE
    assert plan.tenant_id == state.tenant_id
    assert plan.mission_id == state.mission_id
    assert plan.version == 1 and plan.parent_plan_id is None

    # the selected Strategy is the one actually expanded: same capability multiset, same stage-by-stage shape
    expected_capabilities = [cap for stage in selected.stages for cap in stage.capabilities]
    agent_steps = [s for s in plan.steps if s.kind is PlanStepKind.AGENT]
    assert sorted(s.capability for s in agent_steps) == sorted(expected_capabilities)

    # expected stage topology is preserved: stage 0 is roots; each later stage depends on exactly the whole of the
    # one before it; a FINAL-verification VERIFY step (every rule-based shape allocates a capability, so
    # verification is always FINAL here) depends on exactly the final stage's own step ids.
    offset = 0
    previous_stage_ids: tuple = ()
    for stage in selected.stages:
        stage_steps = agent_steps[offset:offset + len(stage.capabilities)]
        for step in stage_steps:
            assert step.depends_on == previous_stage_ids
        previous_stage_ids = tuple(s.step_id for s in stage_steps)
        offset += len(stage.capabilities)
    verify_steps = [s for s in plan.steps if s.kind is PlanStepKind.VERIFY]
    assert len(verify_steps) == 1
    assert set(verify_steps[0].depends_on) == set(previous_stage_ids)

    # --- the expanded Plan passes the existing, unmodified full Plan validation ---------------------------------
    validation = validate_plan(plan, state, GENEROUS_LIMITS)
    assert validation.accepted, validation.violations

    # --- baseline execution, recorded, over real V0.4 agents and a scripted model --------------------------------
    run, _ = record(state, plan, respond=_respond, registry=make_registry(), limits=GENEROUS_LIMITS, clock=FixedClock(), ids=SequentialIds())
    assert run.refused == () and run.discrepancies == ()  # nothing hidden, nothing disagreed
    assert isinstance(run.report.run, RunResult)
    assert all(result.status is NodeStatus.SUCCEEDED for result in run.report.run.results)
    assert run.report.run.verified is True
    assert len(run.log.records) > 0

    # --- Telemetry projection ------------------------------------------------------------------------------------
    telemetry = project(run.log.records)
    assert isinstance(telemetry, TelemetryRecord)

    # telemetry identity corresponds to the executed mission/plan/execution
    assert telemetry.tenant_id == state.tenant_id
    assert telemetry.mission_id == state.mission_id
    assert telemetry.execution_id == state.execution_id
    assert telemetry.plan_id == plan.plan_id
    assert telemetry.plan_version == plan.version

    # telemetry facts match the real run: every agent step plus the VERIFY step succeeded, nothing else happened
    assert telemetry.mission_status is MissionStatus.COMPLETED
    assert telemetry.failure_cause is None
    assert telemetry.verified is True
    assert telemetry.succeeded_count == len(agent_steps) + 1  # every agent step, plus the one VERIFY step
    assert (telemetry.failed_count, telemetry.no_result_count, telemetry.verification_failed_count) == (0, 0, 0)
    assert telemetry.model_call_count == len(agent_steps)  # one model call per agent step, none for VERIFY
    assert telemetry.remote_task_count == 0  # no A2A task exists in this mission
    assert telemetry.agent_calls_used == len(agent_steps)


def test_each_run_of_the_same_genome_draws_fresh_unique_strategy_and_plan_ids():
    # A second, independent pass over an identical genome must never repeat an id: proves the real sources are
    # actually drawing fresh UUIDs each call, not memoizing or reusing anything.
    state = make_mission(capabilities=("research", "cost", "security"))
    genome = state.task_genome

    def one_pass():
        generation = generate_candidate_strategies(
            RuleBasedCandidateGenerator(), genome, mission_id=state.mission_id, reliability_contract=state.reliability_contract,
            limits=GENEROUS_LIMITS, max_candidates=3, ids=UuidStrategyIds(),
        )
        selection = select_strategy(DeterministicSelector(), generation.candidates, genome)
        plan = expand_strategy(selection.selected, ids=UuidPlanIds())
        return {c.strategy_id for c in generation.candidates}, plan.plan_id

    first_strategy_ids, first_plan_id = one_pass()
    second_strategy_ids, second_plan_id = one_pass()
    assert first_strategy_ids.isdisjoint(second_strategy_ids)
    assert first_plan_id != second_plan_id
