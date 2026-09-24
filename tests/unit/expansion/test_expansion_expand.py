"""``expand_strategy`` (decisions.md D-194, D-195; V0.9 Step 2)."""

import re

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


def test_version_and_lineage_fields_default_to_fresh_plan_values():
    strategy = strategy_with_stages(1, ("research",))
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    assert plan.version == 1
    assert plan.parent_plan_id is None
    assert plan.replan_reason is None


# --- explicit lineage parameters (D-199, V1.1 Step 1): additive, every default preserved -------------------------


def test_explicit_version_is_stamped_onto_the_plan():
    strategy = strategy_with_stages(1, ("research",))
    plan = expand_strategy(strategy, ids=FixedPlanIdSource(), version=2)
    assert plan.version == 2
    assert plan.parent_plan_id is None
    assert plan.replan_reason is None


def test_explicit_parent_plan_id_is_stamped_onto_the_plan():
    strategy = strategy_with_stages(1, ("research",))
    parent = make_plan_id(1)
    plan = expand_strategy(strategy, ids=FixedPlanIdSource(start=2), parent_plan_id=parent)
    assert plan.parent_plan_id == parent
    assert plan.version == 1
    assert plan.replan_reason is None


def test_explicit_replan_reason_is_stamped_onto_the_plan():
    strategy = strategy_with_stages(1, ("research",))
    plan = expand_strategy(strategy, ids=FixedPlanIdSource(), replan_reason="execution_failed: the agent call failed")
    assert plan.replan_reason == "execution_failed: the agent call failed"
    assert plan.version == 1
    assert plan.parent_plan_id is None


def test_all_three_lineage_parameters_together_mirror_a_real_replan():
    strategy = strategy_with_stages(1, ("research",))
    parent = make_plan_id(1)
    plan = expand_strategy(
        strategy, ids=FixedPlanIdSource(start=2), version=2, parent_plan_id=parent,
        replan_reason="verification_failed: insufficient evidence",
    )
    assert plan.version == 2
    assert plan.parent_plan_id == parent
    assert plan.replan_reason == "verification_failed: insufficient evidence"
    assert plan.plan_id == make_plan_id(2)  # the id source is still the only source of plan_id itself


def test_lineage_parameters_are_independent_of_each_other_and_of_plan_id():
    # Setting one does not require or imply setting the others — expand_strategy stamps exactly what it is given.
    strategy = strategy_with_stages(1, ("research",))
    plan = expand_strategy(strategy, ids=FixedPlanIdSource(), version=3)
    assert plan.version == 3 and plan.parent_plan_id is None and plan.replan_reason is None


def test_lineage_parameters_never_change_the_plans_shape():
    # A replanned Plan's own steps depend only on the Strategy's own shape, exactly as a fresh Plan's do — same
    # step kinds, same capabilities, same dependency structure. Only the work-step *ids* differ (D-200, which
    # superseded this test's original "ids are identical" claim: D-147 requires fresh ids across plan versions);
    # `parent_plan_id`/`replan_reason` themselves never affect construction at all.
    strategy = strategy_with_stages(1, ("research",), ("cost",), verification=VerificationPosture.FINAL)
    fresh = expand_strategy(strategy, ids=FixedPlanIdSource())
    replanned = expand_strategy(
        strategy, ids=FixedPlanIdSource(), version=2, parent_plan_id=make_plan_id(99), replan_reason="execution_failed: x",
    )
    assert [type(s) for s in fresh.steps] == [type(s) for s in replanned.steps]
    assert [getattr(s, "capability", None) for s in fresh.steps] == [getattr(s, "capability", None) for s in replanned.steps]
    fresh_index = {s.step_id: n for n, s in enumerate(fresh.steps)}
    replanned_index = {s.step_id: n for n, s in enumerate(replanned.steps)}
    assert [tuple(fresh_index[d] for d in s.depends_on) for s in fresh.steps] == [
        tuple(replanned_index[d] for d in s.depends_on) for s in replanned.steps
    ]
    only_parent_and_reason = expand_strategy(
        strategy, ids=FixedPlanIdSource(), parent_plan_id=make_plan_id(99), replan_reason="execution_failed: x",
    )
    assert [s.step_id for s in only_parent_and_reason.steps] == [s.step_id for s in fresh.steps]


# --- work-step ids across plan versions (D-200, D-147): version 1 untouched, version > 1 namespaced --------------


_SHAPES = (
    strategy_with_stages(1, ("research",), verification=VerificationPosture.NONE),
    strategy_with_stages(1, ("research",), ("cost",), verification=VerificationPosture.FINAL),
    strategy_with_stages(1, ("research", "cost"), ("security",), verification=VerificationPosture.FINAL),
    strategy_with_stages(1, ("research", "research"), ("cost", "security", "cost"), ("architecture",), verification=VerificationPosture.FINAL),
)


def _work_ids(plan):
    return [s.step_id for s in plan.steps if isinstance(s, AgentStep)]


def _reference_pre_v11_ids(strategy):
    """The D-194 formula exactly as it stood before V1.1 — an independent re-statement, not a call into the code
    under test."""
    return [
        f"stage{stage_index}_{position}_{capability}"
        for stage_index, stage in enumerate(strategy.stages)
        for position, capability in enumerate(stage.capabilities)
    ]


def test_version_1_ids_are_the_d194_literals_byte_for_byte():
    strategy = strategy_with_stages(
        1, ("research",), ("cost", "security"), ("architecture",), verification=VerificationPosture.FINAL
    )
    plan = expand_strategy(strategy, ids=FixedPlanIdSource())
    assert [s.step_id for s in plan.steps] == [
        "stage0_0_research", "stage1_0_cost", "stage1_1_security", "stage2_0_architecture", "verify",
    ]


@pytest.mark.parametrize("strategy", _SHAPES)
def test_version_1_ids_equal_the_pre_v11_formula_for_every_shape(strategy):
    assert _work_ids(expand_strategy(strategy, ids=FixedPlanIdSource())) == _reference_pre_v11_ids(strategy)
    assert _work_ids(expand_strategy(strategy, ids=FixedPlanIdSource(), version=1)) == _reference_pre_v11_ids(strategy)


def test_version_1_plans_are_identical_with_and_without_the_explicit_version_argument():
    strategy = strategy_with_stages(1, ("research",), ("cost",), verification=VerificationPosture.FINAL)
    assert expand_strategy(strategy, ids=FixedPlanIdSource()) == expand_strategy(strategy, ids=FixedPlanIdSource(), version=1)


def test_version_2_ids_differ_from_version_1_ids():
    strategy = strategy_with_stages(1, ("research",), ("cost", "security"), verification=VerificationPosture.FINAL)
    v1 = _work_ids(expand_strategy(strategy, ids=FixedPlanIdSource()))
    v2 = _work_ids(expand_strategy(strategy, ids=FixedPlanIdSource(), version=2))
    assert v2 == ["v2_stage0_0_research", "v2_stage1_0_cost", "v2_stage1_1_security"]
    assert set(v1).isdisjoint(v2)


def test_version_3_ids_differ_from_both_version_1_and_version_2_ids():
    strategy = strategy_with_stages(1, ("research",), ("cost", "security"), verification=VerificationPosture.FINAL)
    v1, v2, v3 = (_work_ids(expand_strategy(strategy, ids=FixedPlanIdSource(), version=n)) for n in (1, 2, 3))
    assert v3 == ["v3_stage0_0_research", "v3_stage1_0_cost", "v3_stage1_1_security"]
    assert set(v3).isdisjoint(v1) and set(v3).isdisjoint(v2) and set(v1).isdisjoint(v2)


@pytest.mark.parametrize("version", [1, 2, 3, 10])
@pytest.mark.parametrize("strategy", _SHAPES)
def test_ids_are_deterministic_for_every_version(strategy, version):
    first = expand_strategy(strategy, ids=FixedPlanIdSource(), version=version)
    second = expand_strategy(strategy, ids=FixedPlanIdSource(), version=version)
    assert [s.step_id for s in first.steps] == [s.step_id for s in second.steps]


@pytest.mark.parametrize("version", [2, 3, 10])
@pytest.mark.parametrize("strategy", _SHAPES)
def test_versioned_ids_stay_structurally_derived_from_stage_position_and_capability(strategy, version):
    plan = expand_strategy(strategy, ids=FixedPlanIdSource(), version=version)
    # The version prefix wraps the unchanged D-194 id: stripping it recovers exactly the version-1 id.
    assert [str(i).removeprefix(f"v{version}_") for i in _work_ids(plan)] == _reference_pre_v11_ids(strategy)
    expected = [
        (stage_index, position, str(capability))
        for stage_index, stage in enumerate(strategy.stages)
        for position, capability in enumerate(stage.capabilities)
    ]
    parsed = [re.fullmatch(rf"v{version}_stage(\d+)_(\d+)_(.+)", str(i)) for i in _work_ids(plan)]
    assert all(parsed)
    assert [(int(m.group(1)), int(m.group(2)), m.group(3)) for m in parsed] == expected


@pytest.mark.parametrize("strategy", _SHAPES)
def test_no_work_step_id_collides_between_any_two_plan_versions(strategy):
    # Versions 1..12 deliberately include 2 vs 12 and 1 vs 11: the digits-only version is recovered uniquely
    # from the first underscore, so `v2_…` can never equal `v12_…`.
    per_version = {n: _work_ids(expand_strategy(strategy, ids=FixedPlanIdSource(), version=n)) for n in range(1, 13)}
    for a in per_version:
        for b in per_version:
            if a != b:
                assert set(per_version[a]).isdisjoint(per_version[b]), (a, b)
    everything = [i for ids in per_version.values() for i in ids]
    assert len(everything) == len(set(everything))


def test_a_versioned_plan_keeps_every_dependency_edge_inside_its_own_versions_ids():
    strategy = strategy_with_stages(1, ("research",), ("cost", "security"), verification=VerificationPosture.FINAL)
    plan = expand_strategy(strategy, ids=FixedPlanIdSource(), version=2)
    work = [s for s in plan.steps if isinstance(s, AgentStep)]
    verify = next(s for s in plan.steps if isinstance(s, ControlStep))
    assert work[0].depends_on == ()
    assert work[1].depends_on == (work[0].step_id,) and work[2].depends_on == (work[0].step_id,)
    assert set(verify.depends_on) == {work[1].step_id, work[2].step_id}
    assert all(str(i).startswith("v2_") for s in work for i in (s.step_id, *s.depends_on))


def test_the_verify_control_step_keeps_its_id_in_every_version():
    # `verify` stores no artifact and the intake's repeated-step guard is keyed by plan (D-162), so it needs no namespace.
    strategy = strategy_with_stages(1, ("research",), verification=VerificationPosture.FINAL)
    for version in (1, 2, 3):
        plan = expand_strategy(strategy, ids=FixedPlanIdSource(), version=version)
        assert next(s for s in plan.steps if isinstance(s, ControlStep)).step_id == "verify"


def test_a_version_2_plan_still_passes_full_validation_and_compiles():
    state = make_mission(capabilities=("research", "cost"))
    strategy = make_strategy(
        tenant_id=state.tenant_id, mission_id=state.mission_id,
        stages=(make_strategy_stage("research"), make_strategy_stage("cost")), verification=VerificationPosture.FINAL,
    )
    plan = expand_strategy(
        strategy, ids=FixedPlanIdSource(start=2), version=2, parent_plan_id=make_plan_id(1), replan_reason="execution_failed: x",
    )
    report = validate_plan(plan, state, GENEROUS_LIMITS)
    assert report.accepted, report.violations
    assert compile_plan(plan, report).succeeded


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
