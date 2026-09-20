"""ExecutionContext — the frozen, minimal snapshot a run is given.

decisions.md: D-113 (MissionState never enters runtime or backend state; a run
receives a frozen ``ExecutionContext`` containing only the required immutable run
snapshot), D-123 (V0.3 writes nothing to MissionState), D-085 (one execution
identity per mission; a resumed run keeps it), D-088 (a plan is a mission-specific
versioned artifact that self-identifies), D-139 (from V0.4 the frozen
``ReliabilityContract`` is part of the snapshot).

The context carries exactly what execution needs and nothing else:

- ``tenant_id``, ``mission_id`` and ``execution_id`` — who and which execution;
- ``plan_id`` and ``plan_version`` — which plan version this run is *for*;
- ``task_genome`` — what the mission is (its goal and required capabilities), as the
  existing frozen contract rather than a copy of its fields;
- ``reliability_contract`` — the mission's frozen contract, so a verifier can read the
  thresholds it is judged against (D-139). The genome's reference to it must agree.

It deliberately does **not** carry MissionState, budget counters, status, the plan
collection, ``active_plan_id`` or ``agent_tasks``: those are the authoritative state's,
and the runtime neither reads them during a run nor writes them (invariants 1 and 2).
There is no output or answer field (D-041 stays Open). ``context_from_state`` is the one
place MissionState is read, once, before a run starts.
"""

from pydantic import Field, model_validator

from eidos.compiler import CompiledPlan
from eidos.contracts import (
    EidosModel,
    ExecutionId,
    MissionId,
    MissionState,
    PlanId,
    ReliabilityContract,
    TaskGenome,
    TenantId,
)


class ExecutionContext(EidosModel):
    tenant_id: TenantId
    mission_id: MissionId
    execution_id: ExecutionId
    plan_id: PlanId
    plan_version: int = Field(ge=1)
    task_genome: TaskGenome
    reliability_contract: ReliabilityContract

    @model_validator(mode="after")
    def _check_genome_belongs_to_the_tenant(self) -> "ExecutionContext":
        if self.task_genome.tenant_id != self.tenant_id:
            raise ValueError("task_genome.tenant_id must match ExecutionContext.tenant_id")
        return self

    @model_validator(mode="after")
    def _check_contract_belongs_to_the_tenant_and_the_genome(self) -> "ExecutionContext":
        if self.reliability_contract.tenant_id != self.tenant_id:
            raise ValueError("reliability_contract.tenant_id must match ExecutionContext.tenant_id")
        if self.task_genome.reliability_contract_id != self.reliability_contract.contract_id:
            raise ValueError(
                "task_genome.reliability_contract_id must equal reliability_contract.contract_id (D-100, D-139)"
            )
        return self


def context_from_state(state: MissionState, compiled: CompiledPlan) -> ExecutionContext:
    """Snapshot the narrow fields a run needs from ``state``; ``state`` is only read.

    Identity, genome and reliability contract come from the state. The plan identity comes from the compiled
    plan the run is for. Nothing is validated against the state's ``plans`` here — the
    executor's preconditions decide whether the context and the compiled plan agree.
    """
    return ExecutionContext(
        tenant_id=state.tenant_id,
        mission_id=state.mission_id,
        execution_id=state.execution_id,
        plan_id=compiled.plan_id,
        plan_version=compiled.plan_version,
        task_genome=state.task_genome,
        reliability_contract=state.reliability_contract,
    )
