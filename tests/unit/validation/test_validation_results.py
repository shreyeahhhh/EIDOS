"""Validation result models (decisions.md D-105, D-106, D-110; invariants 5, 13)."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from eidos.contracts import CapabilityId, PlanId, StepId
from eidos.validation.limits import MISSION_BUDGETS, LimitName
from eidos.validation.results import (
    CODE_STAGE,
    PlanValidationReport,
    StageResult,
    StageStatus,
    ValidationStage,
    Violation,
    ViolationCode,
)

STAGES = list(ValidationStage)


# --- builders --------------------------------------------------------------


def limit_violation(code: ViolationCode, name: LimitName, **overrides) -> Violation:
    fields = dict(
        stage=CODE_STAGE[code],
        code=code,
        message="over the limit",
        limit_name=name,
        limit_value=3,
        observed_value=4,
    )
    fields.update(overrides)
    return Violation(**fields)


def cycle_violation(**overrides) -> Violation:
    fields = dict(
        stage=ValidationStage.CYCLE,
        code=ViolationCode.CYCLE_DETECTED,
        message="cycle",
        step_ids=(StepId("a"), StepId("b")),
    )
    fields.update(overrides)
    return Violation(**fields)


def passed(stage: ValidationStage) -> StageResult:
    return StageResult(stage=stage, status=StageStatus.PASSED)


def all_passed_stages() -> list[StageResult]:
    return [passed(stage) for stage in STAGES]


def report_with(**replacements: StageResult) -> PlanValidationReport:
    stages = [replacements.get(s.value, passed(s)) for s in STAGES]
    return PlanValidationReport(plan_id=PlanId(uuid4()), stages=tuple(stages))


# --- ValidationStage / StageStatus ----------------------------------------


def test_stage_order_is_the_invariant_5_order_without_compile():
    assert [s.value for s in ValidationStage] == [
        "schema",
        "dependency",
        "cycle",
        "capability",
        "policy",
        "resource",
        "complexity",
    ]


def test_stage_statuses_are_exactly_the_four_outcomes():
    assert {s.value for s in StageStatus} == {"passed", "failed", "skipped", "not_applicable"}


def test_every_violation_code_has_exactly_one_stage():
    assert set(CODE_STAGE) == set(ViolationCode)
    assert set(CODE_STAGE.values()) <= set(ValidationStage)


def test_only_the_policy_stage_has_no_violation_codes():
    # D-110: POLICY reports NOT_APPLICABLE; there is nothing it can reject on.
    assert set(ValidationStage) - set(CODE_STAGE.values()) == {ValidationStage.POLICY}


# --- Violation: code/stage pairing ---------------------------------------


def test_a_code_under_the_wrong_stage_is_rejected():
    with pytest.raises(ValidationError, match="belongs to stage"):
        cycle_violation(stage=ValidationStage.SCHEMA)


@pytest.mark.parametrize("code", [c for c in ViolationCode if CODE_STAGE[c] in (
    ValidationStage.SCHEMA, ValidationStage.DEPENDENCY)])
def test_plain_codes_construct_with_message_only(code):
    violation = Violation(stage=CODE_STAGE[code], code=code, message="x")
    assert violation.step_ids == ()
    assert violation.limit_name is None


def test_message_may_not_be_empty():
    with pytest.raises(ValidationError):
        Violation(stage=ValidationStage.SCHEMA, code=ViolationCode.SCHEMA_VIOLATION, message="")


# --- Violation: limit fields ------------------------------------------------


@pytest.mark.parametrize(
    "code, name",
    [
        (ViolationCode.MAX_NODES_EXCEEDED, LimitName.MAX_NODES),
        (ViolationCode.MAX_DEPTH_EXCEEDED, LimitName.MAX_DEPTH),
        (ViolationCode.MAX_PARALLEL_BRANCHES_EXCEEDED, LimitName.MAX_PARALLEL_BRANCHES),
        (ViolationCode.AGENT_CALLS_EXCEEDED, LimitName.MAX_AGENT_CALLS),
    ],
)
def test_fixed_limit_codes_construct_with_their_own_limit_name(code, name):
    violation = limit_violation(code, name)
    assert (violation.limit_value, violation.observed_value) == (3, 4)


def test_a_fixed_limit_code_naming_another_limit_is_rejected():
    with pytest.raises(ValidationError, match="must name limit"):
        limit_violation(ViolationCode.MAX_DEPTH_EXCEEDED, LimitName.MAX_NODES)


@pytest.mark.parametrize("missing", ["limit_name", "limit_value", "observed_value"])
def test_a_limit_code_missing_any_limit_field_is_rejected(missing):
    with pytest.raises(ValidationError, match="requires limit_name"):
        limit_violation(ViolationCode.MAX_NODES_EXCEEDED, LimitName.MAX_NODES, **{missing: None})


@pytest.mark.parametrize("budget", MISSION_BUDGETS)
def test_contract_exceeds_ceiling_may_name_any_mission_budget(budget):
    assert limit_violation(ViolationCode.CONTRACT_EXCEEDS_CEILING, budget).limit_name is budget


@pytest.mark.parametrize(
    "shape", [LimitName.MAX_NODES, LimitName.MAX_DEPTH, LimitName.MAX_PARALLEL_BRANCHES]
)
def test_contract_exceeds_ceiling_may_not_name_a_shape_limit(shape):
    # D-009: shape limits are system-only, so no contract value can exceed one.
    with pytest.raises(ValidationError, match="mission budget"):
        limit_violation(ViolationCode.CONTRACT_EXCEEDS_CEILING, shape)


def test_a_non_limit_code_may_not_carry_limit_fields():
    with pytest.raises(ValidationError, match="must not carry limit fields"):
        cycle_violation(limit_name=LimitName.MAX_DEPTH)
    with pytest.raises(ValidationError, match="must not carry limit fields"):
        cycle_violation(observed_value=1)


# --- Violation: subject fields ---------------------------------------------


def test_capability_violation_requires_capability_and_step_ids():
    ok = Violation(
        stage=ValidationStage.CAPABILITY,
        code=ViolationCode.CAPABILITY_NOT_REQUIRED,
        message="not required",
        step_ids=(StepId("s1"),),
        capability=CapabilityId("research"),
    )
    assert ok.capability == "research"
    for bad in (dict(capability=None), dict(step_ids=())):
        fields = dict(
            stage=ValidationStage.CAPABILITY,
            code=ViolationCode.CAPABILITY_NOT_REQUIRED,
            message="m",
            step_ids=(StepId("s1"),),
            capability=CapabilityId("research"),
        )
        fields.update(bad)
        with pytest.raises(ValidationError, match="requires capability and step_ids"):
            Violation(**fields)


def test_only_a_capability_violation_may_carry_a_capability():
    with pytest.raises(ValidationError, match="must not carry a capability"):
        cycle_violation(capability=CapabilityId("research"))


def test_cycle_violation_requires_step_ids():
    with pytest.raises(ValidationError, match="requires the step_ids"):
        cycle_violation(step_ids=())


def test_violation_is_immutable_strict_and_closed():
    violation = cycle_violation()
    with pytest.raises(ValidationError):
        violation.message = "changed"
    with pytest.raises(ValidationError):
        cycle_violation(extra=1)
    with pytest.raises(ValidationError):
        cycle_violation(code="cycle_detected")  # a str is not the enum under strict mode


# --- StageResult ----------------------------------------------------------


def test_passed_stage_needs_no_detail():
    assert passed(ValidationStage.CYCLE).violations == ()


def test_failed_stage_requires_a_violation():
    with pytest.raises(ValidationError, match="at least one violation"):
        StageResult(stage=ValidationStage.CYCLE, status=StageStatus.FAILED)


@pytest.mark.parametrize("status", [StageStatus.PASSED, StageStatus.SKIPPED, StageStatus.NOT_APPLICABLE])
def test_only_a_failed_stage_may_carry_violations(status):
    with pytest.raises(ValidationError, match="must not carry violations"):
        StageResult(
            stage=ValidationStage.CYCLE,
            status=status,
            violations=(cycle_violation(),),
            detail="why",
        )


@pytest.mark.parametrize("status", [StageStatus.SKIPPED, StageStatus.NOT_APPLICABLE])
def test_skipped_and_not_applicable_must_state_why(status):
    with pytest.raises(ValidationError, match="must state why"):
        StageResult(stage=ValidationStage.POLICY, status=status)
    ok = StageResult(stage=ValidationStage.POLICY, status=status, detail="no checks exist")
    assert ok.detail == "no checks exist"


def test_detail_may_not_be_an_empty_string():
    with pytest.raises(ValidationError):
        StageResult(stage=ValidationStage.POLICY, status=StageStatus.NOT_APPLICABLE, detail="")


def test_a_violation_from_another_stage_is_rejected():
    with pytest.raises(ValidationError, match="in the 'schema' stage result"):
        StageResult(
            stage=ValidationStage.SCHEMA,
            status=StageStatus.FAILED,
            violations=(cycle_violation(),),
        )


# --- PlanValidationReport --------------------------------------------------


def test_an_all_passed_report_is_accepted_and_fully_evaluated():
    report = report_with()
    assert report.accepted is True
    assert report.fully_evaluated is True
    assert report.violations == ()


def test_not_applicable_policy_does_not_block_acceptance_but_is_not_a_pass():
    policy = StageResult(
        stage=ValidationStage.POLICY, status=StageStatus.NOT_APPLICABLE, detail="D-110"
    )
    report = report_with(policy=policy)
    assert report.accepted is True
    assert report.result_for(ValidationStage.POLICY).status is StageStatus.NOT_APPLICABLE
    assert report.result_for(ValidationStage.POLICY).status is not StageStatus.PASSED


def test_a_failed_stage_makes_the_report_rejected_but_still_fully_evaluated():
    failed = StageResult(
        stage=ValidationStage.CYCLE, status=StageStatus.FAILED, violations=(cycle_violation(),)
    )
    report = report_with(cycle=failed)
    assert report.accepted is False
    assert report.fully_evaluated is True
    assert report.violations == (cycle_violation(),)


def test_a_skipped_stage_is_never_accepted_even_without_a_failure():
    # Invariants 5 and 13: an unchecked plan is not an accepted plan.
    skipped = StageResult(
        stage=ValidationStage.RESOURCE, status=StageStatus.SKIPPED, detail="input absent"
    )
    report = report_with(resource=skipped)
    assert not any(r.status is StageStatus.FAILED for r in report.stages)
    assert report.accepted is False
    assert report.fully_evaluated is False


def test_violations_are_reported_in_stage_order_then_within_stage_order():
    first = cycle_violation(step_ids=(StepId("a"),))
    second = cycle_violation(step_ids=(StepId("b"),))
    complexity = limit_violation(ViolationCode.MAX_NODES_EXCEEDED, LimitName.MAX_NODES)
    report = report_with(
        complexity=StageResult(
            stage=ValidationStage.COMPLEXITY, status=StageStatus.FAILED, violations=(complexity,)
        ),
        cycle=StageResult(
            stage=ValidationStage.CYCLE, status=StageStatus.FAILED, violations=(first, second)
        ),
    )
    assert report.violations == (first, second, complexity)


def test_report_requires_exactly_seven_stages():
    with pytest.raises(ValidationError, match="exactly one result per stage"):
        PlanValidationReport(stages=tuple(all_passed_stages()[:-1]))
    with pytest.raises(ValidationError, match="exactly one result per stage"):
        PlanValidationReport(stages=tuple(all_passed_stages()) + (passed(ValidationStage.SCHEMA),))
    with pytest.raises(ValidationError, match="exactly one result per stage"):
        PlanValidationReport(stages=())


def test_report_requires_pipeline_order():
    stages = all_passed_stages()
    stages[0], stages[1] = stages[1], stages[0]
    with pytest.raises(ValidationError, match="pipeline order"):
        PlanValidationReport(stages=tuple(stages))


def test_report_rejects_a_duplicated_stage_even_at_the_right_length():
    stages = all_passed_stages()
    stages[-1] = passed(ValidationStage.SCHEMA)
    with pytest.raises(ValidationError, match="pipeline order"):
        PlanValidationReport(stages=tuple(stages))


def test_plan_id_is_optional_for_an_unparseable_plan():
    assert PlanValidationReport(stages=tuple(all_passed_stages())).plan_id is None


def test_equal_inputs_build_equal_reports_and_equal_json():
    plan_id = PlanId(uuid4())
    a = PlanValidationReport(plan_id=plan_id, stages=tuple(all_passed_stages()))
    b = PlanValidationReport(plan_id=plan_id, stages=tuple(all_passed_stages()))
    assert a == b
    assert a.model_dump_json() == b.model_dump_json()


def test_report_is_immutable():
    report = report_with()
    with pytest.raises(ValidationError):
        report.plan_id = None
