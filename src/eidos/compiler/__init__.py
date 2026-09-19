"""Plan compilation — milestone V0.3, Step 2: the compiled form and ``compile_plan``.

Turns a validated ``Plan`` into an immutable, backend-neutral ``CompiledPlan``.
The Plan DSL remains the source of truth; the compiled form is derived from it
and is never edited.

    from eidos.compiler import compile_plan
    report = compile_plan(plan, validation_report)      # a typed CompileReport, never raises
    report.compiled                                    # a CompiledPlan, or None

Constraints (CLAUDE.md §8; decisions.md D-112, D-114, D-115, D-123):

- Compiles only ``agent`` and ``VERIFY`` steps. ROUTE, RETRY, REPLAN, TERMINATE
  and HUMAN_APPROVAL are rejected at compile time (D-112); D-012 stays Open.
- Input is a ``Plan`` and an accepted ``PlanValidationReport``. The compiler
  re-checks the structure it depends on and does not repeat V0.2's capability,
  resource, complexity or policy checks.
- Pure and deterministic: no I/O, no clock, no randomness, no hidden state.
- Backend-neutral: imports only ``eidos.contracts`` and the public surface of
  ``eidos.validation``. It never imports the runtime or any execution backend (D-115).
- Writes nothing to MissionState and emits no event (D-123).

Not here: any execution, port, admission guard, verification runtime, retry,
replan driver or backend object. Those are later V0.3 steps.
"""

from .compile import compile_plan
from .ir import SUPPORTED_STEP_KINDS, CompiledNode, CompiledPlan, VerifyNode, WorkNode
from .results import CompileFailureCode, CompileReport, CompileViolation

__all__ = [
    "SUPPORTED_STEP_KINDS",
    "CompileFailureCode",
    "CompileReport",
    "CompileViolation",
    "CompiledNode",
    "CompiledPlan",
    "VerifyNode",
    "WorkNode",
    "compile_plan",
]
