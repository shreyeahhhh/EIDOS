"""Plan validation — milestone V0.2 (docs/05_plan_dsl.md §4, handoff §14).

A deterministic pipeline that decides whether a Plan may proceed toward
compilation. Invariant 5: no plan executes unvalidated.

    from eidos.validation import SystemLimits, validate_plan_json
    report = validate_plan_json(text, state, SystemLimits(...))   # explicit limits, always
    report.accepted

Constraints (CLAUDE.md §8, decisions.md D-103, D-105, D-110):

- Pure and deterministic: no I/O, no network, no LLM, no randomness, no
  wall-clock, no hidden global state.
- Depends only on the public surface of ``eidos.contracts``.
- No production numeric limit is defined here. Every ceiling is supplied by
  the caller (D-103); actual values are governed by D-046 (Open).
- Invalid plans are reported, never raised.

Not here: the compiler (V0.3), capability-to-agent availability (V0.4), the
policy engine (D-060/D-061/D-074, Open), or any runtime counting of retries,
replans, tool calls, time or tokens (D-043, V0.3).
"""

from .limits import LimitName, SystemLimits
from .pipeline import validate_plan, validate_plan_json
from .results import (
    PlanValidationReport,
    StageResult,
    StageStatus,
    ValidationStage,
    Violation,
    ViolationCode,
)

__all__ = [
    "LimitName",
    "PlanValidationReport",
    "StageResult",
    "StageStatus",
    "SystemLimits",
    "ValidationStage",
    "Violation",
    "ViolationCode",
    "validate_plan",
    "validate_plan_json",
]
