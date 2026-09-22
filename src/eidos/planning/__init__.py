"""eidos.planning — candidate execution strategies (decisions.md D-178 to D-182; V0.7 Step 2).

A new core layer, joining ``eidos.contracts``, ``eidos.validation``, ``eidos.compiler``, ``eidos.runtime`` and
``eidos.state``: deterministic, no I/O, no clock, no hidden state, no model/vendor/tool name (invariant 9), no
``AgentId`` (invariant 11 applied one level earlier than ``Plan``, D-179).

V0.7 Step 2 is the data contract alone — ``Strategy``, ``StrategyStage``, ``VerificationPosture``:

    from eidos.planning import Strategy, StrategyStage, VerificationPosture

Not here yet (later V0.7 steps): ``CandidateGenerator``, feasibility filtering (D-180), Strategy-to-Plan
expansion, or Strategy selection (V0.8).
"""

from .strategy import Strategy, StrategyStage, VerificationPosture

__all__ = [
    "Strategy",
    "StrategyStage",
    "VerificationPosture",
]
