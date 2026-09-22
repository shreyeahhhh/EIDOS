"""What one candidate-generation round produced (decisions.md D-178 to D-182; V0.7 Steps 3 and 4).

Never a ranking and never a "best" — candidate generation is not strategy selection (V0.8, not built). Mirrors the
codebase's own report-shaped-result discipline (``PlanValidationReport``, ``BindReport``, ``IntakeResult``): a
caller sees everything that happened, not only what survived.
"""

from pydantic import Field

from eidos.contracts import EidosModel

from .feasibility import FeasibilityReport
from .strategy import Strategy


class RejectedCandidate(EidosModel):
    """A structurally distinct, identity-stamped candidate ``check_feasibility`` found infeasible (V0.7 Step 4).
    Never silently dropped: ``report`` names every violation, not merely that one occurred."""

    strategy: Strategy
    report: FeasibilityReport


class CandidateGenerationResult(EidosModel):
    """``candidates`` are the feasible ones, capped at the caller's ``max_candidates`` (D-181); ``rejected`` and
    ``truncated`` account for everything else a distinct, identity-stamped candidate could have been but was not,
    so nothing disappears silently."""

    candidates: tuple[Strategy, ...]
    rejected: tuple[RejectedCandidate, ...] = ()
    truncated: int = Field(default=0, ge=0)
