"""Deterministic fixtures for the V0.5 state tests: fixed identifiers, fixed times, and a builder for a realistic recorded baseline.

Nothing here reads the wall clock or draws a random identifier, so a test built on it is repeatable across interpreters. It imports the
mission and plan helpers that are themselves pure (``eidos_mission_factories``), and no backend, agent or provider.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from eidos.contracts import (
    A2AContextId,
    A2ATaskId,
    AgentId,
    AgentTaskStatus,
    ArtifactRef,
    CapabilityId,
    EventId,
    MissionEvent,
    MissionEventType,
    MissionState,
    Plan,
    PlanStepKind,
    StepId,
)
from eidos.runtime import AwaitingInfo, HaltInfo, NodeResult, NodeStatus, VerificationVerdict
from eidos.state import (
    A2ATaskCompletedPayload,
    A2ATaskStartedPayload,
    EventRecord,
    MissionCompletedPayload,
    MissionCreatedPayload,
    MissionFailedPayload,
    MissionFailureCause,
    MissionPausedPayload,
    ModelCallFacts,
    ModelCallOutcome,
    NodeSettledPayload,
    NodeStartedPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    PlanRejectedPayload,
    PlanRejectionStage,
    RejectionReason,
    VerificationFacts,
)

from eidos_mission_factories import make_mission, make_mission_plan

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
RESEARCH_AGENT = AgentId(UUID(int=501))
ANALYSIS_AGENT = AgentId(UUID(int=502))


def at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


def event_id(number: int) -> EventId:
    return EventId(UUID(int=900_000 + number))


def a2a_task_id(number: int) -> A2ATaskId:
    return A2ATaskId(f"remote-task-{number}")


def a2a_context_id(number: int) -> A2AContextId:
    return A2AContextId(f"remote-context-{number}")


def make_record(payload, *, state: MissionState, sequence: int, number: int | None = None, seconds: int | None = None) -> EventRecord:
    """A record for ``state``'s mission. ``number`` picks the event id (default: the sequence) and ``seconds`` the time (default: the sequence)."""
    moment = at(sequence if seconds is None else seconds)
    return EventRecord(
        event=MissionEvent(
            event_id=event_id(sequence if number is None else number),
            tenant_id=state.tenant_id,
            mission_id=state.mission_id,
            sequence=sequence,
            occurred_at=moment,
            recorded_at=moment,
            type=payload.event_type,
        ),
        payload=payload,
    )


def created(state: MissionState) -> MissionCreatedPayload:
    return MissionCreatedPayload(task_genome=state.task_genome, reliability_contract=state.reliability_contract, execution_id=state.execution_id)


def work_result(step: str, *, status: NodeStatus = NodeStatus.SUCCEEDED, reason: str | None = None) -> NodeResult:
    if status is NodeStatus.SUCCEEDED:
        return NodeResult(step_id=StepId(step), kind=PlanStepKind.AGENT, status=status, artifact=ArtifactRef(f"artifact:{step}"))
    return NodeResult(step_id=StepId(step), kind=PlanStepKind.AGENT, status=status, reason=reason or f"{status.value} for {step}")


def verify_result(step: str, *, status: NodeStatus = NodeStatus.SUCCEEDED, reason: str = "the supported rules were satisfied") -> NodeResult:
    return NodeResult(step_id=StepId(step), kind=PlanStepKind.VERIFY, status=status, reason=reason)


def response_call(prompt: int = 100, output: int = 200, seconds: float = 1.5) -> ModelCallFacts:
    return ModelCallFacts(outcome=ModelCallOutcome.RESPONSE, prompt_tokens=prompt, output_tokens=output, elapsed_seconds=seconds)


CAPABILITY_OF = {"gather": "research", "analyse": "analysis"}
AGENT_OF = {"gather": RESEARCH_AGENT, "analyse": ANALYSIS_AGENT}
SPEC = {"gather": "", "analyse": "gather", "check": "analyse"}


def baseline_state_and_plan(seed: int = 1) -> tuple[MissionState, Plan]:
    state = make_mission(seed=seed)
    return state, make_mission_plan(state, SPEC, verify=("check",), capability_of=CAPABILITY_OF)


class LogBuilder:
    """Builds the records of one mission in order, numbering sequences and times as it goes, so a test states only what is interesting."""

    def __init__(self, state: MissionState, plan: Plan):
        self.state, self.plan, self.records = state, plan, []

    def add(self, payload, **kwargs) -> EventRecord:
        record = make_record(payload, state=self.state, sequence=len(self.records) + 1, **kwargs)
        self.records.append(record)
        return record

    def created(self):
        return self.add(created(self.state))

    def generated(self):
        return self.add(PlanGeneratedPayload(plan=self.plan))

    def compiled(self):
        return self.add(PlanCompiledPayload(plan_id=self.plan.plan_id, plan_version=self.plan.version))

    def rejected(self, stage=PlanRejectionStage.VALIDATION, *reasons):
        return self.add(PlanRejectedPayload(plan_id=self.plan.plan_id, stage=stage, reasons=tuple(RejectionReason(code=c, message=m) for c, m in reasons)))

    def started(self, step: str):
        agent = AGENT_OF.get(step)
        kind = PlanStepKind.AGENT if agent else PlanStepKind.VERIFY
        return self.add(NodeStartedPayload(
            plan_id=self.plan.plan_id, step_id=StepId(step), kind=kind,
            capability=CapabilityId(CAPABILITY_OF[step]) if agent else None, agent_id=agent,
        ))

    def settled(self, result: NodeResult, *, dispatched: bool = True, duration_ms: int | None = 1000, model_calls=(), verification=None):
        if not dispatched:
            duration_ms, model_calls, verification = None, (), None
        return self.add(NodeSettledPayload(
            plan_id=self.plan.plan_id, result=result, dispatched=dispatched, duration_ms=duration_ms,
            model_calls=tuple(model_calls), verification=verification,
        ))

    def paused(self, step: str = "analyse", level: int = 2, reason: str = "held for review"):
        return self.add(MissionPausedPayload(plan_id=self.plan.plan_id, halt=HaltInfo(step_id=StepId(step), level=level, reason=reason)))

    def paused_awaiting(self, *steps: str, level: int = 2, reason: str = "awaiting a remote A2A task"):
        infos = tuple(AwaitingInfo(step_id=StepId(step), level=level, reason=reason) for step in steps)
        return self.add(MissionPausedPayload(plan_id=self.plan.plan_id, awaiting=infos))

    def a2a_started(self, step: str, *, task: int = 1, context: int | None = None):
        agent = AGENT_OF[step]
        return self.add(A2ATaskStartedPayload(
            plan_id=self.plan.plan_id, step_id=StepId(step), agent_id=agent,
            a2a_task_id=a2a_task_id(task), a2a_context_id=a2a_context_id(context) if context is not None else None,
        ))

    def a2a_completed(self, step: str, *, task: int = 1, outcome: AgentTaskStatus = AgentTaskStatus.COMPLETED,
                       artifact: ArtifactRef | None = None, reason: str = "the remote task concluded"):
        if outcome is AgentTaskStatus.COMPLETED and artifact is None:
            artifact = ArtifactRef(f"artifact:{step}")
        return self.add(A2ATaskCompletedPayload(
            plan_id=self.plan.plan_id, step_id=StepId(step), a2a_task_id=a2a_task_id(task),
            outcome=outcome, artifact=artifact, reason=reason,
        ))

    def completed(self, verified: bool = True):
        return self.add(MissionCompletedPayload(plan_id=self.plan.plan_id, verified=verified))

    def failed(self, cause=MissionFailureCause.VERIFICATION_FAILED, reason: str = "a rule was violated"):
        return self.add(MissionFailedPayload(plan_id=self.plan.plan_id, cause=cause, reason=reason))


def verified_baseline(seed: int = 1) -> LogBuilder:
    """The recorded shape of a finished, verified baseline: each node is started and then settled in turn; the work nodes each make one model
    call; the VERIFY passes."""
    state, plan = baseline_state_and_plan(seed)
    log = LogBuilder(state, plan)
    log.created()
    log.generated()
    log.compiled()
    log.started("gather")
    log.settled(work_result("gather"), duration_ms=1200, model_calls=(response_call(160, 977, 53.0),))
    log.started("analyse")
    log.settled(work_result("analyse"), duration_ms=3400, model_calls=(response_call(322, 2582, 154.2),))
    log.started("check")
    log.settled(verify_result("check"), duration_ms=5, verification=VerificationFacts(verdict=VerificationVerdict.PASS, reason="the supported rules were satisfied"))
    log.completed(verified=True)
    return log
