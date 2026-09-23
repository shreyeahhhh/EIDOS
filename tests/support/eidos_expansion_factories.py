"""Minimal test doubles for ``eidos.expansion`` tests (decisions.md D-194, D-195; V0.9 Step 2).

Mirrors ``eidos_planning_factories.py``'s own ``FixedStrategyIdSource`` discipline one layer up: fixed ids only,
nothing here reads the wall clock or draws a random identifier.
"""

from uuid import UUID

from eidos.contracts import PlanId


def make_plan_id(number: int = 1) -> PlanId:
    return PlanId(UUID(int=800_000 + number))


class FixedPlanIdSource:
    """A deterministic ``PlanIdSource`` test double: hands out ``make_plan_id(1)``, ``(2)``, ... in order."""

    def __init__(self, start: int = 1):
        self._next = start

    def next_plan_id(self) -> PlanId:
        plan_id = make_plan_id(self._next)
        self._next += 1
        return plan_id
