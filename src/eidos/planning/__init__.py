"""eidos.planning — candidate execution strategies (decisions.md D-178 to D-182; V0.7 Steps 2 to 4).

A core layer, joining ``eidos.contracts``, ``eidos.validation``, ``eidos.compiler``, ``eidos.runtime`` and
``eidos.state``: deterministic, no I/O, no clock, no hidden state, no model/vendor/tool name (invariant 9), no
``AgentId`` (invariant 11 applied one level earlier than ``Plan``, D-179). As of Step 4 it depends on
``eidos.validation.limits`` too (``SystemLimits``, D-180's own approved reuse) — never ``eidos.validation.stages``
or ``eidos.validation.pipeline``: feasibility filtering is not Plan validation and does not call it.

Step 2 is the data contract — ``Strategy``, ``StrategyStage``, ``VerificationPosture``. Step 3 adds the bounded
candidate-generation boundary: the Jev-inspired principle translated to strategy level — EIDOS constructs the
feasible decision space; a future model may choose from it, but never defines what is valid. Step 4 adds the
feasibility gate itself: three narrower, strategy-level analogues of V0.2's CAPABILITY/COMPLEXITY/RESOURCE stages,
reusing the existing ``SystemLimits``/``ReliabilityContract`` — no new numeric limit anywhere.

    from eidos.planning import (
        CandidateGenerationResult, CandidateGenerator, FeasibilityCheck, FeasibilityReport,
        FeasibilityViolation, FeasibilityViolationCode, RejectedCandidate, RuleBasedCandidateGenerator,
        Strategy, StrategyIdSource, StrategyShape, StrategyStage, VerificationPosture,
        check_feasibility, generate_candidate_strategies,
    )

Not here yet: Strategy-to-Plan expansion, or Strategy selection (V0.8 — the still-open question of whether every
candidate is Plan-validated before selection, or only the one selected, is not resolved here either).
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
from .results import CandidateGenerationResult, RejectedCandidate
from .strategy import Strategy, StrategyShape, StrategyStage, VerificationPosture

__all__ = [
    "CandidateGenerationResult",
    "CandidateGenerator",
    "FeasibilityCheck",
    "FeasibilityReport",
    "FeasibilityViolation",
    "FeasibilityViolationCode",
    "RejectedCandidate",
    "RuleBasedCandidateGenerator",
    "Strategy",
    "StrategyIdSource",
    "StrategyShape",
    "StrategyStage",
    "VerificationPosture",
    "check_feasibility",
    "generate_candidate_strategies",
]
