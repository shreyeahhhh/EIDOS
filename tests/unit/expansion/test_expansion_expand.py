"""``expand_strategy`` (decisions.md D-194, D-195; V0.9 Step 2)."""

import pytest
from pydantic import ValidationError

from eidos.compiler import compile_plan
from eidos.contracts import AgentStep, CapabilityId, ControlStep, PlanStepKind
from eidos.expansion import expand_strategy
from eidos.planning import Strategy, StrategyStage, VerificationPosture
from eidos.validation import SystemLimits, validate_plan

from eidos_expansion_factories import FixedPlanIdSource, make_plan_id
from eidos_mission_factories import make_mission
from eidos_planning_factories import GENEROUS_LIMITS, make_strategy, make_strategy_stage, strategy_with_stages


# --- empty strategy --------------------------------------------------------------------------------------------


def test_empty_strategy_produces_empty_plan():
    strategy = make_strategy(stages=(), verification=VerificationPosture.NONE)
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    assert plan.steps == ()


def test_final_with_empty_stages_creates_no_verify_step():
    # Rule 6: empty stages produce an empty Plan, regardless of verification posture.
    strategy = make_strategy(stages=(), verification=VerificationPosture.FINAL)
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    assert plan.steps == ()


# --- one stage, one capability ------------------------------------------------------------------------------------


def test_one_stage_one_capability():
    strategy = strategy_with_stages(1, ("research",), verification=VerificationPosture.NONE)
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert isinstance(step, AgentStep)
    assert step.capability == CapabilityId("research")
    assert step.depends_on == ()


# --- one stage, multiple capabilities: no dependency between them ---------------------------------------------


def test_one_stage_multiple_capabilities_have_no_dependencies_on_each_other():
    strategy = strategy_with_stages(1, ("research", "cost"), verification=VerificationPosture.NONE)
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    assert len(plan.steps) == 2
    for step in plan.steps:
        assert step.depends_on == ()
    capabilities = {step.capability for step in plan.steps}
    assert capabilities == {CapabilityId("research"), CapabilityId("cost")}


# --- multiple stages: full fan-out from the immediately preceding stage ----------------------------------------


def test_multiple_stages_fan_out_from_the_immediately_preceding_stage():
    strategy = strategy_with_stages(1, ("research",), ("cost", "security"), verification=VerificationPosture.NONE)
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    assert len(plan.steps) == 3
    root = next(s for s in plan.steps if s.capability == CapabilityId("research"))
    later = [s for s in plan.steps if s.capability != CapabilityId("research")]
    assert root.depends_on == ()
    assert len(later) == 2
    for step in later:
        assert step.depends_on == (root.step_id,)


# --- the two worked examples from V0.9 Step 1 -------------------------------------------------------------------


def test_worked_example_final_verification_with_uneven_stages():
    strategy = strategy_with_stages(
        1, ("research",), ("analysis", "writing"), verification=VerificationPosture.FINAL
    )
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())

    agent_steps = [s for s in plan.steps if isinstance(s, AgentStep)]
    control_steps = [s for s in plan.steps if isinstance(s, ControlStep)]
    assert len(agent_steps) == 3
    assert len(control_steps) == 1

    research = next(s for s in agent_steps if s.capability == CapabilityId("research"))
    analysis = next(s for s in agent_steps if s.capability == CapabilityId("analysis"))
    writing = next(s for s in agent_steps if s.capability == CapabilityId("writing"))
    verify = control_steps[0]

    assert research.depends_on == ()
    assert analysis.depends_on == (research.step_id,)
    assert writing.depends_on == (research.step_id,)
    assert verify.kind is PlanStepKind.VERIFY
    assert set(verify.depends_on) == {analysis.step_id, writing.step_id}
    assert len(verify.depends_on) == 2


def test_worked_example_none_verification_single_stage():
    strategy = strategy_with_stages(1, ("research", "analysis"), verification=VerificationPosture.NONE)
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    assert all(isinstance(s, AgentStep) for s in plan.steps)
    assert len(plan.steps) == 2
    for step in plan.steps:
        assert step.depends_on == ()


# --- FINAL vs NONE ------------------------------------------------------------------------------------------------


def test_final_creates_exactly_one_verify_step():
    strategy = strategy_with_stages(1, ("research",), verification=VerificationPosture.FINAL)
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    verify_steps = [s for s in plan.steps if isinstance(s, ControlStep)]
    assert len(verify_steps) == 1
    assert verify_steps[0].kind is PlanStepKind.VERIFY


def test_none_creates_no_verify_step():
    strategy = strategy_with_stages(1, ("research",), verification=VerificationPosture.NONE)
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    assert not any(isinstance(s, ControlStep) for s in plan.steps)


# --- duplicate capability occurrences: never deduplicated ----------------------------------------------------------


def test_duplicate_capability_occurrences_are_not_deduplicated():
    stage = StrategyStage(capabilities=(CapabilityId("research"), CapabilityId("research")))
    strategy = make_strategy(stages=(stage,), verification=VerificationPosture.NONE)
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    assert len(plan.steps) == 2
    assert plan.steps[0].capability == plan.steps[1].capability == CapabilityId("research")
    assert plan.steps[0].step_id != plan.steps[1].step_id  # distinct occurrences, distinct steps


def test_a_duplicate_occurrence_in_the_final_stage_gives_verify_two_distinct_predecessors():
    stage = StrategyStage(capabilities=(CapabilityId("research"), CapabilityId("research")))
    strategy = make_strategy(stages=(stage,), verification=VerificationPosture.FINAL)
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    verify = next(s for s in plan.steps if isinstance(s, ControlStep))
    agent_ids = {s.step_id for s in plan.steps if isinstance(s, AgentStep)}
    assert set(verify.depends_on) == agent_ids
    assert len(verify.depends_on) == 2


# --- PlanId: only from the injected source -----------------------------------------------------------------------


def test_plan_id_comes_only_from_the_injected_source():
    strategy = strategy_with_stages(1, ("research",))
    plan = expand_strategy(strategy, ids=FixedPlanIdSource(start=7))
    assert plan.plan_id == make_plan_id(7)


def test_plan_id_source_is_called_exactly_once_per_expansion():
    class CountingIds:
        def __init__(self):
            self.calls = 0

        def next_plan_id(self):
            self.calls += 1
            return make_plan_id(self.calls)

    ids = CountingIds()
    strategy = strategy_with_stages(1, ("research",))
    expand_strategy(strategy, ids=ids)
    assert ids.calls == 1


# --- step ids: deterministic, unique --------------------------------------------------------------------------


def test_step_ids_are_deterministic_across_repeated_calls():
    strategy = strategy_with_stages(1, ("research",), ("cost", "security"), verification=VerificationPosture.FINAL)
    first = expand_strategy(strategy, ids=FixedPlanIdSource())
    second = expand_strategy(strategy, ids=FixedPlanIdSource())
    assert [s.step_id for s in first.steps] == [s.step_id for s in second.steps]


def test_step_ids_are_unique_within_the_plan():
    strategy = strategy_with_stages(
        1, ("research", "research"), ("cost", "security", "cost"), verification=VerificationPosture.FINAL
    )
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    step_ids = [s.step_id for s in plan.steps]
    assert len(step_ids) == len(set(step_ids))


# --- identity propagation, lineage -----------------------------------------------------------------------------


def test_tenant_and_mission_id_are_propagated_from_strategy():
    strategy = strategy_with_stages(1, ("research",))
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    assert plan.tenant_id == strategy.tenant_id
    assert plan.mission_id == strategy.mission_id


def test_version_and_lineage_fields_are_always_fresh():
    strategy = strategy_with_stages(1, ("research",))
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    assert plan.version == 1
    assert plan.parent_plan_id is None
    assert plan.replan_reason is None


# --- VERIFY edges: exactly the final stage, never transitively earlier -----------------------------------------


def test_verify_depends_on_exactly_the_final_stage_step_ids_never_earlier_stages():
    strategy = strategy_with_stages(
        1, ("research",), ("cost",), ("security", "architecture"), verification=VerificationPosture.FINAL
    )
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    verify = next(s for s in plan.steps if isinstance(s, ControlStep))
    final_stage_ids = {
        s.step_id for s in plan.steps
        if isinstance(s, AgentStep) and s.capability in (CapabilityId("security"), CapabilityId("architecture"))
    }
    assert set(verify.depends_on) == final_stage_ids
    earlier_ids = {s.step_id for s in plan.steps if isinstance(s, AgentStep) and s.step_id not in final_stage_ids}
    assert not (set(verify.depends_on) & earlier_ids)


def test_capabilities_within_a_stage_never_depend_on_each_other():
    strategy = strategy_with_stages(1, ("research", "cost", "security"), verification=VerificationPosture.NONE)
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    step_ids = {s.step_id for s in plan.steps}
    for step in plan.steps:
        assert set(step.depends_on) & step_ids == set()  # depends_on names nothing in this same stage


# --- purity ----------------------------------------------------------------------------------------------------


def test_expand_strategy_does_not_mutate_the_strategy():
    strategy = strategy_with_stages(1, ("research",), ("cost",), verification=VerificationPosture.FINAL)
    before = strategy
    expand_strategy(strategy, ids=FixedPlanIdSource())
    assert strategy == before
    assert strategy.stages == before.stages


# --- invalid construction is Pydantic's job, not expand_strategy's ----------------------------------------------


def test_an_empty_stage_is_rejected_by_pydantic_before_expand_strategy_is_ever_called():
    with pytest.raises(ValidationError):
        StrategyStage(capabilities=())  # Field(min_length=1) — construction fails, expand_strategy never runs


# --- representative full V0.2 validation and V0.3 compilation ---------------------------------------------------


def test_representative_plan_passes_full_v02_validation():
    state = make_mission(capabilities=("research", "cost"))
    strategy = make_strategy(
        tenant_id=state.tenant_id,
        mission_id=state.mission_id,
        stages=(make_strategy_stage("research"), make_strategy_stage("cost")),
        verification=VerificationPosture.FINAL,
    )
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    report = validate_plan(plan, state, GENEROUS_LIMITS)
    assert report.accepted, report.violations


def test_representative_plan_compiles_under_v03():
    state = make_mission(capabilities=("research", "cost"))
    strategy = make_strategy(
        tenant_id=state.tenant_id,
        mission_id=state.mission_id,
        stages=(make_strategy_stage("research"), make_strategy_stage("cost")),
        verification=VerificationPosture.FINAL,
    )
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    report = validate_plan(plan, state, GENEROUS_LIMITS)
    assert report.accepted
    compiled = compile_plan(plan, report)
    assert compiled.succeeded, compiled.violations
    assert len(compiled.compiled.nodes) == len(plan.steps)
