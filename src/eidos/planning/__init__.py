"""eidos.planning — candidate execution strategies and their selection (decisions.md D-178 to D-189; V0.7 Steps 2
to 5; V0.8 Step 2).

A core layer, joining ``eidos.contracts``, ``eidos.validation``, ``eidos.compiler``, ``eidos.runtime`` and
``eidos.state``: deterministic, no I/O, no clock, no hidden state, no model/vendor/tool name (invariant 9), no
``AgentId`` (invariant 11 applied one level earlier than ``Plan``, D-179). Depends only on ``eidos.contracts`` and
``eidos.validation.limits`` (``SystemLimits``, D-180's own approved reuse) — never ``eidos.validation.stages``/
``.pipeline`` (the Plan validator) and never ``eidos.agents`` (``ModelPort``, D-135) — a model-assisted ``Selector``
is a future adapter *outside* this core layer, not built here.

V0.7 (Steps 2–5): the `Strategy` data contract; the bounded, deterministic `CandidateGenerator` boundary; the
feasibility gate; the three remaining architectural questions (D-183–D-185) — closed as scoped.

V0.8 Step 2: the selection boundary. `Selector` proposes a candidate by id only, never a `Strategy` value and
never Plan DSL (D-186); `DeterministicSelector` is the reference implementation, choosing the structurally
cheapest candidate by a lexicographic rule, never a scalar score (D-188); `select_strategy` is the orchestration
boundary that handles the zero/one-candidate edge cases and is the one place a selector's proposal is actually
admitted or refused, by candidate-set membership (D-187). `SelectionResult` is a typed, replay-ready value only —
no `SelectionId`, no `MissionEvent`, no Strategy Memory (D-189).

    from eidos.planning import (
        CandidateGenerationResult, CandidateGenerator, DeterministicSelector, FeasibilityCheck,
        FeasibilityReport, FeasibilityViolation, FeasibilityViolationCode, RejectedCandidate,
        RuleBasedCandidateGenerator, SelectedCandidate, SelectionOutcome, SelectionResult, Selector,
        SelectorChoice, SelectorFailure, SelectorFailureKind, Strategy, StrategyIdSource, StrategyShape,
        StrategyStage, VerificationPosture,
        check_feasibility, generate_candidate_strategies, select_strategy, structural_cost,
    )

Not here yet: Strategy-to-Plan expansion, Strategy Memory, adaptive learning, ranking infrastructure, or a
model-assisted `Selector` implementation.
"""

from .feasibility import (
    FeasibilityCheck,
    FeasibilityReport,
    FeasibilityViolation,
    FeasibilityViolationCode,
    check_feasibility,
)
from .generator import CandidateGenerator, RuleBasedCandidateGenerator
from .pipeline import StrategyIdSource, generate_candidate_strategies
from .results import (
    CandidateGenerationResult,
    RejectedCandidate,
    SelectionOutcome,
    SelectionResult,
)
from .selection import select_strategy
from .selector import (
    DeterministicSelector,
    SelectedCandidate,
    Selector,
    SelectorChoice,
    SelectorFailure,
    SelectorFailureKind,
    structural_cost,
)
from .strategy import Strategy, StrategyShape, StrategyStage, VerificationPosture

__all__ = [
    "CandidateGenerationResult",
    "CandidateGenerator",
    "DeterministicSelector",
    "FeasibilityCheck",
    "FeasibilityReport",
    "FeasibilityViolation",
    "FeasibilityViolationCode",
    "RejectedCandidate",
    "RuleBasedCandidateGenerator",
    "SelectedCandidate",
    "SelectionOutcome",
    "SelectionResult",
    "Selector",
    "SelectorChoice",
    "SelectorFailure",
    "SelectorFailureKind",
    "Strategy",
    "StrategyIdSource",
    "StrategyShape",
    "StrategyStage",
    "VerificationPosture",
    "check_feasibility",
    "generate_candidate_strategies",
    "select_strategy",
    "structural_cost",
]
