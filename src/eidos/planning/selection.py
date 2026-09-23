"""``select_strategy`` — the selection orchestration boundary (decisions.md D-186 to D-189; V0.8 Step 2).

**Why this exists at all, separately from ``Selector``:** the same "genuinely required, not genuinely optional"
test ``pipeline.generate_candidate_strategies`` was built against. Three concerns apply to *any* ``Selector``, not
only the deterministic reference one, so none belongs duplicated inside every implementation: the zero- and
one-candidate edge cases (nothing to choose, or nothing to choose *between* — no ``Selector`` is even called for
either), and, the actual enforcement point, **candidate-set membership**. A ``Selector`` only ever proposes a
``StrategyId`` (``selector.py``'s own docstring); this function is the one place that decides whether that
proposal is honoured — governance never depends on the selector behaving, mirroring exactly the same discipline
``generate_candidate_strategies`` already applies to an untrusted ``CandidateGenerator`` (D-178 onward).

**Feasibility is not re-run here.** ``candidates`` is trusted to already be the feasibility-filtered output of
``pipeline.generate_candidate_strategies`` (V0.7) — every candidate offered to a ``Selector`` is, by construction,
already admissible. The membership check below is an identity check (did the selector name one of *these exact*
objects), not a second admissibility pass; re-running the feasibility gate here would be exactly the kind of
duplicated authority D-180 already ruled against for the Plan validator, applied to itself one layer up.

**The exact object is returned, never a reconstructed copy.** ``matched`` is the same ``Strategy`` instance found
in ``candidates`` by identity of ``strategy_id`` — never rebuilt through the constructor, so a caller holding a
reference to a candidate can compare it to ``SelectionResult.selected`` with ``is``, not only ``==``.
"""

from eidos.contracts import TaskGenome

from .results import SelectionOutcome, SelectionResult
from .selector import Selector, SelectorFailure
from .strategy import Strategy


def select_strategy(selector: Selector, candidates: tuple[Strategy, ...], task_genome: TaskGenome) -> SelectionResult:
    """Select one of ``candidates`` — no ranking, no "best": ``Selector`` proposes at most one name, this function
    only ever admits or refuses it. Never mutates ``candidates``."""
    if not candidates:
        return SelectionResult(outcome=SelectionOutcome.NO_FEASIBLE_CANDIDATES, reason="no feasible candidates")

    if len(candidates) == 1:  # nothing to choose between: no Selector call at all
        return SelectionResult(outcome=SelectionOutcome.SELECTED, selected=candidates[0])

    choice = selector.select(candidates, task_genome)

    if isinstance(choice, SelectorFailure):
        return SelectionResult(outcome=SelectionOutcome.SELECTOR_FAILED, reason=choice.message)

    matched = next((candidate for candidate in candidates if candidate.strategy_id == choice.strategy_id), None)
    if matched is None:
        return SelectionResult(
            outcome=SelectionOutcome.INVALID_CANDIDATE_RETURNED,
            reason=f"selector named strategy_id {choice.strategy_id!r}, which is not in the candidate set",
        )
    return SelectionResult(outcome=SelectionOutcome.SELECTED, selected=matched)
