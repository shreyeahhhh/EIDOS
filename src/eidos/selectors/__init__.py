"""eidos.selectors — Selector implementations that need a dependency the core eidos.planning layer cannot have
(decisions.md D-190 to D-193, D-198; V0.8 Step 5, V1.0 Step 4).

A narrow adapter package, sibling to ``eidos.providers`` (adapts a vendor to ``ModelPort``) and ``eidos.backends``
(adapts a workflow library to the runtime's executor port): each one adapts a dependency the core
``eidos.planning`` layer cannot have to the existing ``eidos.planning.selector.Selector`` Protocol. Neither
defines a new abstraction — each simply implements the Protocol V0.8 Step 2 already defined, exactly as the core
layer's own deterministic reference implementation does.

    from eidos.selectors import ModelAssistedSelector, ExperienceInformedSelector

``ModelAssistedSelector`` adapts ``eidos.agents.ModelPort`` (V0.8 Step 5). ``ExperienceInformedSelector`` adapts
``eidos.memory.ExperienceStore`` (V1.0 Step 4): it prefers candidates with directly observed, verified-successful
historical experience, deferring entirely to its own injected fallback selector when no candidate has any
relevant history at all — no ambient default, no automatic scoring, no embeddings.

Not here yet: any automatic fallback *between* these two adapters (each is independent, D-193's discipline
extended one selector further), a possible future scoring-based selector implementation of the same Protocol
(not integrated, not assumed), and any recording of raw prompts or responses beyond the one call each makes.
"""

from .experience_informed import ExperienceInformedSelector
from .model_assisted import ModelAssistedSelector

__all__ = ["ExperienceInformedSelector", "ModelAssistedSelector"]
