"""Typed compile results (decisions.md D-112, D-114): a family separate from V0.2's."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from eidos.compiler import (
    SUPPORTED_STEP_KINDS,
    CompileFailureCode,
    CompileReport,
    CompileViolation,
    CompiledPlan,
    WorkNode,
)
from eidos.contracts import CapabilityId, MissionId, PlanId, PlanStepKind, StepId, TenantId
from eidos.validation import ViolationCode

PLAN = PlanId(UUID(int=3))
UNSUPPORTED_KINDS = [k for k in PlanStepKind if k not in SUPPORTED_STEP_KINDS]

EVIDENCE = [
    CompileFailureCode.MISSING_VALIDATION,
    CompileFailureCode.VALIDATION_NOT_ACCEPTED,
    CompileFailureCode.VALIDATION_PLAN_MISMATCH,
]
PLAN_LEVEL = [
    CompileFailureCode.DUPLICATE_STEP_ID,
    CompileFailureCode.UNKNOWN_DEPENDENCY,
    CompileFailureCode.DEPENDENCY_CYCLE,
]


def one_node_plan(plan_id=PLAN) -> CompiledPlan:
    node = WorkNode(
        step_id=StepId("a"), position=0, level=1, predecessors=(), capability=CapabilityId("r")
    )
    return CompiledPlan(
        tenant_id=TenantId(UUID(int=1)),
        mission_id=MissionId(UUID(int=2)),
        plan_id=plan_id,
        plan_version=1,
        nodes=(node,),
    )


def violation(code, **fields) -> CompileViolation:
    return CompileViolation(code=code, message="a reason", **fields)


# --- the code set and its separation from V0.2 ------------------------------------


def test_the_failure_codes_are_exactly_these_eight():
    assert [c.value for c in CompileFailureCode] == [
        "missing_validation",
        "validation_not_accepted",
        "validation_plan_mismatch",
        "duplicate_step_id",
        "unknown_dependency",
        "dependency_cycle",
        "unsupported_step_kind",
        "malformed_step",
    ]


def test_compile_failures_are_a_separate_family_from_validation_violations():
    assert CompileFailureCode is not ViolationCode
    assert not issubclass(CompileViolation, Exception)
    # A validation ViolationCode is never accepted where a compile code is required.
    with pytest.raises(ValidationError):
        CompileViolation(code=ViolationCode.CYCLE_DETECTED, message="x", step_ids=(StepId("a"),))
    # And a compile code has no counterpart with the unsupported-kind meaning in V0.2.
    assert "unsupported_step_kind" not in {c.value for c in ViolationCode}


# --- CompileViolation: fields follow the code -----------------------------------------


@pytest.mark.parametrize("code", EVIDENCE)
def test_evidence_violations_are_about_the_report_not_steps(code):
    assert violation(code).step_ids == ()
    with pytest.raises(ValidationError, match="not steps"):
        violation(code, step_ids=(StepId("a"),))


@pytest.mark.parametrize("code", PLAN_LEVEL)
def test_plan_level_violations_require_the_steps_they_concern(code):
    assert violation(code, step_ids=(StepId("a"), StepId("b"))).step_ids == ("a", "b")
    with pytest.raises(ValidationError, match="requires the step_ids"):
        violation(code)


@pytest.mark.parametrize("code", [CompileFailureCode.UNSUPPORTED_STEP_KIND, CompileFailureCode.MALFORMED_STEP])
def test_single_step_violations_concern_exactly_one_step(code):
    extra = dict(step_kind=PlanStepKind.ROUTE) if code is CompileFailureCode.UNSUPPORTED_STEP_KIND else {}
    assert violation(code, step_ids=(StepId("a"),), **extra)
    for bad in ((), (StepId("a"), StepId("b"))):
        with pytest.raises(ValidationError, match="exactly one step"):
            violation(code, step_ids=bad, **extra)


@pytest.mark.parametrize("kind", UNSUPPORTED_KINDS)
def test_an_unsupported_step_kind_violation_names_the_kind(kind):
    v = violation(CompileFailureCode.UNSUPPORTED_STEP_KIND, step_ids=(StepId("a"),), step_kind=kind)
    assert v.step_kind is kind


@pytest.mark.parametrize("kind", list(SUPPORTED_STEP_KINDS) + [None])
def test_an_unsupported_step_kind_violation_cannot_name_a_supported_kind_or_none(kind):
    with pytest.raises(ValidationError, match="does not compile"):
        violation(CompileFailureCode.UNSUPPORTED_STEP_KIND, step_ids=(StepId("a"),), step_kind=kind)


@pytest.mark.parametrize("code", EVIDENCE + PLAN_LEVEL + [CompileFailureCode.MALFORMED_STEP])
def test_only_the_unsupported_kind_code_may_carry_a_step_kind(code):
    fields = dict(step_ids=(StepId("a"),)) if code not in EVIDENCE else {}
    with pytest.raises(ValidationError, match="must not carry a step_kind"):
        violation(code, step_kind=PlanStepKind.ROUTE, **fields)


def test_a_violation_needs_a_message():
    with pytest.raises(ValidationError):
        CompileViolation(code=CompileFailureCode.MISSING_VALIDATION, message="")


def test_a_violation_is_frozen_strict_and_closed():
    v = violation(CompileFailureCode.MISSING_VALIDATION)
    with pytest.raises(ValidationError):
        v.message = "changed"
    with pytest.raises(ValidationError):
        violation(CompileFailureCode.MISSING_VALIDATION, extra=1)
    with pytest.raises(ValidationError):
        CompileViolation(code="missing_validation", message="x")  # a str is not the enum


# --- CompileReport ------------------------------------------------------------------


def test_a_successful_report_carries_the_compiled_plan_and_no_violations():
    report = CompileReport(plan_id=PLAN, compiled=one_node_plan())
    assert report.succeeded is True
    assert report.violations == ()


def test_a_failed_report_carries_violations_and_no_compiled_plan():
    report = CompileReport(
        plan_id=PLAN, violations=(violation(CompileFailureCode.MISSING_VALIDATION),)
    )
    assert report.succeeded is False
    assert report.compiled is None


def test_a_report_with_neither_or_both_is_rejected():
    with pytest.raises(ValidationError, match="exactly when there are no violations"):
        CompileReport(plan_id=PLAN)
    with pytest.raises(ValidationError, match="exactly when there are no violations"):
        CompileReport(
            plan_id=PLAN,
            compiled=one_node_plan(),
            violations=(violation(CompileFailureCode.MISSING_VALIDATION),),
        )


def test_a_report_cannot_carry_the_compiled_form_of_another_plan():
    with pytest.raises(ValidationError, match="must equal the report's plan_id"):
        CompileReport(plan_id=PlanId(UUID(int=99)), compiled=one_node_plan())


def test_a_report_is_frozen_and_equal_by_value():
    report = CompileReport(plan_id=PLAN, compiled=one_node_plan())
    with pytest.raises(ValidationError):
        report.plan_id = PlanId(UUID(int=4))
    assert report == CompileReport(plan_id=PLAN, compiled=one_node_plan())
    assert report.model_dump_json() == CompileReport(plan_id=PLAN, compiled=one_node_plan()).model_dump_json()
