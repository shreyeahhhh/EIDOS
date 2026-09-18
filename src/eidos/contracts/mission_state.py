"""MissionState — handoff §9, §10.

MissionState is the only authoritative global state (invariant 1). Only the
state reducer mutates it (invariant 2) — V0.1 has no reducer (that is
V0.5), so this model is constructed directly and never mutated in place
(it is frozen, per _base.py).

decisions.md: D-010a (a materialized view over the event log, holding only
what the runtime must answer synchronously — task_genome, status, plan
lineage, remote AgentTask records, budget counters, and the acceptance
contract per D-100; detailed per-node runtime execution state does not
enter this model), D-042/D-091 (plans, agent_tasks and the six budget
counters are required, immutable, may be empty; counters are non-negative
integers), D-077 (required/optional split for this model's own fields),
D-078 (the execution-time counter is in milliseconds, matching
ReliabilityContract.max_execution_time's unit), D-079 (tenant_id default),
D-082 (plans is an ordered collection; agent_tasks is unkeyed), D-083
(timezone-aware UTC; naive rejected), D-084 (task_genome is required — a
mission is created with its genome; no §33 event type introduces one, so
under D-010a's fold it must exist from MISSION_CREATED), D-085
(execution_id is required and immutable; V0.1 has exactly one execution
identity per mission — replans create plan versions, not new executions,
and pause/resume keeps the same execution_id), D-088 (a contained Plan's
mission_id must match this MissionState's mission_id), D-097 (state_version
is a non-negative integer; sequencing semantics belong to the V0.5
reducer), D-100 (this model holds the authoritative ReliabilityContract;
TaskGenome holds only a reference to it, so the two must agree).

The six model_validators below are exactly the MissionState-level
consistency checks approved as A7 (2026-09-18): contract-reference
consistency, plan/mission_id consistency, plan_id uniqueness, plan-lineage
referential integrity, active_plan_id referential integrity, and tenant
consistency across every contained root object. No further lifecycle rule
is added (A7: "Do not invent additional lifecycle rules") — in particular,
Plan.version ordering across `plans` is not checked here.
"""

from pydantic import Field, model_validator

from ._base import EidosModel
from ._validators import UtcDateTime
from .agent_task import AgentTask
from .enums import MissionStatus
from .identifiers import (
    DEFAULT_TENANT_ID,
    ExecutionId,
    MissionId,
    PlanId,
    TenantId,
)
from .plan import Plan
from .reliability_contract import ReliabilityContract
from .task_genome import TaskGenome


class MissionState(EidosModel):
    tenant_id: TenantId = Field(default=DEFAULT_TENANT_ID)
    mission_id: MissionId
    execution_id: ExecutionId

    created_at: UtcDateTime
    updated_at: UtcDateTime
    state_version: int = Field(ge=0)

    task_genome: TaskGenome
    reliability_contract: ReliabilityContract

    status: MissionStatus
    status_reason: str | None = None

    plans: tuple[Plan, ...]
    active_plan_id: PlanId | None = None

    agent_tasks: tuple[AgentTask, ...]

    retries_used: int = Field(ge=0)
    replans_used: int = Field(ge=0)
    agent_calls_used: int = Field(ge=0)
    tool_calls_used: int = Field(ge=0)
    execution_time_used_ms: int = Field(ge=0)
    tokens_used: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_contract_reference_consistency(self) -> "MissionState":
        if self.task_genome.reliability_contract_id != self.reliability_contract.contract_id:
            raise ValueError(
                "task_genome.reliability_contract_id must equal "
                "reliability_contract.contract_id (decisions.md D-100)"
            )
        return self

    @model_validator(mode="after")
    def _check_plan_mission_id_consistency(self) -> "MissionState":
        for plan in self.plans:
            if plan.mission_id != self.mission_id:
                raise ValueError(
                    f"plan {plan.plan_id!r} has mission_id {plan.mission_id!r}, "
                    f"expected {self.mission_id!r} (decisions.md D-088)"
                )
        return self

    @model_validator(mode="after")
    def _check_plan_id_uniqueness(self) -> "MissionState":
        seen: set[PlanId] = set()
        for plan in self.plans:
            if plan.plan_id in seen:
                raise ValueError(
                    f"duplicate plan_id {plan.plan_id!r} within MissionState.plans"
                )
            seen.add(plan.plan_id)
        return self

    @model_validator(mode="after")
    def _check_plan_lineage_resolves(self) -> "MissionState":
        plan_ids = {plan.plan_id for plan in self.plans}
        for plan in self.plans:
            if plan.parent_plan_id is not None and plan.parent_plan_id not in plan_ids:
                raise ValueError(
                    f"plan {plan.plan_id!r} has parent_plan_id "
                    f"{plan.parent_plan_id!r} which does not resolve to any "
                    "plan in MissionState.plans"
                )
        return self

    @model_validator(mode="after")
    def _check_active_plan_id_resolves(self) -> "MissionState":
        if self.active_plan_id is not None:
            plan_ids = {plan.plan_id for plan in self.plans}
            if self.active_plan_id not in plan_ids:
                raise ValueError(
                    f"active_plan_id {self.active_plan_id!r} does not resolve "
                    "to any plan in MissionState.plans"
                )
        return self

    @model_validator(mode="after")
    def _check_tenant_consistency(self) -> "MissionState":
        if self.task_genome.tenant_id != self.tenant_id:
            raise ValueError("task_genome.tenant_id must match MissionState.tenant_id")
        if self.reliability_contract.tenant_id != self.tenant_id:
            raise ValueError(
                "reliability_contract.tenant_id must match MissionState.tenant_id"
            )
        for plan in self.plans:
            if plan.tenant_id != self.tenant_id:
                raise ValueError(
                    f"plan {plan.plan_id!r}.tenant_id must match MissionState.tenant_id"
                )
        return self
