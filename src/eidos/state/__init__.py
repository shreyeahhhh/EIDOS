"""eidos.state — the event records, and (in later V0.5 steps) the reducer, the log, checkpoint, replay and ``ExecutionRecord``
(decisions.md D-152 to D-161).

This is a core layer: it imports the contract and runtime layers and never an agent, provider, capability or baseline module. It does no
I/O, reads no clock and holds no hidden state. The event log is authoritative and ``MissionState`` is only its view (D-157); only the reducer
writes ``MissionState`` (invariants 1 and 2).

Step 2 — the typed payloads and ``EventRecord`` (D-153, D-154, D-160).
Step 3 — the pure reducer (D-155, D-156, D-160).
Step 4 — the event log and intake, checkpoint, replay and the strict JSONL form (D-157).
Step 6 — ``ExecutionRecord``, the derived read-only projection of a log (D-159).
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
from .execution_record import ExecutionRecord, StepRecord, execution_record
from .log import EventLog, EventProposal, IntakeResult
from .records import EventRecord, Payload
from .reducer import ReduceOutcome, ReduceResult, reduce
from .replay import (
    Checkpoint,
    LoadResult,
    ReplayRejection,
    ReplayRejectionCode,
    ReplayResult,
    checkpoint_at,
    dump_jsonl,
    load_jsonl,
    records_after,
    replay,
    replay_jsonl,
    resume,
)

__all__ = [
    "PAYLOAD_TYPES",
    "Checkpoint",
    "EmittedPayload",
    "EventLog",
    "EventProposal",
    "EventRecord",
    "ExecutionRecord",
    "IntakeResult",
    "LoadResult",
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
    "ReplayRejection",
    "ReplayRejectionCode",
    "ReplayResult",
    "StepRecord",
    "VerificationFacts",
    "checkpoint_at",
    "dump_jsonl",
    "execution_record",
    "load_jsonl",
    "records_after",
    "reduce",
    "replay",
    "replay_jsonl",
    "resume",
]
