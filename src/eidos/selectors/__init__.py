"""eidos.selectors — Selector implementations that need a dependency the core eidos.planning layer cannot have
(decisions.md D-190 to D-193; V0.8 Step 5).

A narrow adapter package, sibling to ``eidos.providers`` (adapts a vendor to ``ModelPort``) and ``eidos.backends``
(adapts a workflow library to the runtime's executor port): this one adapts ``eidos.agents.ModelPort`` to the
existing ``eidos.planning.selector.Selector`` Protocol. It defines no new abstraction — ``ModelAssistedSelector``
simply implements the Protocol V0.8 Step 2 already defined, exactly as the core layer's own deterministic
reference implementation does.

    from eidos.selectors import ModelAssistedSelector

Not here yet: any automatic fallback to the deterministic reference selector (D-193), a possible future
scoring-based selector implementation of the same Protocol (not integrated, not assumed), and any recording of
raw prompts or responses beyond the one call each makes.
"""

from .model_assisted import ModelAssistedSelector

__all__ = ["ModelAssistedSelector"]
