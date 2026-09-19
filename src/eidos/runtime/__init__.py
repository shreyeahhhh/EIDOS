"""Backend-neutral execution — milestone V0.3, Step 3.

Defines what a run *means* (level-synchronous, D-117) and ships the sequential
reference executor that embodies it (D-128). An execution backend (D-115) is later
held to the same results.

    from eidos.runtime import SequentialExecutor, context_from_state
    executor = SequentialExecutor(work_executor=..., verifier=..., admission_guard=...)
    result = executor.run(compiled_plan, context_from_state(state, compiled_plan))
    # a RunResult, or a RunRejection when the run may not start

Constraints (CLAUDE.md §8; decisions.md D-113, D-115, D-119, D-122, D-123):

- Backend-neutral: imports only ``eidos.contracts``, ``eidos.compiler``, pydantic and the
  standard library. It never imports an execution backend or a workflow library (D-115).
- No I/O, no network, no clock, no randomness, no hidden state. Ports are synchronous.
- MissionState is read once, to build a frozen ``ExecutionContext``, and never written
  (invariants 1 and 2). No ``MissionEvent`` is emitted (D-123): invariant 15 is **not
  exercised** by V0.3.
- No automatic retry, no in-run replan, no runtime budget, time or token accounting.
  The ``AdmissionGuard`` is required; no guard ships.

Not here: any execution backend, real agents, model providers, remote-agent or tool
protocols, events, the reducer, checkpoints, a planner or a driver loop.
"""

from .context import ExecutionContext, context_from_state
from .executor import SequentialExecutor
from .ports import (
    AdmissionDecision,
    AdmissionGuard,
    AdmissionOutcome,
    AdmissionRequest,
    VerificationResult,
    VerificationVerdict,
    Verifier,
    WorkExecutor,
    WorkResult,
    WorkStatus,
)
from .preconditions import check_run_preconditions
from .results import (
    HaltInfo,
    NodeResult,
    NodeStatus,
    PriorOutcomes,
    RunOutcome,
    RunRejection,
    RunRejectionCode,
    RunResult,
)

__all__ = [
    "AdmissionDecision",
    "AdmissionGuard",
    "AdmissionOutcome",
    "AdmissionRequest",
    "ExecutionContext",
    "HaltInfo",
    "NodeResult",
    "NodeStatus",
    "PriorOutcomes",
    "RunOutcome",
    "RunRejection",
    "RunRejectionCode",
    "RunResult",
    "SequentialExecutor",
    "VerificationResult",
    "VerificationVerdict",
    "Verifier",
    "WorkExecutor",
    "WorkResult",
    "WorkStatus",
    "check_run_preconditions",
    "context_from_state",
]
