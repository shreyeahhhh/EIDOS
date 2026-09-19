"""The individual validation stages (decisions.md D-004, D-009, D-050, D-102, D-104, D-105, D-106, D-110)."""

from uuid import uuid4

import pytest

from eidos.contracts import CapabilityId, MissionId, PlanStepKind, StepId, TenantId
from eidos.validation.limits import MISSION_BUDGETS, LimitName
from eidos.validation.results import (
    StageStatus,
    ValidationStage,
    ViolationCode,
)
from eidos.validation.stages import (
    check_capabilities,
    check_complexity,
    check_cycles,
    check_policy,
    check_resources,
    identity_violations,
)

from eidos_factories import (
    make_agent_step,
    make_control_step,
    make_plan,
    make_reliability_contract,
)
from eidos_validation_factories import make_system_limits


def plan_of(spec: dict[str, str], **plan_overrides):
    """A plan of agent steps from ``{"name": "dep1 dep2"}``, in dict order."""
    steps = tuple(
        make_agent_step(step_id=StepId(name), depends_on=tuple(StepId(d) for d in deps.split()))
        for name, deps in spec.items()
    )
    return make_plan(steps=steps, **plan_overrides)


def agent_steps(n: int):
    return make_plan(steps=tuple(make_agent_step(step_id=StepId(f"a{i}")) for i in range(n)))


# --- identity binding ------------------------------------------------------


def test_matching_identity_has_no_violations():
    plan = make_plan()
    assert identity_violations(plan, mission_id=plan.mission_id, tenant_id=plan.tenant_id) == ()


def test_mission_mismatch_is_reported_under_schema():
    plan = make_plan()
    (violation,) = identity_violations(
        plan, mission_id=MissionId(uuid4()), tenant_id=plan.tenant_id
    )
    assert violation.code is ViolationCode.PLAN_MISSION_MISMATCH
    assert violation.stage is ValidationStage.SCHEMA


def test_tenant_mismatch_is_reported_under_schema():
    plan = make_plan()
    (violation,) = identity_violations(
        plan, mission_id=plan.mission_id, tenant_id=TenantId(uuid4())
    )
    assert violation.code is ViolationCode.PLAN_TENANT_MISMATCH


def test_both_mismatches_are_reported_mission_first():
    plan = make_plan()
    violations = identity_violations(
        plan, mission_id=MissionId(uuid4()), tenant_id=TenantId(uuid4())
    )
    assert [v.code for v in violations] == [
        ViolationCode.PLAN_MISSION_MISMATCH,
        ViolationCode.PLAN_TENANT_MISMATCH,
    ]


# --- CYCLE -----------------------------------------------------------------


def test_an_acyclic_plan_passes_the_cycle_stage():
    result = check_cycles(plan_of({"a": "", "b": "a", "c": "a b"}))
    assert result.status is StageStatus.PASSED
    assert result.stage is ValidationStage.CYCLE


def test_an_empty_plan_passes_the_cycle_stage():
    assert check_cycles(make_plan(steps=())).status is StageStatus.PASSED


def test_the_v01_self_dependency_plan_is_rejected_here():
    # test_self_dependency_is_not_rejected_in_v01 pins that V0.1 *accepts* this
    # plan; the V0.2 cycle stage is where it is rejected.
    plan = plan_of({"s1": "s1"})
    result = check_cycles(plan)
    assert result.status is StageStatus.FAILED
    (violation,) = result.violations
    assert violation.code is ViolationCode.CYCLE_DETECTED
    assert violation.step_ids == ("s1",)
    assert "depends on itself" in violation.message


def test_a_two_step_cycle_names_both_steps():
    result = check_cycles(plan_of({"a": "b", "b": "a"}))
    (violation,) = result.violations
    assert violation.step_ids == ("a", "b")
    assert "form a dependency cycle" in violation.message


def test_every_disjoint_cycle_is_reported_in_plan_order():
    plan = plan_of({"a": "b", "b": "a", "fine": "", "c": "d", "d": "c", "s": "s"})
    result = check_cycles(plan)
    assert [v.step_ids for v in result.violations] == [("a", "b"), ("c", "d"), ("s",)]


def test_steps_downstream_of_a_cycle_are_not_named_as_members():
    result = check_cycles(plan_of({"a": "b", "b": "a", "tail": "a"}))
    (violation,) = result.violations
    assert "tail" not in violation.step_ids


def test_cycle_stage_ignores_step_kind():
    plan = make_plan(
        steps=(
            make_control_step(step_id=StepId("r"), depends_on=(StepId("a"),), kind=PlanStepKind.ROUTE),
            make_agent_step(step_id=StepId("a"), depends_on=(StepId("r"),)),
        )
    )
    assert check_cycles(plan).status is StageStatus.FAILED


# --- CAPABILITY (D-102) ----------------------------------------------------


def _agent(step_id: str, capability: str):
    return make_agent_step(step_id=StepId(step_id), capability=CapabilityId(capability))


def caps(*names: str) -> tuple[CapabilityId, ...]:
    return tuple(CapabilityId(n) for n in names)


def test_an_exactly_matching_capability_passes():
    plan = make_plan(steps=(_agent("s1", "research"),))
    assert check_capabilities(plan, required_capabilities=caps("research")).status is StageStatus.PASSED


def test_a_capability_absent_from_required_fails_and_names_the_step():
    plan = make_plan(steps=(_agent("s1", "research"), _agent("s2", "analysis")))
    result = check_capabilities(plan, required_capabilities=caps("research"))
    assert result.status is StageStatus.FAILED
    (violation,) = result.violations
    assert violation.code is ViolationCode.CAPABILITY_NOT_REQUIRED
    assert violation.step_ids == ("s2",)
    assert violation.capability == "analysis"


@pytest.mark.parametrize("variant", ["Research", "RESEARCH", "research ", " research", "research\n", "resea rch"])
def test_matching_is_exact_string_no_case_folding_or_trimming(variant):
    plan = make_plan(steps=(_agent("s1", variant),))
    result = check_capabilities(plan, required_capabilities=caps("research"))
    assert result.status is StageStatus.FAILED
    assert result.violations[0].capability == variant


def test_every_offending_step_is_reported_once_in_plan_order():
    plan = make_plan(steps=(_agent("z", "bad"), _agent("ok", "research"), _agent("a", "bad")))
    result = check_capabilities(plan, required_capabilities=caps("research"))
    assert [v.step_ids for v in result.violations] == [("z",), ("a",)]


def test_empty_required_capabilities_fail_every_agent_step():
    plan = make_plan(steps=(_agent("s1", "research"), _agent("s2", "research")))
    result = check_capabilities(plan, required_capabilities=())
    assert [v.step_ids for v in result.violations] == [("s1",), ("s2",)]


def test_empty_required_capabilities_with_no_agent_steps_passes():
    plan = make_plan(steps=(make_control_step(step_id=StepId("v")),))
    assert check_capabilities(plan, required_capabilities=()).status is StageStatus.PASSED
    assert check_capabilities(make_plan(steps=()), required_capabilities=()).status is StageStatus.PASSED


def test_a_required_capability_with_no_step_using_it_passes():
    # D-102: the converse is not required.
    plan = make_plan(steps=(_agent("s1", "research"),))
    result = check_capabilities(plan, required_capabilities=caps("research", "analysis", "verification"))
    assert result.status is StageStatus.PASSED


def test_control_steps_are_never_capability_checked():
    plan = make_plan(
        steps=tuple(
            make_control_step(step_id=StepId(kind.value), kind=kind)
            for kind in PlanStepKind
            if kind is not PlanStepKind.AGENT
        )
    )
    assert check_capabilities(plan, required_capabilities=()).status is StageStatus.PASSED


def test_duplicate_required_capabilities_are_harmless():
    plan = make_plan(steps=(_agent("s1", "research"),))
    result = check_capabilities(plan, required_capabilities=caps("research", "research"))
    assert result.status is StageStatus.PASSED


# --- POLICY (D-110) --------------------------------------------------------


def test_policy_is_not_applicable_and_explains_why():
    result = check_policy()
    assert result.stage is ValidationStage.POLICY
    assert result.status is StageStatus.NOT_APPLICABLE
    assert result.violations == ()
    assert "D-110" in result.detail
    assert "did not approve" in result.detail


def test_policy_never_reports_passed():
    assert check_policy().status is not StageStatus.PASSED


# --- RESOURCE (D-009, D-065, D-105) ----------------------------------------


def test_a_contract_with_no_budgets_passes():
    result = check_resources(
        agent_steps(3), contract=make_reliability_contract(), limits=make_system_limits()
    )
    assert result.status is StageStatus.PASSED


@pytest.mark.parametrize("budget", MISSION_BUDGETS)
def test_a_contract_value_equal_to_the_ceiling_passes(budget):
    limits = make_system_limits()
    contract = make_reliability_contract(**{budget.value: limits.ceiling(budget)})
    assert check_resources(make_plan(steps=()), contract=contract, limits=limits).status is StageStatus.PASSED


@pytest.mark.parametrize("budget", MISSION_BUDGETS)
def test_a_contract_value_one_over_the_ceiling_is_rejected_not_clamped(budget):
    limits = make_system_limits()
    ceiling = limits.ceiling(budget)
    contract = make_reliability_contract(**{budget.value: ceiling + 1})
    result = check_resources(make_plan(steps=()), contract=contract, limits=limits)
    assert result.status is StageStatus.FAILED
    (violation,) = result.violations
    assert violation.code is ViolationCode.CONTRACT_EXCEEDS_CEILING
    assert violation.limit_name is budget
    assert (violation.limit_value, violation.observed_value) == (ceiling, ceiling + 1)
    assert "rejected, not clamped" in violation.message
    assert getattr(contract, budget.value) == ceiling + 1  # the contract is untouched


@pytest.mark.parametrize("budget", MISSION_BUDGETS)
def test_a_contract_value_below_the_ceiling_passes(budget):
    limits = make_system_limits()
    contract = make_reliability_contract(**{budget.value: limits.ceiling(budget) - 1})
    assert check_resources(make_plan(steps=()), contract=contract, limits=limits).status is StageStatus.PASSED


def test_a_zero_contract_budget_is_a_real_limit_not_unset():
    contract = make_reliability_contract(max_agent_calls=0)
    result = check_resources(agent_steps(1), contract=contract, limits=make_system_limits())
    (violation,) = result.violations
    assert violation.code is ViolationCode.AGENT_CALLS_EXCEEDED
    assert (violation.limit_value, violation.observed_value) == (0, 1)


def test_an_omitted_contract_budget_falls_back_to_the_system_ceiling():
    limits = make_system_limits(max_agent_calls=2)
    contract = make_reliability_contract()  # max_agent_calls omitted (D-065)
    assert check_resources(agent_steps(2), contract=contract, limits=limits).status is StageStatus.PASSED
    result = check_resources(agent_steps(3), contract=contract, limits=limits)
    (violation,) = result.violations
    assert violation.code is ViolationCode.AGENT_CALLS_EXCEEDED
    assert (violation.limit_value, violation.observed_value) == (2, 3)


def test_the_effective_agent_call_limit_is_the_tighter_contract_value():
    limits = make_system_limits(max_agent_calls=20)
    contract = make_reliability_contract(max_agent_calls=1)
    assert check_resources(agent_steps(1), contract=contract, limits=limits).status is StageStatus.PASSED
    (violation,) = check_resources(agent_steps(2), contract=contract, limits=limits).violations
    assert (violation.limit_value, violation.observed_value) == (1, 2)


def test_a_contract_over_the_ceiling_still_checks_the_plan_against_the_ceiling():
    # Effective limit is min(system, contract) = the ceiling, so both fire.
    limits = make_system_limits(max_agent_calls=2)
    contract = make_reliability_contract(max_agent_calls=30)
    result = check_resources(agent_steps(3), contract=contract, limits=limits)
    assert [v.code for v in result.violations] == [
        ViolationCode.CONTRACT_EXCEEDS_CEILING,
        ViolationCode.AGENT_CALLS_EXCEEDED,
    ]
    assert result.violations[1].limit_value == 2


def test_a_contract_over_the_ceiling_with_a_small_plan_reports_only_the_contract():
    limits = make_system_limits(max_agent_calls=2)
    contract = make_reliability_contract(max_agent_calls=30)
    result = check_resources(agent_steps(1), contract=contract, limits=limits)
    assert [v.code for v in result.violations] == [ViolationCode.CONTRACT_EXCEEDS_CEILING]


def test_the_agent_call_message_says_declared_and_not_actual():
    limits = make_system_limits(max_agent_calls=1)
    (violation,) = check_resources(
        agent_steps(2), contract=make_reliability_contract(), limits=limits
    ).violations
    assert "declares" in violation.message
    assert "declared steps, not actual invocations" in violation.message


def test_only_agent_steps_count_as_declared_agent_calls():
    plan = make_plan(
        steps=(
            make_agent_step(step_id=StepId("a")),
            *(make_control_step(step_id=StepId(f"c{i}")) for i in range(5)),
        )
    )
    limits = make_system_limits(max_agent_calls=1)
    assert check_resources(plan, contract=make_reliability_contract(), limits=limits).status is StageStatus.PASSED


def test_other_budgets_are_not_inferred_from_plan_structure():
    # D-105: RETRY / REPLAN steps are not "retries" or "replans"; nothing in the
    # plan is counted against max_retries, max_replans, tool calls, time or tokens.
    plan = make_plan(
        steps=(
            make_control_step(step_id=StepId("r1"), kind=PlanStepKind.RETRY),
            make_control_step(step_id=StepId("r2"), kind=PlanStepKind.RETRY),
            make_control_step(step_id=StepId("p1"), kind=PlanStepKind.REPLAN),
        )
    )
    contract = make_reliability_contract(max_retries=0, max_replans=0, max_tool_calls=0, max_tokens=0)
    result = check_resources(plan, contract=contract, limits=make_system_limits())
    assert result.status is StageStatus.PASSED


def test_budget_violations_follow_the_fixed_budget_order_then_agent_calls():
    limits = make_system_limits()
    contract = make_reliability_contract(
        **{b.value: limits.ceiling(b) + 1 for b in reversed(MISSION_BUDGETS)}
    )
    result = check_resources(agent_steps(limits.max_agent_calls + 5), contract=contract, limits=limits)
    assert [v.limit_name for v in result.violations] == [*MISSION_BUDGETS, LimitName.MAX_AGENT_CALLS]


def test_an_empty_plan_declares_zero_agent_calls():
    limits = make_system_limits(max_agent_calls=0)
    result = check_resources(make_plan(steps=()), contract=make_reliability_contract(), limits=limits)
    assert result.status is StageStatus.PASSED


# --- COMPLEXITY (D-050, D-104, D-106) --------------------------------------


def test_an_empty_plan_passes_even_against_all_zero_shape_limits():
    limits = make_system_limits(max_nodes=0, max_depth=0, max_parallel_branches=0)
    assert check_complexity(make_plan(steps=()), limits=limits).status is StageStatus.PASSED


def test_node_count_equal_to_max_nodes_passes_and_one_more_fails():
    limits = make_system_limits(max_nodes=3, max_depth=10, max_parallel_branches=10)
    assert check_complexity(agent_steps(3), limits=limits).status is StageStatus.PASSED
    result = check_complexity(agent_steps(4), limits=limits)
    (violation,) = result.violations
    assert violation.code is ViolationCode.MAX_NODES_EXCEEDED
    assert (violation.limit_value, violation.observed_value) == (3, 4)


def test_depth_equal_to_max_depth_passes_and_one_more_fails():
    limits = make_system_limits(max_depth=3)
    chain3 = plan_of({"a": "", "b": "a", "c": "b"})
    chain4 = plan_of({"a": "", "b": "a", "c": "b", "d": "c"})
    assert check_complexity(chain3, limits=limits).status is StageStatus.PASSED
    (violation,) = check_complexity(chain4, limits=limits).violations
    assert violation.code is ViolationCode.MAX_DEPTH_EXCEEDED
    assert (violation.limit_value, violation.observed_value) == (3, 4)


def test_a_single_step_plan_has_depth_one():
    # D-104: depth counts nodes.
    plan = plan_of({"only": ""})
    assert check_complexity(plan, limits=make_system_limits(max_depth=1)).status is StageStatus.PASSED
    (violation,) = check_complexity(plan, limits=make_system_limits(max_depth=0)).violations
    assert violation.observed_value == 1


def test_depth_is_the_longest_component_not_the_total():
    plan = plan_of({"a": "", "b": "a", "x": "", "y": "x"})
    assert check_complexity(plan, limits=make_system_limits(max_depth=2)).status is StageStatus.PASSED


def test_width_equal_to_the_limit_passes_and_one_more_fails():
    limits = make_system_limits(max_parallel_branches=4)
    assert check_complexity(agent_steps(4), limits=limits).status is StageStatus.PASSED
    (violation,) = check_complexity(agent_steps(5), limits=limits).violations
    assert violation.code is ViolationCode.MAX_PARALLEL_BRANCHES_EXCEEDED
    assert (violation.limit_value, violation.observed_value) == (4, 5)


def test_exact_antichain_width_is_enforced_not_the_widest_level():
    # Widest level is 2 but {p, q, t} is an antichain of 3 (see the graph tests).
    plan = plan_of({"s": "", "q": "s", "t": "s", "r": "t", "p": ""})
    assert check_complexity(plan, limits=make_system_limits(max_parallel_branches=3)).status is StageStatus.PASSED
    (violation,) = check_complexity(plan, limits=make_system_limits(max_parallel_branches=2)).violations
    assert violation.code is ViolationCode.MAX_PARALLEL_BRANCHES_EXCEEDED
    assert (violation.limit_value, violation.observed_value) == (2, 3)


def test_nodes_and_depth_are_reported_together_and_width_is_skipped_when_oversize():
    plan = plan_of({"a": "", "b": "a", "c": "b", "x": "", "y": "", "z": ""})
    limits = make_system_limits(max_nodes=5, max_depth=2, max_parallel_branches=2)
    assert [v.code for v in check_complexity(plan, limits=limits).violations] == [
        ViolationCode.MAX_NODES_EXCEEDED,
        ViolationCode.MAX_DEPTH_EXCEEDED,
    ]


def test_depth_then_width_are_reported_together_within_max_nodes():
    plan = plan_of({"a": "", "b": "a", "c": "b", "x": "", "y": "", "z": ""})
    limits = make_system_limits(max_nodes=6, max_depth=2, max_parallel_branches=2)
    assert [v.code for v in check_complexity(plan, limits=limits).violations] == [
        ViolationCode.MAX_DEPTH_EXCEEDED,
        ViolationCode.MAX_PARALLEL_BRANCHES_EXCEEDED,
    ]


def test_an_oversize_plan_skips_width_but_still_checks_depth():
    limits = make_system_limits(max_nodes=3, max_depth=2, max_parallel_branches=1)
    result = check_complexity(agent_steps(5), limits=limits)  # width 5 would breach 1
    assert result.status is StageStatus.FAILED
    assert [v.code for v in result.violations] == [ViolationCode.MAX_NODES_EXCEEDED]
    assert "max_parallel_branches (the plan exceeds max_nodes)" in result.detail

    chain = plan_of({f"s{i}": f"s{i - 1}" if i else "" for i in range(5)})
    result = check_complexity(chain, limits=limits)
    assert [v.code for v in result.violations] == [
        ViolationCode.MAX_NODES_EXCEEDED,
        ViolationCode.MAX_DEPTH_EXCEEDED,
    ]


def test_a_cyclic_plan_within_max_nodes_is_skipped_not_passed():
    result = check_complexity(plan_of({"a": "b", "b": "a"}), limits=make_system_limits())
    assert result.status is StageStatus.SKIPPED
    assert result.violations == ()
    assert "the plan is cyclic" in result.detail


def test_the_v01_self_dependency_plan_is_skipped_not_passed_by_complexity():
    result = check_complexity(plan_of({"s1": "s1"}), limits=make_system_limits())
    assert result.status is StageStatus.SKIPPED


def test_a_cyclic_plan_over_max_nodes_still_fails_on_node_count():
    limits = make_system_limits(max_nodes=1)
    result = check_complexity(plan_of({"a": "b", "b": "a"}), limits=limits)
    assert result.status is StageStatus.FAILED
    assert [v.code for v in result.violations] == [ViolationCode.MAX_NODES_EXCEEDED]
    assert "the plan is cyclic" in result.detail


def test_a_passing_complexity_stage_has_no_detail():
    result = check_complexity(agent_steps(2), limits=make_system_limits())
    assert result.status is StageStatus.PASSED
    assert result.detail is None


def test_control_steps_count_toward_nodes_depth_and_width():
    plan = make_plan(
        steps=(
            make_control_step(step_id=StepId("v1")),
            make_control_step(step_id=StepId("v2"), depends_on=(StepId("v1"),)),
        )
    )
    limits = make_system_limits(max_nodes=1, max_depth=1, max_parallel_branches=1)
    assert [v.code for v in check_complexity(plan, limits=limits).violations] == [
        ViolationCode.MAX_NODES_EXCEEDED,
        ViolationCode.MAX_DEPTH_EXCEEDED,
    ]


def test_a_300_step_plan_is_checked_promptly():
    plan = agent_steps(300)
    limits = make_system_limits(max_nodes=300, max_depth=1, max_parallel_branches=300)
    assert check_complexity(plan, limits=limits).status is StageStatus.PASSED
