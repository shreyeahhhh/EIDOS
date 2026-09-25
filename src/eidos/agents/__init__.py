"""Agents and the model seam — milestone V0.4.

The model seam (D-135), the artifact model and in-memory store (D-137, D-145), the Research and Analysis agents and the
deterministic Verification Agent (D-138, D-146). The dispatcher and the single-pass runner arrive in a later V0.4 step.

    from eidos.agents import ModelPort, ModelRequest, ModelSettings, GenerationParameters
    from eidos.agents import Artifact, InMemoryArtifactStore

Constraints (the repository rules, §8; D-135, D-140):

- Vendor-free: no model, provider or SDK name appears here. Adapters live in ``eidos.providers``, the only
  place a vendor name may appear; this package never imports them.
- No I/O, no network, no clock, no randomness. Agents are read-only with no tools (D-140). The tool seam (``ToolPort`` and its typed request,
  result and failure, D-203) exists from V1.2 Step 2; no agent uses it yet.
- Core layers (contracts, validation, compiler, runtime, backends) never import this package.
"""

from .analysis import AnalysisAgent
from .artifacts import Artifact, ArtifactConflict, ArtifactStore, InMemoryArtifactStore
from .base import STEP_ID_REUSED, SUPPORTED_CONTENT_TYPES, WorkAgent, artifact_ref_for, cited_refs, refuse_a_reused_step
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
from .research import ResearchAgent
from .tool import (
    ToolArgument,
    ToolDocument,
    ToolFailure,
    ToolFailureKind,
    ToolOutcome,
    ToolPort,
    ToolRequest,
    ToolResult,
    bound_result,
)
from .verification import (
    NOT_EVALUATED_CLAUSES,
    Rule,
    RuleOutcome,
    RuleResult,
    VerificationAgent,
    VerificationReport,
)

__all__ = [
    "AnalysisAgent",
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
    "NOT_EVALUATED_CLAUSES",
    "ResearchAgent",
    "Rule",
    "RuleOutcome",
    "RuleResult",
    "STEP_ID_REUSED",
    "SUPPORTED_CONTENT_TYPES",
    "ToolArgument",
    "ToolDocument",
    "ToolFailure",
    "ToolFailureKind",
    "ToolOutcome",
    "ToolPort",
    "ToolRequest",
    "ToolResult",
    "VerificationAgent",
    "VerificationReport",
    "WorkAgent",
    "artifact_ref_for",
    "bound_result",
    "cited_refs",
    "refuse_a_reused_step",
]
