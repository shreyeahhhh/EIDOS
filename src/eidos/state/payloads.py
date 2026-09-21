"""Typed event payloads — one class per event type V0.5 emits (decisions.md D-153, D-154, D-160).

The V0.1 ``MissionEvent`` is an envelope with no payload field (D-067) and stays one. A payload travels beside it in an
``EventRecord`` (``records.py``) and is chosen by the envelope's ``type``. There are payload classes **only** for the nine types V0.5
emits; a type with no class here cannot form an ``EventRecord``, and nothing is invented for it (D-153). ``VERIFICATION_FAILED`` is
deliberately absent: ``NODE_SETTLED`` carries the verdict, so emitting it would record one fact twice (D-160 item 2).

What a payload holds is what the reducer and the ``ExecutionRecord`` need and nothing else (D-153): an ``ArtifactRef`` and never artifact
content; what the provider reported and what the recorder observed, and ``None`` where neither exists (D-158) — **no stop reason**, because
``MeasuredFacts`` is not modified (D-151 stays Open); no quality, confidence or score of any kind (D-159).

This module imports the core layers only. The recorded model-call outcome is an enum owned here and mirrored from the agents' failure kinds
by the recording adapter, so that ``eidos.state`` never imports an agent (D-153 item 5).
"""

from enum import StrEnum
from types import MappingProxyType
from typing import Literal

from pydantic import Field, model_validator

from eidos.contracts import (
    AgentId,
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
from eidos.runtime import HaltInfo, NodeResult, NodeStatus, VerificationVerdict


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


class MissionPausedPayload(EidosModel):
    """A run halted at an admission guard, so the mission is ``paused``. ``paused`` is terminal in V0.5: resume is deferred (D-160 item 9)."""

    event_type: Literal[MissionEventType.MISSION_PAUSED] = MissionEventType.MISSION_PAUSED
    plan_id: PlanId
    halt: HaltInfo


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
    | MissionPausedPayload
    | MissionCompletedPayload
    | MissionFailedPayload
)

# Every event type V0.5 emits, and the class that is its payload. Anything else in ``MissionEventType`` has no payload class in V0.5.
PAYLOAD_TYPES = MappingProxyType({
    MissionEventType.MISSION_CREATED: MissionCreatedPayload,
    MissionEventType.PLAN_GENERATED: PlanGeneratedPayload,
    MissionEventType.PLAN_REJECTED: PlanRejectedPayload,
    MissionEventType.PLAN_COMPILED: PlanCompiledPayload,
    MissionEventType.NODE_STARTED: NodeStartedPayload,
    MissionEventType.NODE_SETTLED: NodeSettledPayload,
    MissionEventType.MISSION_PAUSED: MissionPausedPayload,
    MissionEventType.MISSION_COMPLETED: MissionCompletedPayload,
    MissionEventType.MISSION_FAILED: MissionFailedPayload,
})
