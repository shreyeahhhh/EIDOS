"""What one candidate-generation round produced (decisions.md D-178 to D-182; V0.7 Step 3).

Never a ranking and never a "best" — candidate generation is not strategy selection (V0.8, not built). Mirrors the
codebase's own report-shaped-result discipline (``PlanValidationReport``, ``BindReport``, ``IntakeResult``): a
caller sees everything that happened, not only what survived.
"""

from pydantic import Field

from eidos.contracts import EidosModel

from .strategy import Strategy, StrategyShape


class RejectedCandidate(EidosModel):
    """A structurally distinct shape the generator produced that named a capability outside the mission's own
    ``TaskGenome.required_capabilities`` — the one boundary check every ``CandidateGenerator`` is held to,
    regardless of whether it kept the rule (``generator.py``'s own docstring). Never silently dropped."""

    shape: StrategyShape
    reason: str = Field(min_length=1)


class CandidateGenerationResult(EidosModel):
    """``candidates`` is capped at the caller's ``max_candidates`` (D-181); ``rejected`` and ``truncated`` account
    for everything else a distinct, valid shape could have been but was not, so nothing disappears silently."""

    candidates: tuple[Strategy, ...]
    rejected: tuple[RejectedCandidate, ...] = ()
    truncated: int = Field(default=0, ge=0)
