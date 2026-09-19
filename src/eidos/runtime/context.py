"""ExecutionContext — the frozen, minimal snapshot a run is given.

decisions.md: D-113 (MissionState never enters runtime or backend state; a run
receives a frozen ``ExecutionContext`` containing only the required immutable run
snapshot), D-123 (V0.3 writes nothing to MissionState), D-085 (one execution
identity per mission; a resumed run keeps it), D-088 (a plan is a mission-specific
versioned artifact that self-identifies).

The context carries exactly what execution needs and nothing else:

- ``tenant_id``, ``mission_id`` and ``execution_id`` — who and which execution;
- ``plan_id`` and ``plan_version`` — which plan version this run is *for*;
- ``task_genome`` — what the mission is (its goal and required capabilities), as the
  existing frozen contract rather than a copy of its fields.

It deliberately does **not** carry MissionState, the reliability contract, budget
counters, status, the plan collection, ``active_plan_id`` or ``agent_tasks``: those
are the authoritative state's, and the runtime neither reads them during a run nor
writes them (invariants 1 and 2). ``context_from_state`` is the one place MissionState
is read, once, before a run starts.
"""

from pydantic import Field, model_validator

from eidos.compiler import CompiledPlan
from eidos.contracts import (
    EidosModel,
    ExecutionId,
    MissionId,
    MissionState,
    PlanId,
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

    @model_validator(mode="after")
    def _check_genome_belongs_to_the_tenant(self) -> "ExecutionContext":
        if self.task_genome.tenant_id != self.tenant_id:
            raise ValueError("task_genome.tenant_id must match ExecutionContext.tenant_id")
        return self


def context_from_state(state: MissionState, compiled: CompiledPlan) -> ExecutionContext:
    """Snapshot the narrow fields a run needs from ``state``; ``state`` is only read.

    Identity and genome come from the state. The plan identity comes from the compiled
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
    )
