"""eidos.planning — candidate execution strategies (decisions.md D-178 to D-182; V0.7 Steps 2 and 3).

A core layer, joining ``eidos.contracts``, ``eidos.validation``, ``eidos.compiler``, ``eidos.runtime`` and
``eidos.state``: deterministic, no I/O, no clock, no hidden state, no model/vendor/tool name (invariant 9), no
``AgentId`` (invariant 11 applied one level earlier than ``Plan``, D-179). Still depends only on
``eidos.contracts`` — feasibility filtering (D-180), the only approved reason to add ``eidos.validation``, is not
built yet.

Step 2 is the data contract — ``Strategy``, ``StrategyStage``, ``VerificationPosture``. Step 3 adds the bounded
candidate-generation boundary: the Jev-inspired principle translated to strategy level — EIDOS constructs the
feasible decision space; a future model may choose from it, but never defines what is valid.

    from eidos.planning import (
        CandidateGenerationResult, CandidateGenerator, RejectedCandidate, RuleBasedCandidateGenerator,
        Strategy, StrategyIdSource, StrategyShape, StrategyStage, VerificationPosture,
        generate_candidate_strategies,
    )

Not here yet: feasibility filtering (D-180: ``SystemLimits``/``ReliabilityContract`` shape and resource ceilings —
distinct from this step's own, narrower capability-membership check), Strategy-to-Plan expansion, or Strategy
selection (V0.8).
"""

from .generator import CandidateGenerator, RuleBasedCandidateGenerator
from .pipeline import StrategyIdSource, generate_candidate_strategies
from .results import CandidateGenerationResult, RejectedCandidate
from .strategy import Strategy, StrategyShape, StrategyStage, VerificationPosture

__all__ = [
    "CandidateGenerationResult",
    "CandidateGenerator",
    "RejectedCandidate",
    "RuleBasedCandidateGenerator",
    "Strategy",
    "StrategyIdSource",
    "StrategyShape",
    "StrategyStage",
    "VerificationPosture",
    "generate_candidate_strategies",
]
