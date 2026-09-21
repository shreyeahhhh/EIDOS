"""eidos.state — the event records, and (in later V0.5 steps) the reducer, the log, checkpoint, replay and ``ExecutionRecord``
(decisions.md D-152 to D-161).

This is a core layer: it imports the contract and runtime layers and never an agent, provider, capability or baseline module. It does no
I/O, reads no clock and holds no hidden state. The event log is authoritative and ``MissionState`` is only its view (D-157); only the reducer
writes ``MissionState`` (invariants 1 and 2).

Step 2 — the typed payloads and ``EventRecord`` (D-153, D-154, D-160).
Step 3 — the pure reducer (D-155, D-156, D-160).
"""

from .payloads import (
    PAYLOAD_TYPES,
    EmittedPayload,
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
from .records import EventRecord, Payload
from .reducer import ReduceOutcome, ReduceResult, reduce

__all__ = [
    "PAYLOAD_TYPES",
    "EmittedPayload",
    "EventRecord",
    "MissionCompletedPayload",
    "MissionCreatedPayload",
    "MissionFailedPayload",
    "MissionFailureCause",
    "MissionPausedPayload",
    "ModelCallFacts",
    "ModelCallOutcome",
    "NodeSettledPayload",
    "NodeStartedPayload",
    "Payload",
    "PlanCompiledPayload",
    "PlanGeneratedPayload",
    "PlanRejectedPayload",
    "PlanRejectionStage",
    "ReduceOutcome",
    "ReduceResult",
    "RejectionReason",
    "VerificationFacts",
    "reduce",
]
