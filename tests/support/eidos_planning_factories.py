"""Minimal valid-object factories for ``eidos.planning`` tests (decisions.md D-178 to D-182; V0.7 Step 2).

Mirrors ``eidos_factories.py``'s own discipline: every factory returns a fresh, structurally valid instance so a
test starts from something known-good and mutates exactly the field under test. Fixed ids only — nothing here
reads the wall clock or draws a random identifier.
"""

from uuid import UUID

from eidos.contracts import CapabilityId, MissionId, StrategyId, TenantId
from eidos.planning import Strategy, StrategyStage, VerificationPosture

TENANT = TenantId(UUID(int=101))
MISSION = MissionId(UUID(int=102))


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
