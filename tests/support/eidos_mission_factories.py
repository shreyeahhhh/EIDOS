"""Pure mission and plan helpers for scenario-style tests: fixed identifiers, no executor, no backend.

They live apart from ``eidos_scenario_factories`` (which drives both executors and so needs the LangGraph extra) so that unit tests can build a
mission and a plan without importing a backend. Core unit tests must run with LangGraph blocked (decisions.md D-116).
"""

from uuid import UUID

from eidos.contracts import (
    CapabilityId,
    ExecutionId,
    MissionId,
    MissionState,
    Plan,
    PlanId,
    PlanStepKind,
    ReliabilityContractId,
    StepId,
    TenantId,
)

from eidos_factories import (
    make_agent_step,
    make_control_step,
    make_mission_state,
    make_plan,
    make_reliability_contract,
    make_task_genome,
)

CAPABILITIES = ("research", "analysis")


def make_mission(*, capabilities: tuple[str, ...] = CAPABILITIES, seed: int = 1, **contract_overrides) -> MissionState:
    """A real, valid MissionState with fixed identifiers. ``contract_overrides`` shape its reliability contract."""
    base = seed * 1000
    tenant_id = TenantId(UUID(int=base + 1))
    contract = make_reliability_contract(
        tenant_id=tenant_id, contract_id=ReliabilityContractId(UUID(int=base + 4)), **contract_overrides
    )
    genome = make_task_genome(
        contract=contract, required_capabilities=tuple(CapabilityId(name) for name in capabilities)
    )
    return make_mission_state(
        tenant_id=tenant_id,
        mission_id=MissionId(UUID(int=base + 2)),
        execution_id=ExecutionId(UUID(int=base + 3)),
        reliability_contract=contract,
        task_genome=genome,
        plans=(),  # V0.3 has no reducer, so nothing records plans into the state
        active_plan_id=None,
    )


def make_mission_plan(
    state: MissionState,
    spec: dict[str, str],
    *,
    verify: tuple[str, ...] = (),
    controls: dict[str, PlanStepKind] | None = None,
    capability_of: dict[str, str] | None = None,
    version: int = 1,
    parent: Plan | None = None,
    reason: str | None = None,
    plan_number: int | None = None,
) -> Plan:
    """A plan for ``state``'s mission from ``{"step": "dep1 dep2"}`` in dict order.

    Names in ``verify`` are ``VERIFY`` steps and names in ``controls`` are control steps of the kind given;
    every other step is a work step requesting ``capability_of[name]`` (default ``research``). ``parent`` and
    ``reason`` set the lineage a replan carries.
    """
    capability_of = capability_of or {}
    kind_of = {name: PlanStepKind.VERIFY for name in verify} | (controls or {})
    steps = []
    for name, deps in spec.items():
        depends_on = tuple(StepId(d) for d in deps.split())
        if name in kind_of:
            steps.append(make_control_step(step_id=StepId(name), depends_on=depends_on, kind=kind_of[name]))
        else:
            steps.append(
                make_agent_step(
                    step_id=StepId(name),
                    depends_on=depends_on,
                    capability=CapabilityId(capability_of.get(name, "research")),
                )
            )
    number = plan_number if plan_number is not None else version
    return make_plan(
        tenant_id=state.tenant_id,
        mission_id=state.mission_id,
        plan_id=PlanId(UUID(int=state.mission_id.int + 100 * number)),
        version=version,
        parent_plan_id=parent.plan_id if parent is not None else None,
        replan_reason=reason,
        steps=tuple(steps),
    )
