"""``Strategy`` — an execution *shape*, distinct from ``Plan`` (decisions.md D-178, D-179, D-182; V0.7 Step 2).

**A Strategy is not a Plan.** It never carries a ``StepId``, a dependency edge, an ``AgentId``, a model or vendor
identifier, a tool identifier, or a retry/replan field (D-178, D-179). It expresses only the three V0.7 dimensions
D-179 approved: execution topology/parallelism (the ``stages`` shape itself), verification posture, and capability
allocation (which capabilities appear, and how often). A selected strategy may eventually (V0.8+, not built here)
expand into a concrete ``Plan`` — through the unmodified V0.2 validation and V0.3 compiler pipeline, never around it.

**``stages`` is level-structured, not an arbitrary graph.** Each ``StrategyStage`` names the capabilities that run
in parallel within it; stage *i+1* implicitly depends on the *whole* of stage *i*. This is deliberately coarser than
``Plan.steps``/``depends_on`` (D-178's own reason for being a separate, narrower object): a linear chain, a
parallel-then-converge shape and a staged shape (handoff §16's Plan A/B/C) are all expressible as this one
sequence, with no separate "topology" or "parallelism" field needed — both read off the stage shape itself, never
stored twice. An empty ``stages`` tuple is legal, mirroring ``Plan``'s own permissiveness (D-106: empty plans pass).

**A capability may repeat within one stage.** Two parallel calls to the same capability (for example, two
independent research angles) is a legitimate strategy shape — nothing at the Plan level forbids two steps
requesting the same capability either. This is *not* the same question ``AgentDescriptor.capabilities`` answers
(D-134): that field describes which capabilities one agent serves, a set by nature; a stage's capabilities describe
which roles run concurrently, a multiset by nature. ``StrategyStage`` does not deduplicate.

**Verification posture is deliberately narrow.** ``VerificationPosture`` has exactly two members because exactly
one deterministic ``Verifier`` exists (D-133), invoked once, at the end, in every baseline built so far — there is
nothing yet to choose a richer "approach" between. Growing this enum is additive and needs no change to ``Strategy``
itself, whenever a second verification posture becomes real.

**Identity.** ``strategy_id`` is a plain, UUID-backed ``StrategyId`` (D-053's default; D-182) — not a version, and
not the "Strategy signature"/"Strategy Genome" handoff §21/§39 sketch (D-021, still Open and untouched by this).
Strategies are not amended in place the way a ``Plan`` is replanned; a fresh generation round produces fresh ids
for an unrelated candidate set. ``tenant_id``/``mission_id`` follow ``Plan``'s own precedent (D-088) rather than
``TaskGenome``'s: a ``Strategy``, like a ``Plan``, is a self-identifying value that crosses module boundaries
(generator, a future selector, a future Plan-expander), not one embedded permanently inside a single container.

**``StrategyShape`` (V0.7 Step 3): the identity-free content a generator produces.** Step 2 considered and dropped
this split because nothing consumed it yet; ``CandidateGenerator`` (``generator.py``) is that consumer now. It is
exactly ``Strategy`` minus ``tenant_id``/``mission_id``/``strategy_id`` — the deterministic core builds *content*;
identity is stamped on afterward, at the orchestration boundary (``pipeline.py``), mirroring
``eidos.recording.ports``'s injected ``Clock``/``IdSource`` discipline (D-158 item 3) one layer earlier. This is
not a new identity mechanism (nothing here invents one) and it is not a change to the approved ``Strategy``
contract — ``Strategy`` itself is unchanged from Step 2.

**Not built here (later V0.7/V0.8 steps, D-178's own scope line):** feasibility filtering (D-180), Strategy-to-Plan
expansion, and Strategy selection (V0.8).
"""

from enum import StrEnum

from pydantic import Field

from eidos.contracts import CapabilityId, DEFAULT_TENANT_ID, EidosModel, MissionId, StrategyId, TenantId


class VerificationPosture(StrEnum):
    """Whether a strategy ends with a verification gate (decisions.md D-179 item 2)."""

    NONE = "none"
    FINAL = "final"


class StrategyStage(EidosModel):
    """One level of a strategy's execution shape: the capabilities that run in parallel within it."""

    capabilities: tuple[CapabilityId, ...] = Field(min_length=1)


class Strategy(EidosModel):
    """An execution shape a mission might use — not a Plan (decisions.md D-178). See the module docstring."""

    tenant_id: TenantId = Field(default=DEFAULT_TENANT_ID)
    mission_id: MissionId
    strategy_id: StrategyId
    stages: tuple[StrategyStage, ...]
    verification: VerificationPosture
    rationale: str = Field(min_length=1)


class StrategyShape(EidosModel):
    """``Strategy`` minus identity — what a ``CandidateGenerator`` produces (V0.7 Step 3). See the module docstring."""

    stages: tuple[StrategyStage, ...]
    verification: VerificationPosture
    rationale: str = Field(min_length=1)
