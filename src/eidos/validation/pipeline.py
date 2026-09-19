"""The V0.2 validation pipeline — two entry points, one ordered report.

    validate_plan_json(text, state, limits)   untrusted ingress: a JSON document
    validate_plan(plan, state, limits)        an already-constructed Plan

decisions.md: D-107 (JSON text is the untrusted ingress), D-103 (``limits`` is
a required argument; there is no ambient configuration), D-110 (POLICY is
``NOT_APPLICABLE``), D-106 (empty plans pass), invariant 5 (stage order),
invariant 13 (a stage that did not run is SKIPPED, never PASSED).

Both entry points return a ``PlanValidationReport`` and never raise for an
invalid plan. Only this module reads ``MissionState``: the stage functions
take the narrow pieces they need.

Stage dependencies, all reported rather than hidden:

- If the plan cannot be constructed from the JSON, every stage after the
  failing one is SKIPPED.
- If the plan's ``mission_id`` / ``tenant_id`` do not match the state, the two
  stages that read the state (CAPABILITY, RESOURCE) are SKIPPED rather than
  run against the wrong mission's genome and contract.
- If step ids or dependencies are invalid, the two graph stages (CYCLE,
  COMPLEXITY) are SKIPPED: the graph is undefined.
"""

from pydantic import ValidationError

from eidos.contracts import (
    DuplicateStepIdError,
    MissionState,
    Plan,
    UnknownDependencyError,
)

from .limits import SystemLimits
from .results import (
    PlanValidationReport,
    StageResult,
    StageStatus,
    ValidationStage,
    Violation,
    ViolationCode,
)
from .stages import (
    check_capabilities,
    check_complexity,
    check_cycles,
    check_dependencies,
    check_policy,
    check_resources,
    identity_violations,
)

_JSON_SYNTAX_ERROR_TYPES = frozenset({"json_invalid", "json_type"})


def _skipped(stage: ValidationStage, reason: str) -> StageResult:
    return StageResult(stage=stage, status=StageStatus.SKIPPED, detail=f"not evaluated: {reason}")


def validate_plan(plan: Plan, state: MissionState, limits: SystemLimits) -> PlanValidationReport:
    """Validate an already-constructed plan against a mission and explicit system limits."""
    identity = identity_violations(plan, mission_id=state.mission_id, tenant_id=state.tenant_id)
    if identity:
        schema = StageResult(
            stage=ValidationStage.SCHEMA, status=StageStatus.FAILED, violations=identity
        )
    else:
        schema = StageResult(
            stage=ValidationStage.SCHEMA,
            status=StageStatus.PASSED,
            detail="plan fields were validated when the Plan was constructed; identity matches the mission",
        )

    dependency = check_dependencies(plan)
    graph_defined = dependency.status is StageStatus.PASSED
    not_defined = "step ids or dependencies are invalid, so the dependency graph is undefined"
    cycle = check_cycles(plan) if graph_defined else _skipped(ValidationStage.CYCLE, not_defined)
    complexity = (
        check_complexity(plan, limits=limits)
        if graph_defined
        else _skipped(ValidationStage.COMPLEXITY, not_defined)
    )

    if identity:
        wrong_mission = (
            "the plan does not belong to this mission, so it must not be checked against "
            "this mission's task genome and reliability contract"
        )
        capability = _skipped(ValidationStage.CAPABILITY, wrong_mission)
        resource = _skipped(ValidationStage.RESOURCE, wrong_mission)
    else:
        capability = check_capabilities(
            plan, required_capabilities=state.task_genome.required_capabilities
        )
        resource = check_resources(plan, contract=state.reliability_contract, limits=limits)

    return PlanValidationReport(
        plan_id=plan.plan_id,
        stages=(schema, dependency, cycle, capability, check_policy(), resource, complexity),
    )


def validate_plan_json(text: str, state: MissionState, limits: SystemLimits) -> PlanValidationReport:
    """Validate an untrusted plan document (JSON text) — the ingress of D-107."""
    try:
        plan = Plan.model_validate_json(text)
    except ValidationError as error:
        return _construction_failure(error)
    return validate_plan(plan, state, limits)


def _location(location: tuple[int | str, ...]) -> str:
    return ".".join(str(part) for part in location) if location else "(plan)"


def _violation_for(detail) -> Violation:
    """One pydantic error -> one typed violation, without matching message text."""
    cause = (detail.get("ctx") or {}).get("error")
    if isinstance(cause, DuplicateStepIdError):
        return Violation(
            stage=ValidationStage.DEPENDENCY,
            code=ViolationCode.DUPLICATE_STEP_ID,
            message=f"step_id {cause.step_id!r} is used by more than one step",
            step_ids=(cause.step_id,),
        )
    if isinstance(cause, UnknownDependencyError):
        return Violation(
            stage=ValidationStage.DEPENDENCY,
            code=ViolationCode.UNKNOWN_DEPENDENCY,
            message=f"step {cause.step_id!r} depends on unknown step {cause.dependency!r}",
            step_ids=(cause.step_id,),
        )
    if detail["type"] in _JSON_SYNTAX_ERROR_TYPES:
        return Violation(
            stage=ValidationStage.SCHEMA,
            code=ViolationCode.MALFORMED_JSON,
            message=f"plan is not valid JSON: {detail['msg']}",
        )
    return Violation(
        stage=ValidationStage.SCHEMA,
        code=ViolationCode.SCHEMA_VIOLATION,
        message=f"{_location(detail['loc'])}: {detail['msg']}",
    )


def _construction_failure(error: ValidationError) -> PlanValidationReport:
    """The report for text that did not become a Plan: every failure attributed, the rest SKIPPED."""
    violations = [_violation_for(detail) for detail in error.errors(include_url=False)]
    schema_violations = tuple(v for v in violations if v.stage is ValidationStage.SCHEMA)
    dependency_violations = tuple(v for v in violations if v.stage is ValidationStage.DEPENDENCY)

    if schema_violations:
        schema = StageResult(
            stage=ValidationStage.SCHEMA, status=StageStatus.FAILED, violations=schema_violations
        )
    else:
        schema = StageResult(
            stage=ValidationStage.SCHEMA,
            status=StageStatus.PASSED,
            detail="every field is valid; the failure is a dependency failure raised by the Plan contract",
        )
    if dependency_violations:
        dependency = StageResult(
            stage=ValidationStage.DEPENDENCY,
            status=StageStatus.FAILED,
            violations=dependency_violations,
        )
    else:
        dependency = _skipped(ValidationStage.DEPENDENCY, "the plan document failed schema validation")

    unbuilt = "the plan could not be constructed from the document"
    return PlanValidationReport(
        plan_id=None,
        stages=(
            schema,
            dependency,
            _skipped(ValidationStage.CYCLE, unbuilt),
            _skipped(ValidationStage.CAPABILITY, unbuilt),
            check_policy(),
            _skipped(ValidationStage.RESOURCE, unbuilt),
            _skipped(ValidationStage.COMPLEXITY, unbuilt),
        ),
    )
