"""``generate_candidate_strategies`` — the orchestration boundary (decisions.md D-178 to D-182; V0.7 Step 3).

**Why this exists at all ("only if genuinely required"):** two concerns apply to *any* ``CandidateGenerator``, not
only the reference one, so neither belongs duplicated inside every implementation: structural deduplication (a
generator should not have to reimplement "what counts as the same shape" — ``generator.py`` already gates the
obvious cases, but this is the backstop for any generator, including a future one this module has never seen) and
identity — ``strategy_id`` is drawn *here*, never inside the deterministic core (``generator.py``), mirroring
``eidos.recording.ports``'s injected ``Clock``/``IdSource`` discipline (D-158 item 3) one layer earlier. This
module does not invent a new identity mechanism; it reuses the existing one's *shape* — an injected source, a
``StrategyIdSource`` Protocol — scoped to this package rather than importing ``eidos.recording`` itself, which
would reach a higher, adapter layer from a core one (backwards).

**The capability boundary is re-checked here too, not only trusted from the generator** (the same "check twice"
discipline ``eidos.validation.stages.check_dependencies`` already established for ``Plan``): every shape's every
stage is checked against ``task_genome.required_capabilities`` — the same, only rule this step enforces; this is
*not* D-180's future feasibility filtering (no ``SystemLimits``/``ReliabilityContract`` shape or resource ceiling
is checked here — that is a separate, later step). A shape that fails is reported in ``rejected``, never silently
dropped and never raised: an untrusted or future LLM-assisted generator naming an unavailable capability is an
*expected* case to defend against, not a programming error.

**``max_candidates`` is required, with no default** (D-181): a negative value is rejected outright (slicing with a
negative count would silently drop from the end rather than truncate, which is not what a caller asking for "no
more than N" means). The reference generator never overproduces to make truncation interesting, but the mechanism
itself is generator-agnostic and must not pad, so ``truncated`` accounts for exactly the difference the cap made.
"""

from typing import Protocol

from eidos.contracts import MissionId, StrategyId, TaskGenome

from .generator import CandidateGenerator
from .results import CandidateGenerationResult, RejectedCandidate
from .strategy import Strategy, StrategyShape


class StrategyIdSource(Protocol):
    """Draws one ``StrategyId`` per accepted candidate. Injected, never read inside ``generator.py``'s deterministic
    core (D-182; mirrors ``eidos.recording.ports.IdSource`` one layer earlier — no real, uuid-drawing implementation
    lives in this core-layer package; a caller supplies one, exactly as a caller supplies a real ``IdSource`` to
    ``eidos.recording`` today)."""

    def next_strategy_id(self) -> StrategyId: ...


def _dedupe(shapes: tuple[StrategyShape, ...]) -> tuple[StrategyShape, ...]:
    """The first occurrence of each distinct ``(stages, verification)`` wins; ``rationale`` is not part of identity —
    two shapes with the same structure and a different explanation are still the same strategy (module docstring)."""
    seen: dict[tuple, StrategyShape] = {}  # insertion-ordered; deterministic given a deterministic input order
    for shape in shapes:
        key = (shape.stages, shape.verification)
        if key not in seen:
            seen[key] = shape
    return tuple(seen.values())


def _capability_violation(shape: StrategyShape, allowed: frozenset) -> str | None:
    for stage in shape.stages:
        for capability in stage.capabilities:
            if capability not in allowed:
                return f"stage names capability {capability!r}, which is not in the mission's required_capabilities"
    return None


def generate_candidate_strategies(
    generator: CandidateGenerator,
    task_genome: TaskGenome,
    *,
    mission_id: MissionId,
    max_candidates: int,
    ids: StrategyIdSource,
) -> CandidateGenerationResult:
    """Generate, deduplicate, capability-check and identity-stamp — capped at ``max_candidates``, never padded.

    No ranking, no "best": candidate order is generation order, nothing more (candidate generation is not
    selection, V0.8, not built here).
    """
    if max_candidates < 0:
        raise ValueError(f"max_candidates must be >= 0, got {max_candidates}")

    distinct = _dedupe(generator.generate(task_genome))

    allowed = frozenset(task_genome.required_capabilities)  # membership only, never iterated
    accepted: list[StrategyShape] = []
    rejected: list[RejectedCandidate] = []
    for shape in distinct:
        violation = _capability_violation(shape, allowed)
        if violation is None:
            accepted.append(shape)
        else:
            rejected.append(RejectedCandidate(shape=shape, reason=violation))

    capped = accepted[:max_candidates]
    truncated = len(accepted) - len(capped)

    candidates = tuple(
        Strategy(
            tenant_id=task_genome.tenant_id,
            mission_id=mission_id,
            strategy_id=ids.next_strategy_id(),
            stages=shape.stages,
            verification=shape.verification,
            rationale=shape.rationale,
        )
        for shape in capped
    )
    return CandidateGenerationResult(candidates=candidates, rejected=tuple(rejected), truncated=truncated)
