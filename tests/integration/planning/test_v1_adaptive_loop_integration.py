"""The complete V1.0 adaptive loop, two real missions, start to finish (decisions.md D-198; V1.0 Step 6):

    TaskGenome -> candidate generation -> feasibility -> experience-informed selection -> Strategy-to-Plan
    -> plan validation -> execution -> telemetry -> ExecutionExperience -> ExperienceStore -> future mission
    -> experience-informed selection

An integration proof, not a new architecture phase and not Benchmark 2 (V1.0 Step 7, not started): every stage
is the real, already-shipped implementation (``RuleBasedCandidateGenerator``, ``check_feasibility`` (inside
``generate_candidate_strategies``), ``ExperienceInformedSelector``, ``select_strategy``, ``expand_strategy``,
``validate_plan``, ``record_baseline`` over real V0.4 agents, ``project``, ``evaluate_experience``,
``JsonlExperienceStore``) — nothing here is a duplicate test implementation of any of them. The only things
standing in for anything are the model (a scripted response, D-136's own established substitution point) and the
recording layer's existing deterministic test doubles (``FixedClock``/``SequentialIds``), exactly as
``test_strategy_to_telemetry_integration.py`` (V0.9 Step 3) and the V1.0 Step 4 selector tests already use them.

**Mission 1 and Mission 2 are genuinely separate missions** (``make_mission(seed=1)``/``make_mission(seed=2)`` —
distinct tenant/mission/execution identity), not two runs of the same one: the whole point is that experience
carries across missions by *structure*, never by mission continuity or `StrategyId` (fresh every generation
round, D-182).

**Test A (the primary scenario)** uses the topology-driven, guard-based mechanism already approved for Benchmark
2 (D-198): a deterministic `AdmissionGuard` halts any shape that dispatches more than one node per level. A
two-capability `TaskGenome` yields exactly two candidates — linear (never halts) and parallel (always halts,
`DeterministicSelector`'s own known bias always prefers it). Mission 1 is a genuine cold start: the empty store
gives `ExperienceInformedSelector` nothing to work with, so it defers to its own injected fallback
(`DeterministicSelector`), which picks parallel — and parallel halts, a real non-success. Mission 2 sees that
history (matched by structure, under fresh `StrategyId`s) and picks linear instead — untested outranks proven
non-success (D-198's own tier ordering) — which genuinely succeeds.

**Test B (the inverse)** proves the mechanism is not accidentally coupled to "linear always wins": with a
*content*-based (citation) mechanism instead of the guard, linear is seeded with a proven verification failure
and the real selector, offered a fresh, untested parallel candidate alongside it, picks parallel — the same
tier-ordering rule, the opposite topology winning.
"""

from uuid import UUID

from eidos.agents import MeasuredFacts, ModelResponse
from eidos.contracts import MissionStatus, PlanStepKind
from eidos.expansion import expand_strategy
from eidos.memory import ExecutionExperience, JsonlExperienceStore, evaluate_experience
from eidos.planning import (
    DeterministicSelector,
    RuleBasedCandidateGenerator,
    SelectionOutcome,
    generate_candidate_strategies,
    select_strategy,
)
from eidos.recording import UuidPlanIds, UuidStrategyIds
from eidos.runtime import NodeStatus, RunOutcome
from eidos.selectors import ExperienceInformedSelector
from eidos.telemetry import TelemetryRecord, project
from eidos.validation import validate_plan

from eidos_mission_factories import make_mission
from eidos_planning_factories import GENEROUS_LIMITS
from eidos_recording_factories import FixedClock, SequentialIds, record
from eidos_runtime_factories import halt_when
from eidos_state_factories import T0
from eidos_v04_registry import make_registry

_CAPABILITIES = ("research", "cost")


def _uniformly_sufficient(request):
    # Every capability cites all three supplied documents — sufficient for min_independent_evidence=3 regardless
    # of which stage VERIFY ends up seeing (final-stage-only for linear, the whole stage for parallel).
    text = "Findings [[doc:1]] [[doc:2]] [[doc:3]]." if "Documents:" in request.prompt else "Analysis [[doc:1]] [[doc:2]] [[doc:3]]."
    return ModelResponse(text=text, measured=MeasuredFacts(prompt_tokens=100, output_tokens=200, elapsed_seconds=0.5))


def _final_stage_under_cited(request):
    # "cost" (the linear shape's own final stage for this genome's capability order) cites only one source;
    # "research" cites all three. Linear's own VERIFY sees only "cost" -> fails. Parallel's own VERIFY sees both
    # artifacts' citations -> the union already reaches three via "research" alone -> passes.
    if "Documents:" in request.prompt:  # research
        text = "Findings [[doc:1]] [[doc:2]] [[doc:3]]."
    else:  # cost (the only Analysis capability this genome uses)
        text = "Analysis [[doc:1]]."
    return ModelResponse(text=text, measured=MeasuredFacts(prompt_tokens=100, output_tokens=200, elapsed_seconds=0.5))


def _generate_and_select(state, selector, *, strategy_ids=None):
    genome = state.task_genome
    generation = generate_candidate_strategies(
        RuleBasedCandidateGenerator(), genome, mission_id=state.mission_id, reliability_contract=state.reliability_contract,
        limits=GENEROUS_LIMITS, max_candidates=3, ids=strategy_ids or UuidStrategyIds(),
    )
    assert len(generation.candidates) == 2, "a two-capability genome yields exactly linear and parallel"
    selection = select_strategy(selector, generation.candidates, genome)  # the one sanctioned selection boundary
    assert selection.outcome is SelectionOutcome.SELECTED, selection
    return generation, selection.selected


def _run_mission(state, strategy, *, respond, guard=None):
    plan = expand_strategy(strategy, ids=UuidPlanIds())
    validation = validate_plan(plan, state, GENEROUS_LIMITS)
    assert validation.accepted, validation.violations  # requirement 11: the Plan is actually validated
    recorded, _rig = record(
        state, plan, respond=respond, registry=make_registry(), guard=guard, limits=GENEROUS_LIMITS,
        clock=FixedClock(), ids=SequentialIds(),
    )
    assert recorded.refused == () and recorded.discrepancies == ()
    telemetry = project(recorded.log.records)
    assert isinstance(telemetry, TelemetryRecord)
    return plan, recorded, telemetry


def _shape_of(strategy):
    return tuple(stage.capabilities for stage in strategy.stages)


# --- Test A: the primary, guard-based two-mission scenario -----------------------------------------------------


def test_the_complete_adaptive_loop_across_two_real_missions(tmp_path):
    store_path = tmp_path / "experience.jsonl"
    concurrent_halt = lambda: halt_when(lambda request: request.rank_in_level >= 1, "V1.0 Step 6: no concurrent dispatch")

    # === Mission 1: a genuine cold start =========================================================================
    store_1 = JsonlExperienceStore.open(store_path)
    assert isinstance(store_1, JsonlExperienceStore)
    assert store_1.all() == ()  # requirement 1: the first mission starts with an empty store

    mission_1 = make_mission(capabilities=_CAPABILITIES, seed=1)
    selector_1 = ExperienceInformedSelector(store=store_1, fallback=DeterministicSelector())
    generation_1, selected_1 = _generate_and_select(mission_1, selector_1)
    # requirement 2: the cold-start choice matches DeterministicSelector's own known bias (fewest stages) exactly
    deterministic_choice = select_strategy(DeterministicSelector(), generation_1.candidates, mission_1.task_genome).selected
    assert selected_1 is deterministic_choice
    parallel_shape = _shape_of(selected_1)
    assert len(selected_1.stages) == 1  # confirms the cold-start pick really is the parallel (single-stage) shape

    plan_1, recorded_1, telemetry_1 = _run_mission(mission_1, selected_1, respond=_uniformly_sufficient, guard=concurrent_halt())
    # requirement 3: real, recorded facts — the guard genuinely halted the parallel shape before VERIFY
    assert telemetry_1.mission_status is MissionStatus.PAUSED
    assert telemetry_1.run_outcome is RunOutcome.HALTED
    assert telemetry_1.verified is not True
    assert any(result.status is NodeStatus.NOT_REACHED for result in recorded_1.report.run.results)

    experience_1 = evaluate_experience(selected_1, mission_1.task_genome, telemetry_1, recorded_at=T0)
    # requirement 4: built from the actual Strategy/TaskGenome/TelemetryRecord of this real mission
    assert experience_1.strategy_id == selected_1.strategy_id
    assert experience_1.strategy_stage_shapes == parallel_shape
    assert experience_1.mission_id == mission_1.mission_id and experience_1.execution_id == mission_1.execution_id
    assert experience_1.run_outcome is RunOutcome.HALTED and experience_1.verified is not True

    store_1.append(experience_1)  # requirement 5: the real ExperienceStore, not an in-memory selector shortcut
    assert store_1.all() == (experience_1,)

    # === Mission 2: a fresh mission, fresh StrategyIds, experience-informed ======================================
    mission_2 = make_mission(capabilities=_CAPABILITIES, seed=2)
    assert mission_2.mission_id != mission_1.mission_id and mission_2.execution_id != mission_1.execution_id

    store_2 = JsonlExperienceStore.open(store_path)  # reopened from disk, not the same Python object as store_1
    assert isinstance(store_2, JsonlExperienceStore)
    assert store_2.all() == (experience_1,)  # the first mission's own experience survived reopening

    selector_2 = ExperienceInformedSelector(store=store_2, fallback=DeterministicSelector())
    generation_2, selected_2 = _generate_and_select(mission_2, selector_2)

    # requirement 6: fresh StrategyIds this round
    mission_1_ids = {c.strategy_id for c in generation_1.candidates}
    mission_2_ids = {c.strategy_id for c in generation_2.candidates}
    assert mission_1_ids.isdisjoint(mission_2_ids)
    # requirement 7: structurally the same two candidates (same capability multiset, same topologies) either round
    assert {_shape_of(c) for c in generation_1.candidates} == {_shape_of(c) for c in generation_2.candidates}

    # requirement 8/9: the selector recognises mission 1's parallel-shaped failure despite the fresh id, and
    # switches to the untested linear shape instead of DeterministicSelector's own structural-cost bias
    fallback_choice = select_strategy(DeterministicSelector(), generation_2.candidates, mission_2.task_genome).selected
    assert _shape_of(fallback_choice) == parallel_shape  # the bias alone would still pick parallel
    assert _shape_of(selected_2) != parallel_shape  # experience overrides it
    assert len(selected_2.stages) == 2  # the linear shape (two single-capability stages)

    plan_2, recorded_2, telemetry_2 = _run_mission(mission_2, selected_2, respond=_uniformly_sufficient, guard=concurrent_halt())
    # requirement 10: the selected Strategy is the one actually expanded and executed
    expected_capabilities = sorted(cap for stage in selected_2.stages for cap in stage.capabilities)
    agent_steps = [s for s in plan_2.steps if s.kind is PlanStepKind.AGENT]
    assert sorted(s.capability for s in agent_steps) == expected_capabilities
    # requirement 12: real, new telemetry — linear never triggers the guard, and verifies successfully
    assert telemetry_2.run_outcome is RunOutcome.FINISHED
    assert telemetry_2.verified is True
    assert telemetry_2.mission_id == mission_2.mission_id

    experience_2 = evaluate_experience(selected_2, mission_2.task_genome, telemetry_2, recorded_at=T0)
    assert experience_2.strategy_id == selected_2.strategy_id
    assert experience_2.strategy_id != experience_1.strategy_id
    store_2.append(experience_2)

    # === Persistence (requirements 13/14) ========================================================================
    assert store_2.all() == (experience_1, experience_2)  # ordered, both missions
    store_3 = JsonlExperienceStore.open(store_path)  # a third, independent instance against the same file
    assert isinstance(store_3, JsonlExperienceStore)
    assert store_3.all() == (experience_1, experience_2)


# --- Test B: the inverse arrangement — parallel wins, not linear -----------------------------------------------


def test_the_inverse_arrangement_parallel_wins_when_linear_has_the_proven_failure(tmp_path):
    """Not accidentally coupled to "linear is always selected": here linear is seeded with a proven verification
    failure (content-based, no admission guard at all) and the real selector, offered a fresh, untested parallel
    candidate, picks parallel instead — the identical tier-ordering rule Test A exercises, the opposite winner.

    The seed step deliberately bypasses `ExperienceInformedSelector` — it exists only to build one real, honestly
    executed and recorded piece of history for the *linear* shape specifically (`DeterministicSelector`'s own
    bias would otherwise always pick parallel first, defeating the seed). Every later assertion is about the
    real selector's own behaviour, exactly as Test A's is.
    """
    store_path = tmp_path / "experience.jsonl"
    state = make_mission(capabilities=_CAPABILITIES, seed=1)

    generation = generate_candidate_strategies(
        RuleBasedCandidateGenerator(), state.task_genome, mission_id=state.mission_id,
        reliability_contract=state.reliability_contract, limits=GENEROUS_LIMITS, max_candidates=3, ids=UuidStrategyIds(),
    )
    linear = next(c for c in generation.candidates if len(c.stages) == 2)
    parallel_shape = next(_shape_of(c) for c in generation.candidates if len(c.stages) == 1)

    # Seed: force linear specifically (bypassing selection, labelled clearly — not the behaviour under test).
    _plan, _recorded, seed_telemetry = _run_mission(state, linear, respond=_final_stage_under_cited)
    assert seed_telemetry.run_outcome is RunOutcome.FAILED
    assert seed_telemetry.verified is not True
    seed_experience = evaluate_experience(linear, state.task_genome, seed_telemetry, recorded_at=T0)

    store = JsonlExperienceStore.open(store_path)
    assert isinstance(store, JsonlExperienceStore)
    store.append(seed_experience)

    # The real mission under test: fresh candidates, fresh StrategyIds, the real ExperienceInformedSelector.
    reopened = JsonlExperienceStore.open(store_path)
    assert isinstance(reopened, JsonlExperienceStore)
    selector = ExperienceInformedSelector(store=reopened, fallback=DeterministicSelector())
    _generation2, selected = _generate_and_select(state, selector)

    assert _shape_of(selected) == parallel_shape  # untested (parallel) outranks linear's proven non-success
    assert selected.strategy_id != linear.strategy_id  # a genuinely fresh candidate, never the seed's own id
