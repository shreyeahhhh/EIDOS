"""What one candidate-generation round, and later one selection round, produced (decisions.md D-178 to D-189;
V0.7 Steps 3 and 4; V0.8 Step 2). One file for every report-shaped result ``eidos.planning`` returns, mirroring
``eidos.validation.results``'s own single-file precedent (``ValidationStage`` through ``PlanValidationReport``,
all together) rather than fragmenting per producer.

Never a ranking and never a "best" — candidate generation is not strategy selection. Mirrors the codebase's own
report-shaped-result discipline (``PlanValidationReport``, ``BindReport``, ``IntakeResult``): a caller sees
everything that happened, not only what survived.
"""

from enum import StrEnum

from pydantic import Field, model_validator

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


class SelectionOutcome(StrEnum):
    """Closed set of what one selection round came to (V0.8 Step 2, D-187)."""

    SELECTED = "selected"
    NO_FEASIBLE_CANDIDATES = "no_feasible_candidates"
    SELECTOR_FAILED = "selector_failed"
    INVALID_CANDIDATE_RETURNED = "invalid_candidate_returned"


class SelectionResult(EidosModel):
    """A typed, replay-ready value only (D-189) — not a ``MissionEvent``, not a ``MissionState`` field, and carries
    no identity of its own (no ``SelectionId``). ``selected`` is set only when ``outcome`` is ``SELECTED``, and is
    always the exact ``Strategy`` object ``selection.select_strategy`` was given, never a reconstructed copy."""

    outcome: SelectionOutcome
    selected: Strategy | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _check_selected_and_reason_match_outcome(self) -> "SelectionResult":
        # Mirrors eidos.state.reducer.ReduceResult's own rule: a mislabelled result is unconstructible, not
        # merely wrong.
        if self.outcome is SelectionOutcome.SELECTED:
            if self.selected is None:
                raise ValueError("a SELECTED outcome must carry the selected strategy")
            if self.reason is not None:
                raise ValueError("a SELECTED outcome needs no reason")
        else:
            if self.selected is not None:
                raise ValueError(f"a {self.outcome.value} outcome must not carry a selected strategy")
            if not self.reason:
                raise ValueError(f"a {self.outcome.value} outcome states why")
        return self
