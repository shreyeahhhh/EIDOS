"""Minimal valid-object factories for V0.1 contract tests.

Every factory returns a fresh, structurally valid instance so a test can
start from something known-good and mutate exactly the field under test —
CLAUDE.md §6: "Write failure-path tests, not only happy paths." Factories
are plain functions, not pytest fixtures, so a single test can build several
differently-broken variants without fixture indirection.
"""

from datetime import datetime, timezone
from uuid import uuid4

from eidos.contracts import (
    AgentId,
    AgentStep,
    AgentTask,
    AutonomyLevel,
    CapabilityId,
    ControlStep,
    EventId,
    ExecutionId,
    MissionEvent,
    MissionEventType,
    MissionId,
    MissionState,
    MissionStatus,
    Plan,
    PlanId,
    PlanStepKind,
    ReliabilityContract,
    ReliabilityContractId,
    RiskLevel,
    TaskGenome,
    TenantId,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def make_reliability_contract(**overrides) -> ReliabilityContract:
    fields = dict(
        tenant_id=TenantId(uuid4()),
        contract_id=ReliabilityContractId(uuid4()),
        min_quality=0.9,
        max_risk_level=RiskLevel.MEDIUM,
        min_independent_evidence=3,
    )
    fields.update(overrides)
    return ReliabilityContract(**fields)


def make_task_genome(*, contract: ReliabilityContract | None = None, **overrides) -> TaskGenome:
    contract = contract or make_reliability_contract()
    fields = dict(
        tenant_id=contract.tenant_id,
        goal="Assess migration readiness",
        required_capabilities=(CapabilityId("research"),),
        risk_level=RiskLevel.MEDIUM,
        autonomy_level=AutonomyLevel.SAFE_READ_ONLY,
        allowed_actions=(),
        reliability_contract_id=contract.contract_id,
    )
    fields.update(overrides)
    return TaskGenome(**fields)


def make_agent_step(step_id: str = "agent_1", depends_on: tuple = (), **overrides) -> AgentStep:
    fields = dict(step_id=step_id, depends_on=depends_on, capability=CapabilityId("research"))
    fields.update(overrides)
    return AgentStep(**fields)


def make_control_step(
    step_id: str = "route_1",
    depends_on: tuple = (),
    kind: PlanStepKind = PlanStepKind.VERIFY,
    **overrides,
) -> ControlStep:
    fields = dict(step_id=step_id, depends_on=depends_on, kind=kind)
    fields.update(overrides)
    return ControlStep(**fields)


def make_plan(*, tenant_id: TenantId | None = None, mission_id: MissionId | None = None, **overrides) -> Plan:
    fields = dict(
        tenant_id=tenant_id or TenantId(uuid4()),
        plan_id=PlanId(uuid4()),
        mission_id=mission_id or MissionId(uuid4()),
        version=1,
        steps=(make_agent_step(),),
    )
    fields.update(overrides)
    return Plan(**fields)


def make_mission_event(**overrides) -> MissionEvent:
    now = utc_now()
    fields = dict(
        event_id=EventId(uuid4()),
        tenant_id=TenantId(uuid4()),
        mission_id=MissionId(uuid4()),
        sequence=1,
        occurred_at=now,
        recorded_at=now,
        type=MissionEventType.MISSION_CREATED,
    )
    fields.update(overrides)
    return MissionEvent(**fields)


def make_agent_task(**overrides) -> AgentTask:
    fields = dict(agent_id=AgentId(uuid4()), status="pending")
    fields.update(overrides)
    return AgentTask(**fields)


_UNSET = object()  # sentinel distinct from an explicitly-passed None


def make_mission_state(
    *,
    tenant_id=_UNSET,
    mission_id=_UNSET,
    task_genome=_UNSET,
    reliability_contract=_UNSET,
    plans=_UNSET,
    active_plan_id=_UNSET,
    **overrides,
) -> MissionState:
    """Build a valid MissionState, cascading tenant_id/mission_id into every
    auto-built nested object so overriding one does not silently desync the
    others. Pass a keyword explicitly (including ``None``, to test rejection
    of a required field) to bypass its auto-built default entirely — the
    sentinel above distinguishes "not provided" from "explicitly None".
    """
    tenant_id = TenantId(uuid4()) if tenant_id is _UNSET else tenant_id
    mission_id = MissionId(uuid4()) if mission_id is _UNSET else mission_id

    if reliability_contract is _UNSET:
        reliability_contract = make_reliability_contract(tenant_id=tenant_id)
    if task_genome is _UNSET:
        task_genome = make_task_genome(contract=reliability_contract, tenant_id=tenant_id)
    if plans is _UNSET:
        plans = (make_plan(tenant_id=tenant_id, mission_id=mission_id),)
    if active_plan_id is _UNSET:
        active_plan_id = plans[0].plan_id if plans else None

    now = utc_now()
    fields = dict(
        tenant_id=tenant_id,
        mission_id=mission_id,
        execution_id=ExecutionId(uuid4()),
        created_at=now,
        updated_at=now,
        state_version=0,
        task_genome=task_genome,
        reliability_contract=reliability_contract,
        status=MissionStatus.CREATED,
        plans=plans,
        active_plan_id=active_plan_id,
        agent_tasks=(),
        retries_used=0,
        replans_used=0,
        agent_calls_used=0,
        tool_calls_used=0,
        execution_time_used_ms=0,
        tokens_used=0,
    )
    fields.update(overrides)
    return MissionState(**fields)
