"""Agents and the model seam — milestone V0.4.

Step 3 ships only the model seam (decisions.md D-135). The three agents, the artifact store and the verifier
arrive in later V0.4 steps, and this docstring is updated as each one does.

    from eidos.agents import ModelPort, ModelRequest, ModelSettings, GenerationParameters

Constraints (the repository rules, §8; D-135, D-140):

- Vendor-free: no model, provider or SDK name appears here. Adapters live in ``eidos.providers``, the only
  place a vendor name may appear; this package never imports them.
- No I/O, no network, no clock, no randomness. Agents are read-only with no tools (D-140).
- Core layers (contracts, validation, compiler, runtime, backends) never import this package.
"""

from .model import (
    GenerationParameters,
    MeasuredFacts,
    ModelFailure,
    ModelFailureKind,
    ModelPort,
    ModelRequest,
    ModelResponse,
    ModelResult,
    ModelSettings,
)

__all__ = [
    "GenerationParameters",
    "MeasuredFacts",
    "ModelFailure",
    "ModelFailureKind",
    "ModelPort",
    "ModelRequest",
    "ModelResponse",
    "ModelResult",
    "ModelSettings",
]
