"""Typed compile results — what a compilation reports.

decisions.md: D-112 (unsupported kinds are rejected, never compiled), D-114
(compile failures are a separate typed family from V0.2 validation violations:
a plan can be validation-accepted and compile-rejected, and compile never
reuses or extends ``ViolationCode``).

Rules for every model here match V0.2's results: frozen, strict, ``extra=forbid``;
no timestamps, no object reprs, no set-iteration order; every ordering derives
from ``Plan.steps`` order or a fixed sequence. A report is data: ``compile_plan``
returns it and never raises for an invalid plan or report.

Consistency is enforced by model validators, so a mislabelled report is
unconstructible: ``compiled`` is present exactly when there are no violations,
and each violation carries only the fields its code allows.
"""

from enum import StrEnum

from pydantic import Field, model_validator

from eidos.contracts import EidosModel, PlanId, PlanStepKind, StepId

from .ir import SUPPORTED_STEP_KINDS, CompiledPlan


class CompileFailureCode(StrEnum):
    """Closed set of reasons a plan could not be compiled."""

    # Validation evidence (D-114)
    MISSING_VALIDATION = "missing_validation"  # no PlanValidationReport was supplied
    VALIDATION_NOT_ACCEPTED = "validation_not_accepted"
    VALIDATION_PLAN_MISMATCH = "validation_plan_mismatch"  # the report is for another plan
    # Structural properties the compiler depends on and re-checks itself (D-114)
    DUPLICATE_STEP_ID = "duplicate_step_id"
    UNKNOWN_DEPENDENCY = "unknown_dependency"
    DEPENDENCY_CYCLE = "dependency_cycle"
    # Representability
    UNSUPPORTED_STEP_KIND = "unsupported_step_kind"  # a valid kind V0.3 does not compile (D-112)
    MALFORMED_STEP = "malformed_step"  # a step whose kind and shape disagree; not a valid Plan step


# Fixed tuples, used for membership only.
_EVIDENCE_CODES: tuple[CompileFailureCode, ...] = (
    CompileFailureCode.MISSING_VALIDATION,
    CompileFailureCode.VALIDATION_NOT_ACCEPTED,
    CompileFailureCode.VALIDATION_PLAN_MISMATCH,
)
_PLAN_LEVEL_STEP_CODES: tuple[CompileFailureCode, ...] = (
    CompileFailureCode.DUPLICATE_STEP_ID,
    CompileFailureCode.UNKNOWN_DEPENDENCY,
    CompileFailureCode.DEPENDENCY_CYCLE,
)


class CompileViolation(EidosModel):
    """One reason a plan could not be compiled."""

    code: CompileFailureCode
    message: str = Field(min_length=1)
    step_ids: tuple[StepId, ...] = ()
    step_kind: PlanStepKind | None = None  # only for UNSUPPORTED_STEP_KIND

    @model_validator(mode="after")
    def _check_fields_match_code(self) -> "CompileViolation":
        code = self.code
        if code is not CompileFailureCode.UNSUPPORTED_STEP_KIND and self.step_kind is not None:
            raise ValueError(f"code {code.value!r} must not carry a step_kind")
        if code in _EVIDENCE_CODES:
            if self.step_ids:
                raise ValueError(f"code {code.value!r} is about the validation report, not steps")
        elif code in _PLAN_LEVEL_STEP_CODES:
            if not self.step_ids:
                raise ValueError(f"code {code.value!r} requires the step_ids it concerns")
        else:  # one step: UNSUPPORTED_STEP_KIND, MALFORMED_STEP
            if len(self.step_ids) != 1:
                raise ValueError(f"code {code.value!r} concerns exactly one step")
        if code is CompileFailureCode.UNSUPPORTED_STEP_KIND:
            if self.step_kind is None or self.step_kind in SUPPORTED_STEP_KINDS:
                raise ValueError("unsupported_step_kind requires a kind V0.3 does not compile")
        return self


class CompileReport(EidosModel):
    """The outcome of compiling one plan: a compiled form, or the reasons there is none."""

    plan_id: PlanId
    compiled: CompiledPlan | None = None
    violations: tuple[CompileViolation, ...] = ()

    @model_validator(mode="after")
    def _check_compiled_iff_no_violations(self) -> "CompileReport":
        if (self.compiled is None) != bool(self.violations):
            raise ValueError("compiled must be present exactly when there are no violations")
        if self.compiled is not None and self.compiled.plan_id != self.plan_id:
            raise ValueError("compiled.plan_id must equal the report's plan_id")
        return self

    @property
    def succeeded(self) -> bool:
        return self.compiled is not None
