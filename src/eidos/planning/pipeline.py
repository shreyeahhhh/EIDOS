"""``generate_candidate_strategies`` — the orchestration boundary (decisions.md D-178 to D-182; V0.7 Steps 3 and 4).

**Why this exists at all ("only if genuinely required"):** three concerns apply to *any* ``CandidateGenerator``,
not only the reference one, so none belongs duplicated inside every implementation: structural deduplication (a
generator should not have to reimplement "what counts as the same shape" — ``generator.py`` already gates the
obvious cases, but this is the backstop for any generator, including a future one this module has never seen),
identity (``strategy_id`` is drawn *here*, never inside the deterministic core, mirroring
``eidos.recording.ports``'s injected ``Clock``/``IdSource`` discipline, D-158 item 3, one layer earlier — an
injected ``StrategyIdSource`` Protocol, not a new identity mechanism), and, as of Step 4, feasibility — every
identity-stamped candidate is checked with ``feasibility.check_feasibility`` before it may count toward
``max_candidates``. Governance never depends on the generator behaving: an infeasible candidate, from the
reference generator or a future untrusted one, is reported in ``rejected`` with its full ``FeasibilityReport``,
never silently dropped and never raised.

**Order of operations, and why:** generate → deduplicate (structural, generator-agnostic) → stamp identity on
*every* distinct shape (not only the ones that will turn out feasible — a candidate's ``strategy_id`` should be
stable whether or not it survives feasibility, and stamping first means ``check_feasibility`` always receives a
real, fully-identified ``Strategy``, exactly the type its own public signature names) → check feasibility on every
one → split into feasible and infeasible → cap the **feasible** ones at ``max_candidates`` (an infeasible candidate
never occupies a slot in the bounded set) → ``truncated`` accounts for exactly what the cap removed from the
feasible pool. Step 4 replaces Step 3's own narrow, ad hoc capability-only re-check with this: it was always a
placeholder for the real feasibility gate D-180 had already approved as the next step, not a second, competing
check to keep running alongside it.

**``max_candidates`` is required, with no default** (D-181): a negative value is rejected outright (slicing with a
negative count would silently drop from the end rather than truncate, which is not what a caller asking for "no
more than N" means). The reference generator never overproduces to make truncation interesting, but the mechanism
itself is generator-agnostic and must not pad.
"""

from typing import Protocol

from eidos.contracts import MissionId, ReliabilityContract, StrategyId, TaskGenome
from eidos.validation.limits import SystemLimits

from .feasibility import check_feasibility
from .generator import CandidateGenerator
from .results import CandidateGenerationResult, RejectedCandidate
from .strategy import Strategy, StrategyShape


class StrategyIdSource(Protocol):
    """Draws one ``StrategyId`` per distinct candidate. Injected, never read inside ``generator.py``'s deterministic
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


def _stamp(shape: StrategyShape, *, task_genome: TaskGenome, mission_id: MissionId, ids: StrategyIdSource) -> Strategy:
    return Strategy(
        tenant_id=task_genome.tenant_id,
        mission_id=mission_id,
        strategy_id=ids.next_strategy_id(),
        stages=shape.stages,
        verification=shape.verification,
        rationale=shape.rationale,
    )


def generate_candidate_strategies(
    generator: CandidateGenerator,
    task_genome: TaskGenome,
    *,
    mission_id: MissionId,
    reliability_contract: ReliabilityContract,
    limits: SystemLimits,
    max_candidates: int,
    ids: StrategyIdSource,
) -> CandidateGenerationResult:
    """Generate, deduplicate, identity-stamp and feasibility-filter — capped at ``max_candidates`` **feasible**
    candidates, never padded.

    No ranking, no "best": candidate order is generation order, nothing more (candidate generation is not
    selection, V0.8, not built here).
    """
    if max_candidates < 0:
        raise ValueError(f"max_candidates must be >= 0, got {max_candidates}")

    distinct = _dedupe(generator.generate(task_genome))
    stamped = [_stamp(shape, task_genome=task_genome, mission_id=mission_id, ids=ids) for shape in distinct]

    feasible: list[Strategy] = []
    rejected: list[RejectedCandidate] = []
    for strategy in stamped:
        report = check_feasibility(strategy, task_genome, reliability_contract, limits)
        if report.feasible:
            feasible.append(strategy)
        else:
            rejected.append(RejectedCandidate(strategy=strategy, report=report))

    candidates = tuple(feasible[:max_candidates])
    truncated = len(feasible) - len(candidates)

    return CandidateGenerationResult(candidates=candidates, rejected=tuple(rejected), truncated=truncated)
