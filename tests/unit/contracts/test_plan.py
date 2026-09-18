"""Plan and PlanStep (decisions.md D-004, D-047, D-049, D-050, D-082, D-088, D-092, D-093, D-101)."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from eidos.contracts import (
    AgentStep,
    CapabilityId,
    ControlStep,
    DEFAULT_TENANT_ID,
    MissionId,
    Plan,
    PlanId,
    PlanStepKind,
    StepId,
    TenantId,
)

from conftest import make_agent_step, make_control_step, make_plan


# --- PlanStep: the discriminated union itself ----------------------------


def test_agent_step_requires_capability():
    with pytest.raises(ValidationError):
        AgentStep(step_id=StepId("s1"), depends_on=())


def test_agent_step_kind_defaults_to_agent():
    step = make_agent_step()
    assert step.kind == PlanStepKind.AGENT


def test_control_step_rejects_capability_field():
    # decisions.md D-049/D-101: control steps and capability are
    # unrepresentable together, not merely rejected by a rule — this is
    # extra="forbid" firing on a field ControlStep does not declare.
    with pytest.raises(ValidationError):
        ControlStep(step_id=StepId("s1"), depends_on=(), kind=PlanStepKind.ROUTE, capability=CapabilityId("x"))


@pytest.mark.parametrize(
    "kind",
    [
        PlanStepKind.ROUTE,
        PlanStepKind.VERIFY,
        PlanStepKind.RETRY,
        PlanStepKind.REPLAN,
        PlanStepKind.HUMAN_APPROVAL,
        PlanStepKind.TERMINATE,
    ],
)
def test_every_control_kind_constructs_without_capability(kind):
    step = make_control_step(kind=kind)
    assert step.kind == kind


def test_agent_kind_literal_rejects_a_control_kind_value():
    with pytest.raises(ValidationError):
        AgentStep(step_id=StepId("s1"), depends_on=(), kind=PlanStepKind.ROUTE, capability=CapabilityId("x"))


def test_depends_on_may_be_empty_for_a_dag_root():
    step = make_agent_step(depends_on=())
    assert step.depends_on == ()


def test_step_is_immutable():
    step = make_agent_step()
    with pytest.raises(ValidationError):
        step.step_id = StepId("changed")


# --- Plan: construction and required/optional fields ---------------------


def test_valid_construction_with_only_required_fields():
    plan = make_plan()
    assert plan.parent_plan_id is None
    assert plan.replan_reason is None


def test_steps_may_be_empty():
    plan = make_plan(steps=())
    assert plan.steps == ()


def test_tenant_id_defaults_when_omitted():
    plan = Plan(
        plan_id=PlanId(uuid4()),
        mission_id=MissionId(uuid4()),
        version=1,
        steps=(make_agent_step(),),
    )
    assert plan.tenant_id == DEFAULT_TENANT_ID


def test_mission_id_is_required():
    # decisions.md D-088: Plan.mission_id stays required (deliberate
    # asymmetry with D-068's TaskGenome).
    with pytest.raises(ValidationError):
        Plan(
            tenant_id=TenantId(uuid4()),
            plan_id=PlanId(uuid4()),
            version=1,
            steps=(),
        )


@pytest.mark.parametrize("bad_version", [0, -1])
def test_version_below_one_is_rejected(bad_version):
    with pytest.raises(ValidationError):
        make_plan(version=bad_version)


def test_version_one_is_accepted():
    plan = make_plan(version=1)
    assert plan.version == 1


def test_parent_plan_id_and_replan_reason_are_optional():
    parent = make_plan()
    child = make_plan(
        tenant_id=parent.tenant_id,
        mission_id=parent.mission_id,
        version=2,
        parent_plan_id=parent.plan_id,
        replan_reason="insufficient evidence",
    )
    assert child.parent_plan_id == parent.plan_id
    assert child.replan_reason == "insufficient evidence"


def test_model_is_immutable():
    plan = make_plan()
    with pytest.raises(ValidationError):
        plan.version = 2


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        make_plan(unexpected_field=123)


# --- Plan: DAG-level validation (step_id uniqueness, depends_on) ---------


def test_duplicate_step_id_is_rejected():
    with pytest.raises(ValidationError, match="D-092|D-093"):
        make_plan(
            steps=(
                make_agent_step(step_id=StepId("dup")),
                make_control_step(step_id=StepId("dup")),
            )
        )


def test_depends_on_referencing_unknown_step_id_is_rejected():
    with pytest.raises(ValidationError, match="D-004"):
        make_plan(
            steps=(
                make_agent_step(step_id=StepId("s1"), depends_on=(StepId("does_not_exist"),)),
            )
        )


def test_depends_on_referencing_a_sibling_step_is_accepted():
    plan = make_plan(
        steps=(
            make_agent_step(step_id=StepId("s1"), depends_on=()),
            make_control_step(step_id=StepId("s2"), depends_on=(StepId("s1"),)),
        )
    )
    assert plan.steps[1].depends_on == ("s1",)


def test_self_dependency_is_not_rejected_in_v01():
    # decisions.md D-004/D-093: cycle detection, including the trivial case
    # of a self-loop, is explicitly out of V0.1 scope (V0.2). Only
    # referential existence is checked here, and a step referencing its own
    # step_id does exist among its siblings.
    plan = make_plan(
        steps=(make_agent_step(step_id=StepId("s1"), depends_on=(StepId("s1"),)),)
    )
    assert plan.steps[0].depends_on == ("s1",)


def test_step_ids_unique_within_one_plan_do_not_conflict_across_plans():
    # decisions.md D-092: uniqueness is scoped to one Plan instance/version,
    # not across a mission's plan versions.
    tenant_id = TenantId(uuid4())
    mission_id = MissionId(uuid4())
    plan_v1 = make_plan(
        tenant_id=tenant_id,
        mission_id=mission_id,
        version=1,
        steps=(make_agent_step(step_id=StepId("s1")),),
    )
    plan_v2 = make_plan(
        tenant_id=tenant_id,
        mission_id=mission_id,
        version=2,
        parent_plan_id=plan_v1.plan_id,
        steps=(make_agent_step(step_id=StepId("s1")),),
    )
    assert plan_v1.steps[0].step_id == plan_v2.steps[0].step_id == "s1"
