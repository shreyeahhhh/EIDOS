"""Typed validation results — what a validation run reports.

decisions.md: D-105 (only *declared* agent calls are checked structurally;
messages must say so), D-106 (an empty plan is a legal, vacuously-passing
plan), D-110 (the POLICY stage exists and reports ``NOT_APPLICABLE`` — an
honest, distinct outcome, never ``PASSED``), invariant 5 (stage order),
invariant 13 (never manufacture confidence).

Design rules for every model here:

- Frozen, strict, ``extra="forbid"`` (``EidosModel``).
- No timestamps, no object reprs, no set-iteration order: two runs over the
  same inputs must produce equal reports, byte for byte. Every ordering is
  derived from ``plan.steps`` order or from a fixed tuple.
- A report is data. Validators return it; they never raise for an invalid
  plan.

Consistency between a status and its violations, and between a violation's
code and its stage, is enforced by model validators so a mislabelled report
is unconstructible rather than merely wrong.
"""

from enum import StrEnum

from pydantic import Field, model_validator

from eidos.contracts import CapabilityId, EidosModel, PlanId, StepId

from .limits import MISSION_BUDGETS, LimitName


class ValidationStage(StrEnum):
    """The pipeline stages, in the fixed order of invariant 5.

    COMPILE is not a validation stage; it is V0.3. Enum definition order *is*
    the pipeline order and is relied on by ``PlanValidationReport``.
    """

    SCHEMA = "schema"
    DEPENDENCY = "dependency"
    CYCLE = "cycle"
    CAPABILITY = "capability"
    POLICY = "policy"
    RESOURCE = "resource"
    COMPLEXITY = "complexity"


class StageStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    # Not evaluated because an upstream failure or a missing input made the
    # result meaningless. Never a pass.
    SKIPPED = "skipped"
    # No supported check exists for this stage (D-110). Not a pass.
    NOT_APPLICABLE = "not_applicable"


class ViolationCode(StrEnum):
    """Closed set of reasons a plan can be rejected."""

    # SCHEMA
    MALFORMED_JSON = "malformed_json"
    SCHEMA_VIOLATION = "schema_violation"
    PLAN_MISSION_MISMATCH = "plan_mission_mismatch"
    PLAN_TENANT_MISMATCH = "plan_tenant_mismatch"
    # DEPENDENCY
    DUPLICATE_STEP_ID = "duplicate_step_id"
    UNKNOWN_DEPENDENCY = "unknown_dependency"
    # CYCLE
    CYCLE_DETECTED = "cycle_detected"
    # CAPABILITY
    CAPABILITY_NOT_REQUIRED = "capability_not_required"
    # RESOURCE
    CONTRACT_EXCEEDS_CEILING = "contract_exceeds_ceiling"
    AGENT_CALLS_EXCEEDED = "agent_calls_exceeded"
    # COMPLEXITY
    MAX_NODES_EXCEEDED = "max_nodes_exceeded"
    MAX_DEPTH_EXCEEDED = "max_depth_exceeded"
    MAX_PARALLEL_BRANCHES_EXCEEDED = "max_parallel_branches_exceeded"


# The one stage each code belongs to. Plan/state identity mismatches are
# reported under SCHEMA: they are a property of the plan document's own
# identity fields, and invariant 5's order has no earlier home for them.
CODE_STAGE: dict[ViolationCode, ValidationStage] = {
    ViolationCode.MALFORMED_JSON: ValidationStage.SCHEMA,
    ViolationCode.SCHEMA_VIOLATION: ValidationStage.SCHEMA,
    ViolationCode.PLAN_MISSION_MISMATCH: ValidationStage.SCHEMA,
    ViolationCode.PLAN_TENANT_MISMATCH: ValidationStage.SCHEMA,
    ViolationCode.DUPLICATE_STEP_ID: ValidationStage.DEPENDENCY,
    ViolationCode.UNKNOWN_DEPENDENCY: ValidationStage.DEPENDENCY,
    ViolationCode.CYCLE_DETECTED: ValidationStage.CYCLE,
    ViolationCode.CAPABILITY_NOT_REQUIRED: ValidationStage.CAPABILITY,
    ViolationCode.CONTRACT_EXCEEDS_CEILING: ValidationStage.RESOURCE,
    ViolationCode.AGENT_CALLS_EXCEEDED: ValidationStage.RESOURCE,
    ViolationCode.MAX_NODES_EXCEEDED: ValidationStage.COMPLEXITY,
    ViolationCode.MAX_DEPTH_EXCEEDED: ValidationStage.COMPLEXITY,
    ViolationCode.MAX_PARALLEL_BRANCHES_EXCEEDED: ValidationStage.COMPLEXITY,
}

# Codes that report a numeric limit, mapped to the one limit each names.
# CONTRACT_EXCEEDS_CEILING may name any of the six mission budgets instead.
_FIXED_LIMIT: dict[ViolationCode, LimitName] = {
    ViolationCode.AGENT_CALLS_EXCEEDED: LimitName.MAX_AGENT_CALLS,
    ViolationCode.MAX_NODES_EXCEEDED: LimitName.MAX_NODES,
    ViolationCode.MAX_DEPTH_EXCEEDED: LimitName.MAX_DEPTH,
    ViolationCode.MAX_PARALLEL_BRANCHES_EXCEEDED: LimitName.MAX_PARALLEL_BRANCHES,
}
_LIMIT_CODES = frozenset(_FIXED_LIMIT) | {ViolationCode.CONTRACT_EXCEEDS_CEILING}


class Violation(EidosModel):
    """One reason a plan was rejected."""

    stage: ValidationStage
    code: ViolationCode
    message: str = Field(min_length=1)
    step_ids: tuple[StepId, ...] = ()
    limit_name: LimitName | None = None
    limit_value: int | None = None  # the ceiling or effective limit that applied
    observed_value: int | None = None  # the plan's or contract's value
    capability: CapabilityId | None = None

    @model_validator(mode="after")
    def _check_code_matches_stage(self) -> "Violation":
        if CODE_STAGE[self.code] is not self.stage:
            raise ValueError(
                f"code {self.code.value!r} belongs to stage "
                f"{CODE_STAGE[self.code].value!r}, not {self.stage.value!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_limit_fields(self) -> "Violation":
        carries_limit = (
            self.limit_name is not None
            or self.limit_value is not None
            or self.observed_value is not None
        )
        if self.code not in _LIMIT_CODES:
            if carries_limit:
                raise ValueError(f"code {self.code.value!r} must not carry limit fields")
            return self
        if None in (self.limit_name, self.limit_value, self.observed_value):
            raise ValueError(
                f"code {self.code.value!r} requires limit_name, limit_value and observed_value"
            )
        if self.code is ViolationCode.CONTRACT_EXCEEDS_CEILING:
            if self.limit_name not in MISSION_BUDGETS:
                raise ValueError("contract_exceeds_ceiling must name a mission budget")
        elif self.limit_name is not _FIXED_LIMIT[self.code]:
            raise ValueError(
                f"code {self.code.value!r} must name limit "
                f"{_FIXED_LIMIT[self.code].value!r}, not {self.limit_name.value!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_subject_fields(self) -> "Violation":
        if self.code is ViolationCode.CAPABILITY_NOT_REQUIRED:
            if self.capability is None or not self.step_ids:
                raise ValueError("capability_not_required requires capability and step_ids")
        elif self.capability is not None:
            raise ValueError(f"code {self.code.value!r} must not carry a capability")
        if self.code is ViolationCode.CYCLE_DETECTED and not self.step_ids:
            raise ValueError("cycle_detected requires the step_ids on the cycle")
        return self


class StageResult(EidosModel):
    """The outcome of one pipeline stage."""

    stage: ValidationStage
    status: StageStatus
    violations: tuple[Violation, ...] = ()
    # Why a stage was SKIPPED or is NOT_APPLICABLE (required for both); optional
    # context for the others.
    detail: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check_status_consistency(self) -> "StageResult":
        if self.status is StageStatus.FAILED:
            if not self.violations:
                raise ValueError("a FAILED stage must carry at least one violation")
        elif self.violations:
            raise ValueError(f"a {self.status.value} stage must not carry violations")
        if self.status in (StageStatus.SKIPPED, StageStatus.NOT_APPLICABLE) and self.detail is None:
            raise ValueError(f"a {self.status.value} stage must state why (detail)")
        for violation in self.violations:
            if violation.stage is not self.stage:
                raise ValueError(
                    f"violation for stage {violation.stage.value!r} "
                    f"in the {self.stage.value!r} stage result"
                )
        return self


class PlanValidationReport(EidosModel):
    """The full, ordered outcome of validating one plan.

    ``stages`` always holds exactly one result per ``ValidationStage``, in
    pipeline order, whatever happened upstream.
    """

    plan_id: PlanId | None = None  # None when the plan could not be parsed
    stages: tuple[StageResult, ...]

    @model_validator(mode="after")
    def _check_one_result_per_stage_in_order(self) -> "PlanValidationReport":
        if tuple(result.stage for result in self.stages) != tuple(ValidationStage):
            raise ValueError("stages must hold exactly one result per stage, in pipeline order")
        return self

    @property
    def violations(self) -> tuple[Violation, ...]:
        """Every violation, in stage order then within-stage order."""
        return tuple(v for result in self.stages for v in result.violations)

    @property
    def accepted(self) -> bool:
        """True only if every stage PASSED or is NOT_APPLICABLE.

        Deliberately stricter than "no stage FAILED": a SKIPPED stage means a
        check did not run, and an unchecked plan is never accepted
        (invariants 5 and 13).
        """
        return all(
            result.status in (StageStatus.PASSED, StageStatus.NOT_APPLICABLE)
            for result in self.stages
        )

    @property
    def fully_evaluated(self) -> bool:
        """True if no stage was SKIPPED (a rejected report may still be fully evaluated)."""
        return all(result.status is not StageStatus.SKIPPED for result in self.stages)

    def result_for(self, stage: ValidationStage) -> StageResult:
        return self.stages[list(ValidationStage).index(stage)]
