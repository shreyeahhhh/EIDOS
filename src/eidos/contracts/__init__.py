"""Typed contracts — the shared vocabulary every other EIDOS layer is written against.

Milestone V0.1. All seven contracts are implemented: TaskGenome,
ReliabilityContract, MissionState, MissionEvent, Plan, PlanStep, AgentTask.
See docs/03_architecture.md, docs/04-docs/07 and docs/10, and decisions.md
for the full record of what each field is and why.

Constraints these models satisfy (CLAUDE.md §8):

- Pydantic v2. Typed and validated; no untyped dict crosses this boundary.
- This package depends on nothing else inside ``eidos``.
- No model, vendor or SDK reference (invariant 9).
- No I/O, no network, no LLM calls. V0.1 is in-memory only (decision D-005).
- Every model is frozen (immutable) and rejects unknown fields.

Not in this package: the plan validator, the compiler, the runtime, the
state reducer, A2A, MCP, RAG, persistence, or any executable behaviour.
Those arrive at their own milestones — see progress.md.
"""

from ._base import EidosModel
from .agent_task import AgentTask, AgentTaskStatus
from .enums import (
    AutonomyLevel,
    MissionEventType,
    MissionStatus,
    PlanStepKind,
    RiskLevel,
)
from .identifiers import (
    A2AContextId,
    A2ATaskId,
    ActionId,
    AgentId,
    ArtifactRef,
    CapabilityId,
    DEFAULT_TENANT_ID,
    EventId,
    ExecutionId,
    MissionId,
    PlanId,
    ReliabilityContractId,
    StepId,
    TenantId,
)
from .mission_event import MissionEvent
from .mission_state import MissionState
from .plan import (
    AgentStep,
    ControlStep,
    DuplicateStepIdError,
    Plan,
    PlanStep,
    UnknownDependencyError,
)
from .reliability_contract import ReliabilityContract
from .task_genome import TaskGenome

__all__ = [
    "EidosModel",
    "AgentTask",
    "AgentTaskStatus",
    "AutonomyLevel",
    "MissionEventType",
    "MissionStatus",
    "PlanStepKind",
    "RiskLevel",
    "A2AContextId",
    "A2ATaskId",
    "ActionId",
    "AgentId",
    "ArtifactRef",
    "CapabilityId",
    "DEFAULT_TENANT_ID",
    "EventId",
    "ExecutionId",
    "MissionId",
    "PlanId",
    "ReliabilityContractId",
    "StepId",
    "TenantId",
    "MissionEvent",
    "MissionState",
    "AgentStep",
    "ControlStep",
    "DuplicateStepIdError",
    "Plan",
    "PlanStep",
    "UnknownDependencyError",
    "ReliabilityContract",
    "TaskGenome",
]
