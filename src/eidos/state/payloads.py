"""Typed event payloads — one class per event type V0.5 and V0.6 Step 4 emit (decisions.md D-153, D-154, D-160, D-166, D-169, D-174).

The V0.1 ``MissionEvent`` is an envelope with no payload field (D-067) and stays one. A payload travels beside it in an
``EventRecord`` (``records.py``) and is chosen by the envelope's ``type``. There are payload classes **only** for the eleven types this
package emits; a type with no class here cannot form an ``EventRecord``, and nothing is invented for it (D-153). ``VERIFICATION_FAILED`` is
deliberately absent: ``NODE_SETTLED`` carries the verdict, so emitting it would record one fact twice (D-160 item 2). No other reserved-but-unbuilt
event type gains a payload here: ``A2A_TASK_STARTED``/``A2A_TASK_COMPLETED`` are the only two of the vocabulary's remote-subsystem types this
package builds (D-090), and D-174 uses exactly those two — no ``A2A_TASK_FAILED`` or the like, and no producer-assigned sequence field on either
(D-172). The tool-call and evidence-search types stay exactly as V0.5 left them: named in the vocabulary, no payload class, because those
subsystems do not exist yet.

What a payload holds is what the reducer and the ``ExecutionRecord`` need and nothing else (D-153): an ``ArtifactRef`` and never artifact
content; what the provider reported and what the recorder observed, and ``None`` where neither exists (D-158) — **no stop reason**, because
``MeasuredFacts`` is not modified (D-151 stays Open); no quality, confidence or score of any kind (D-159).

This module imports the core layers only. The recorded model-call outcome is an enum owned here and mirrored from the agents' failure kinds
by the recording adapter, so that ``eidos.state`` never imports an agent (D-153 item 5). ``AgentTaskStatus`` is imported from
``eidos.contracts`` unchanged (D-166): this module never collapses it, and no A2A-specific name reaches ``eidos.runtime`` — ``AwaitingInfo``
is the one runtime type shared with the A2A vocabulary, and it already carries nothing protocol-specific (D-165 rule 4).
"""

from enum import StrEnum
from types import MappingProxyType
from typing import Literal

from pydantic import Field, model_validator

from eidos.contracts import (
    A2AContextId,
    A2ATaskId,
    AgentId,
    AgentTaskStatus,
    ArtifactRef,
    CapabilityId,
    EidosModel,
    ExecutionId,
    MissionEventType,
    Plan,
    PlanId,
    PlanStepKind,
    ReliabilityContract,
    StepId,
    TaskGenome,
)
from eidos.runtime import AwaitingInfo, HaltInfo, NodeResult, NodeStatus, VerificationVerdict


class PlanRejectionStage(StrEnum):
    """Which gate refused the plan (the single pass stops at the first that does)."""

    VALIDATION = "validation"
    COMPILATION = "compilation"
    BINDING = "binding"


class RejectionReason(EidosModel):
    """One reason a gate refused, as that gate reported it: its own code and its own message."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ModelCallOutcome(StrEnum):
    """What one model call came to. The failure values mirror ``eidos.agents.ModelFailureKind``; a guard test keeps the two in step."""

    RESPONSE = "response"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    MALFORMED_RESPONSE = "malformed_response"
    EMPTY_RESPONSE = "empty_response"


class ModelCallFacts(EidosModel):
    """What was measured about one model call. ``None`` means nobody measured it; it is never a guess.

    A failed call has no provider facts (D-150), so a non-``RESPONSE`` outcome carries none. There is no field for why generation stopped:
    ``MeasuredFacts`` does not carry one and is not modified (D-151, D-158).
    """

    outcome: ModelCallOutcome
    prompt_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    elapsed_seconds: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_a_failed_call_carries_no_provider_facts(self) -> "ModelCallFacts":
        if self.outcome is not ModelCallOutcome.RESPONSE and (
            self.prompt_tokens is not None or self.output_tokens is not None or self.elapsed_seconds is not None
        ):
            raise ValueError(f"a {self.outcome.value} call has no provider facts (D-150)")
        return self


class VerificationFacts(EidosModel):
    """What the ``Verifier`` port returned for a ``VERIFY`` node: a verdict and its reason text, and no typed per-rule outcomes (D-158 item 7)."""

    verdict: VerificationVerdict
    reason: str = Field(min_length=1)


class MissionFailureCause(StrEnum):
    """Why a mission failed, typed so nothing downstream parses a reason (D-059's concern). D-059 itself stays Open: there is no cause for
    "the reliability contract could not be satisfied", and V0.5 makes no claim about contract satisfaction (D-146)."""

    PLAN_REJECTED = "plan_rejected"
    RUN_REJECTED = "run_rejected"
    EXECUTION_FAILED = "execution_failed"
    NO_RESULT = "no_result"
    VERIFICATION_FAILED = "verification_failed"
    VERIFICATION_INCONCLUSIVE = "verification_inconclusive"


class MissionCreatedPayload(EidosModel):
    event_type: Literal[MissionEventType.MISSION_CREATED] = MissionEventType.MISSION_CREATED
    task_genome: TaskGenome
    reliability_contract: ReliabilityContract
    execution_id: ExecutionId


class PlanGeneratedPayload(EidosModel):
    """A plan entered the system. At V0.4 and V0.5 the plan is supplied, not generated (D-131); the type name is the handoff's (§33)."""

    event_type: Literal[MissionEventType.PLAN_GENERATED] = MissionEventType.PLAN_GENERATED
    plan: Plan


class PlanRejectedPayload(EidosModel):
    event_type: Literal[MissionEventType.PLAN_REJECTED] = MissionEventType.PLAN_REJECTED
    plan_id: PlanId
    stage: PlanRejectionStage
    reasons: tuple[RejectionReason, ...] = ()


class PlanCompiledPayload(EidosModel):
    """The plan passed every gate — validated, compiled and bound — and is ready to run."""

    event_type: Literal[MissionEventType.PLAN_COMPILED] = MissionEventType.PLAN_COMPILED
    plan_id: PlanId
    plan_version: int = Field(ge=1)


class NodeStartedPayload(EidosModel):
    """A node was dispatched. ``capability`` and ``agent_id`` say what did the work and are absent for a ``VERIFY`` node."""

    event_type: Literal[MissionEventType.NODE_STARTED] = MissionEventType.NODE_STARTED
    plan_id: PlanId
    step_id: StepId
    kind: PlanStepKind
    capability: CapabilityId | None = None
    agent_id: AgentId | None = None

    @model_validator(mode="after")
    def _check_who_did_the_work_matches_the_kind(self) -> "NodeStartedPayload":
        if self.kind is PlanStepKind.AGENT:
            if self.capability is None or self.agent_id is None:
                raise ValueError("a started work node names its capability and its agent")
        elif self.kind is PlanStepKind.VERIFY:
            if self.capability is not None or self.agent_id is not None:
                raise ValueError("a VERIFY node is not capability-bound and names no agent (D-133)")
        else:
            raise ValueError(f"{self.kind.value!r} is not a kind V0.5 records (only agent and VERIFY execute)")
        return self


class NodeSettledPayload(EidosModel):
    """A node reached a settled state. ``result`` is the runtime's own ``NodeResult``, so the typed status, the artifact reference and the
    reason are exactly what the run reported (D-118) and inherit its validation.

    ``dispatched`` is stated, not inferred: a node carried over from prior outcomes is ``SUCCEEDED`` without having been dispatched in this
    run (D-120), and it must not be counted as an agent call. ``duration_ms`` is an **observed fact** from the recorder's monotonic clock and
    is absent when the node was not dispatched or nobody observed it (D-160 item 6). ``model_calls`` are the calls made while the node ran,
    in call order, and belong to a work node.
    """

    event_type: Literal[MissionEventType.NODE_SETTLED] = MissionEventType.NODE_SETTLED
    plan_id: PlanId
    result: NodeResult
    dispatched: bool
    duration_ms: int | None = Field(default=None, ge=0)
    model_calls: tuple[ModelCallFacts, ...] = ()
    verification: VerificationFacts | None = None

    @model_validator(mode="after")
    def _check_observations_belong_to_a_dispatched_node_of_the_right_kind(self) -> "NodeSettledPayload":
        if not self.dispatched and (self.duration_ms is not None or self.model_calls or self.verification is not None):
            raise ValueError("a node that was not dispatched has no observations")
        if self.result.status in (NodeStatus.SKIPPED, NodeStatus.NOT_REACHED) and self.dispatched:
            raise ValueError(f"a {self.result.status.value} node was not dispatched")
        if self.model_calls and self.result.kind is not PlanStepKind.AGENT:
            raise ValueError("only a work node makes model calls")
        if self.verification is not None and self.result.kind is not PlanStepKind.VERIFY:
            raise ValueError("only a VERIFY node carries a verdict")
        return self


# The AgentTaskStatus values that genuinely conclude a task (D-166): SUBMITTED, WORKING and UNSPECIFIED never do, so they never produce an
# A2A_TASK_COMPLETED event (D-174) — this is the whole set minus those three, not a hand-picked list, so a future AgentTaskStatus addition is
# terminal by default unless it is deliberately excluded here.
_CONCLUDING_AGENT_TASK_STATUSES = frozenset(AgentTaskStatus) - {
    AgentTaskStatus.SUBMITTED, AgentTaskStatus.WORKING, AgentTaskStatus.UNSPECIFIED,
}


class A2ATaskStartedPayload(EidosModel):
    """A remote A2A task was submitted for a work node (D-174). Recorded alongside the existing ``NODE_STARTED`` for the same node — this event
    carries what ``NODE_STARTED`` cannot: the remote task's own identifiers, mirrored verbatim (D-095) and never invented."""

    event_type: Literal[MissionEventType.A2A_TASK_STARTED] = MissionEventType.A2A_TASK_STARTED
    plan_id: PlanId
    step_id: StepId
    agent_id: AgentId
    a2a_task_id: A2ATaskId
    a2a_context_id: A2AContextId | None = None


class A2ATaskCompletedPayload(EidosModel):
    """A remote A2A task reached a terminal outcome (D-166, D-174): the real wire state, or EIDOS-observed ``TIMED_OUT``. Never ``SUBMITTED``,
    ``WORKING`` or ``UNSPECIFIED`` — none of those concludes a task, so none of them may be this event's ``outcome``. ``artifact`` is present
    only when ``outcome`` is ``COMPLETED`` and a usable result came with it, mirroring ``node_status_for``'s own reading
    (``eidos.state.agent_tasks``). ``reason`` is always stated — the remote's own summary or failure explanation — unlike ``NodeResult``'s,
    which a produced work result carries none of.
    """

    event_type: Literal[MissionEventType.A2A_TASK_COMPLETED] = MissionEventType.A2A_TASK_COMPLETED
    plan_id: PlanId
    step_id: StepId
    a2a_task_id: A2ATaskId
    outcome: AgentTaskStatus
    artifact: ArtifactRef | None = Field(default=None, min_length=1)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_the_outcome_and_artifact_are_coherent(self) -> "A2ATaskCompletedPayload":
        if self.outcome not in _CONCLUDING_AGENT_TASK_STATUSES:
            raise ValueError(f"{self.outcome.value} never concludes a task (D-166); it cannot be A2A_TASK_COMPLETED's outcome")
        if self.artifact is not None and self.outcome is not AgentTaskStatus.COMPLETED:
            raise ValueError(f"a {self.outcome.value} outcome carries no artifact")
        return self


class MissionPausedPayload(EidosModel):
    """A mission pauses for exactly one of two reasons (D-169): an admission-guard halt, or an A2A-awaiting pause. ``halt`` and ``awaiting`` are
    never both present and never both absent. An admission-guard pause is terminal, exactly as V0.5 shipped it (D-160 item 9); an A2A-awaiting
    pause is the one exception the reducer accepts a later event for — ``A2A_TASK_COMPLETED`` only (D-176)."""

    event_type: Literal[MissionEventType.MISSION_PAUSED] = MissionEventType.MISSION_PAUSED
    plan_id: PlanId
    halt: HaltInfo | None = None
    awaiting: tuple[AwaitingInfo, ...] = ()

    @model_validator(mode="after")
    def _check_exactly_one_cause(self) -> "MissionPausedPayload":
        if (self.halt is None) == (not self.awaiting):
            raise ValueError("a mission pauses for exactly one reason: halt or awaiting, never both and never neither")
        return self


class MissionCompletedPayload(EidosModel):
    """The run finished. ``verified`` says whether a ``VERIFY`` node succeeded; a finished run without one is completed and unverified
    (D-156, D-160 item 5) — completion is never read as success (invariant 12)."""

    event_type: Literal[MissionEventType.MISSION_COMPLETED] = MissionEventType.MISSION_COMPLETED
    plan_id: PlanId
    verified: bool


class MissionFailedPayload(EidosModel):
    event_type: Literal[MissionEventType.MISSION_FAILED] = MissionEventType.MISSION_FAILED
    plan_id: PlanId | None = None  # absent only if no plan was accepted into the mission
    cause: MissionFailureCause
    reason: str = Field(min_length=1)


EmittedPayload = (
    MissionCreatedPayload
    | PlanGeneratedPayload
    | PlanRejectedPayload
    | PlanCompiledPayload
    | NodeStartedPayload
    | NodeSettledPayload
    | A2ATaskStartedPayload
    | A2ATaskCompletedPayload
    | MissionPausedPayload
    | MissionCompletedPayload
    | MissionFailedPayload
)

# Every event type this package emits, and the class that is its payload. Anything else in ``MissionEventType`` has no payload class here.
PAYLOAD_TYPES = MappingProxyType({
    MissionEventType.MISSION_CREATED: MissionCreatedPayload,
    MissionEventType.PLAN_GENERATED: PlanGeneratedPayload,
    MissionEventType.PLAN_REJECTED: PlanRejectedPayload,
    MissionEventType.PLAN_COMPILED: PlanCompiledPayload,
    MissionEventType.NODE_STARTED: NodeStartedPayload,
    MissionEventType.NODE_SETTLED: NodeSettledPayload,
    MissionEventType.A2A_TASK_STARTED: A2ATaskStartedPayload,
    MissionEventType.A2A_TASK_COMPLETED: A2ATaskCompletedPayload,
    MissionEventType.MISSION_PAUSED: MissionPausedPayload,
    MissionEventType.MISSION_COMPLETED: MissionCompletedPayload,
    MissionEventType.MISSION_FAILED: MissionFailedPayload,
})
