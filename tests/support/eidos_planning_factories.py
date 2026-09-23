"""Minimal valid-object factories for ``eidos.planning`` tests (decisions.md D-178 to D-189; V0.7 Steps 2 to 5;
V0.8 Step 2).

Mirrors ``eidos_factories.py``'s own discipline: every factory returns a fresh, structurally valid instance so a
test starts from something known-good and mutates exactly the field under test. Fixed ids only — nothing here
reads the wall clock or draws a random identifier. ``make_system_limits``/``make_reliability_contract`` are the
existing V0.2 test fixtures (deliberately distinct per-dimension values, decisions.md D-103 point 4) — reused, not
duplicated, per D-180's own "reuse the existing contracts" instruction.
"""

from uuid import UUID

from eidos.contracts import CapabilityId, MissionId, StrategyId, TenantId
from eidos.planning import (
    CandidateGenerationResult,
    RuleBasedCandidateGenerator,
    Strategy,
    StrategyStage,
    VerificationPosture,
    generate_candidate_strategies,
)
from eidos.validation import SystemLimits

from eidos_factories import make_reliability_contract, make_task_genome
from eidos_validation_factories import make_system_limits

TENANT = TenantId(UUID(int=101))
MISSION = MissionId(UUID(int=102))

GENEROUS_CONTRACT = make_reliability_contract(tenant_id=TENANT)
GENEROUS_LIMITS: SystemLimits = make_system_limits()


def make_strategy_id(number: int = 1) -> StrategyId:
    return StrategyId(UUID(int=900_000 + number))


def make_strategy_stage(*capabilities: str) -> StrategyStage:
    names = capabilities or ("research",)
    return StrategyStage(capabilities=tuple(CapabilityId(name) for name in names))


def make_strategy(**overrides) -> Strategy:
    fields = dict(
        tenant_id=TENANT,
        mission_id=MISSION,
        strategy_id=make_strategy_id(),
        stages=(make_strategy_stage("research"),),
        verification=VerificationPosture.FINAL,
        rationale="sequential: minimizes concurrent agent calls",
    )
    fields.update(overrides)
    return Strategy(**fields)


def genome_with(*capabilities: str, **overrides):
    """A ``TaskGenome`` requiring exactly ``capabilities`` (in the order given, duplicates allowed on purpose —
    some tests exercise the generator's own deduplication)."""
    return make_task_genome(required_capabilities=tuple(CapabilityId(c) for c in capabilities), **overrides)


def strategy_with_stages(number: int, *stage_capabilities: tuple, **overrides) -> Strategy:
    """A ``Strategy`` with id ``make_strategy_id(number)`` and one stage per entry in ``stage_capabilities``
    (each entry a tuple of capability names) — a convenience for selector/selection tests that build several
    strategies with specific, comparable shapes."""
    stages = tuple(make_strategy_stage(*caps) for caps in stage_capabilities) or (make_strategy_stage("research"),)
    fields = dict(strategy_id=make_strategy_id(number), stages=stages)
    fields.update(overrides)
    return make_strategy(**fields)


class FixedStrategyIdSource:
    """A deterministic ``StrategyIdSource`` test double: hands out ``make_strategy_id(1)``, ``(2)``, ... in order."""

    def __init__(self, start: int = 1):
        self._next = start

    def next_strategy_id(self) -> StrategyId:
        strategy_id = make_strategy_id(self._next)
        self._next += 1
        return strategy_id


def generate_feasible(genome, *, limits: SystemLimits | None = None, contract=None, max_candidates: int = 3) -> CandidateGenerationResult:
    """``generate_candidate_strategies`` over the reference generator and the existing fixtures (V0.8 Step 6
    integration tests) — a thin composition of two already-public functions, not a new production abstraction:
    ``CandidateGenerationResult.candidates`` is already exactly the ``tuple[Strategy, ...]``
    ``selection.select_strategy`` expects, so nothing new needed to be built to connect them."""
    return generate_candidate_strategies(
        RuleBasedCandidateGenerator(),
        genome,
        mission_id=MISSION,
        reliability_contract=contract or GENEROUS_CONTRACT,
        limits=limits or GENEROUS_LIMITS,
        max_candidates=max_candidates,
        ids=FixedStrategyIdSource(),
    )
