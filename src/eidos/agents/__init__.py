"""Agents and the model seam — milestone V0.4.

The model seam (D-135), the artifact model and in-memory store (D-137, D-145), the Research and Analysis agents and the
deterministic Verification Agent (D-138, D-146). The dispatcher and the single-pass runner arrive in a later V0.4 step.

    from eidos.agents import ModelPort, ModelRequest, ModelSettings, GenerationParameters
    from eidos.agents import Artifact, InMemoryArtifactStore

Constraints (the repository rules, §8; D-135, D-140):

- Vendor-free: no model, provider or SDK name appears here. Adapters live in ``eidos.providers``, the only
  place a vendor name may appear; this package never imports them.
- No I/O, no network, no clock, no randomness. Agents are read-only (D-140). The tool seam (``ToolPort`` and its typed request, result and
  failure, D-203) exists from V1.2 Step 2; from Step 4 the Research agent may be given tool access through ``ToolAccess``, whose implementation
  ``ToolGate`` admits a call before any port is reached (D-203, D-207). No agent knows how a port reaches its tool.
- The knowledge boundary (V1.3, D-222, D-228): ``evidence_ledger`` and ``knowledge_gate`` are the two modules here that depend on ``eidos.knowledge``, through the package root
  only, each by a pinned set of names; from Step 7 the Research agent may be given knowledge access through ``KnowledgeAccess``, whose implementation ``KnowledgeGate`` builds the request
  from the knowledge base's own bounds and turns an answer into ledger records and citable artifacts. ``eidos.knowledge`` never imports this package.
- Core layers (contracts, validation, compiler, runtime, backends) never import this package.
"""

from .analysis import AnalysisAgent
from .artifacts import Artifact, ArtifactConflict, ArtifactStore, InMemoryArtifactStore
from .base import STEP_ID_REUSED, SUPPORTED_CONTENT_TYPES, WorkAgent, artifact_ref_for, cited_refs, refuse_a_reused_step
from .evidence_ledger import ArtifactEvidence, EvidenceLedger, resolve_supplied_evidence
from .knowledge_gate import EVIDENCE_CONTENT_TYPE, KnowledgeAccess, KnowledgeBaseDescriptor, KnowledgeGate, KnowledgeGateKind, KnowledgeGateOutcome
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
from .tool_gate import (
    TOOL_DOCUMENT_CONTENT_TYPE,
    ToolAccess,
    ToolGate,
    ToolGateKind,
    ToolGateOutcome,
    parse_tool_document_ref,
    tool_document_ref,
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
    "ArtifactEvidence",
    "ArtifactStore",
    "EVIDENCE_CONTENT_TYPE",
    "EvidenceLedger",
    "GenerationParameters",
    "InMemoryArtifactStore",
    "KnowledgeAccess",
    "KnowledgeBaseDescriptor",
    "KnowledgeGate",
    "KnowledgeGateKind",
    "KnowledgeGateOutcome",
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
    "TOOL_DOCUMENT_CONTENT_TYPE",
    "ToolAccess",
    "ToolArgument",
    "ToolDocument",
    "ToolFailure",
    "ToolFailureKind",
    "ToolGate",
    "ToolGateKind",
    "ToolGateOutcome",
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
    "parse_tool_document_ref",
    "refuse_a_reused_step",
    "resolve_supplied_evidence",
    "tool_document_ref",
]
