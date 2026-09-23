"""``Selector`` and the deterministic reference implementation (decisions.md D-186 to D-189; V0.8 Step 2).

**The Jev principle, one step further.** V0.7 built the bounded, feasible decision space (D-178 onward); this is
where a choice is finally made *within* it. A ``Selector`` can only ever *name* a candidate — it returns a
``StrategyId``, never a ``Strategy`` value and never Plan DSL — so it structurally cannot invent one (D-186). The
actual enforcement of "only from the supplied candidate set" lives one layer up, in ``selection.select_strategy``'s
own membership check, not here: this module only ever proposes a choice, it never admits one.

**Why a new, narrower failure vocabulary, not ``eidos.agents.model.ModelFailureKind``:** ``eidos.planning`` is a
core layer and may not import ``eidos.agents`` (the existing guard already forbids it) — reuse was checked, not
assumed, and is architecturally impossible here, the identical reason the feasibility gate's own violation
vocabulary (one layer below this one) is already a separate, narrower vocabulary from the Plan validator's own,
rather than an import of it. ``SelectorFailureKind`` has three members, deliberately narrower than
``ModelFailureKind``'s four (no ``EMPTY_RESPONSE`` — a selector's own answer is either a valid id, an invalid one,
or absent; "empty" and "malformed" are the same case from the orchestration boundary's point of view). None of
the three is exercised by ``DeterministicSelector``, which can never fail — the vocabulary is intentionally scoped
to what a *future* model-assisted ``Selector`` (a separate, later adapter, outside this core layer — it would need
``eidos.agents.ModelPort``) will need, mirroring ``ModelResult``'s own total shape, not a broader taxonomy invented
in passing.

**``structural_cost`` is a tuple, never a scalar** (D-188): ``(total capability occurrences, stage count)``. No
weighting, no quality judgment, no fabricated score — CLAUDE.md's "no fabricated numbers" applies exactly as hard
here as anywhere else. ``DeterministicSelector`` orders candidates by this tuple with ``min()``, whose stability
(the first minimal element in iteration order wins a tie) is what preserves candidate-generation order on an exact
structural tie, with no separate tie-break code needed.
"""

from enum import StrEnum
from typing import Protocol

from pydantic import Field

from eidos.contracts import EidosModel, StrategyId, TaskGenome

from .strategy import Strategy


def structural_cost(strategy: Strategy) -> tuple[int, int]:
    """``(total capability occurrences, stage count)`` — the only facts a ``Strategy`` itself carries that compare
    structurally across candidates (D-188). Not a score: a tuple, compared lexicographically, never weighted."""
    total_capabilities = sum(len(stage.capabilities) for stage in strategy.stages)
    return total_capabilities, len(strategy.stages)


class SelectedCandidate(EidosModel):
    """A ``Selector``'s claim: this candidate, by id. Not yet admitted — ``selection.select_strategy`` validates it
    against the actual candidate set before anything is treated as selected."""

    strategy_id: StrategyId


class SelectorFailureKind(StrEnum):
    """Closed set of reasons a ``Selector`` itself could not produce a choice. See the module docstring for why
    this is a narrower, separate vocabulary from ``ModelFailureKind`` rather than an import of it."""

    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    MALFORMED_CHOICE = "malformed_choice"


class SelectorFailure(EidosModel):
    """A ``Selector`` that could not produce a choice. Returned, never raised — mirrors ``ModelFailure``'s own
    total-function discipline (D-135), including its ``Field(min_length=1)`` convention for a failure message."""

    kind: SelectorFailureKind
    message: str = Field(min_length=1)


SelectorChoice = SelectedCandidate | SelectorFailure


class Selector(Protocol):
    """Proposes one candidate, by id, from ``candidates`` — never returns a ``Strategy`` value, never invents an
    id outside the set (that boundary is enforced by ``selection.select_strategy``, not trusted here)."""

    def select(self, candidates: tuple[Strategy, ...], task_genome: TaskGenome) -> SelectorChoice: ...


class DeterministicSelector:
    """The reference ``Selector`` (D-188). No I/O, no clock, no randomness, no model call: a pure function of
    ``candidates`` alone (``task_genome`` is accepted, per the ``Selector`` protocol's own shape, but not read —
    every fact this rule needs already lives on ``Strategy`` itself). Never mutates ``candidates``.

    Chooses the structurally cheapest candidate: fewest total capability occurrences, then fewest stages, then
    original candidate-generation order on an exact tie (``min()``'s own stability — the first minimal element in
    iteration order wins, so no separate tie-break code is needed).
    """

    def select(self, candidates: tuple[Strategy, ...], task_genome: TaskGenome) -> SelectorChoice:
        cheapest = min(candidates, key=structural_cost)
        return SelectedCandidate(strategy_id=cheapest.strategy_id)
