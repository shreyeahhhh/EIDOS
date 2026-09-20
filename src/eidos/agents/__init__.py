"""Agents and the model seam — milestone V0.4.

Shipped so far: the model seam (D-135, Step 3) and the artifact model and in-memory store (D-137, D-145, Step 5). The three
agents and the verifier arrive in a later V0.4 step, and this docstring is updated as each one does.

    from eidos.agents import ModelPort, ModelRequest, ModelSettings, GenerationParameters
    from eidos.agents import Artifact, InMemoryArtifactStore

Constraints (the repository rules, §8; D-135, D-140):

- Vendor-free: no model, provider or SDK name appears here. Adapters live in ``eidos.providers``, the only
  place a vendor name may appear; this package never imports them.
- No I/O, no network, no clock, no randomness. Agents are read-only with no tools (D-140).
- Core layers (contracts, validation, compiler, runtime, backends) never import this package.
"""

from .artifacts import Artifact, ArtifactConflict, ArtifactStore, InMemoryArtifactStore
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
    "Artifact",
    "ArtifactConflict",
    "ArtifactStore",
    "GenerationParameters",
    "InMemoryArtifactStore",
    "MeasuredFacts",
    "ModelFailure",
    "ModelFailureKind",
    "ModelPort",
    "ModelRequest",
    "ModelResponse",
    "ModelResult",
    "ModelSettings",
]
