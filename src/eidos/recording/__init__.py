"""eidos.recording — turns a baseline pass into events (decisions.md D-152, D-158, D-160; V0.5 Step 5).

An **adapter** package, not a deterministic one: it takes an injected ``Clock`` and ``IdSource`` and may use the real ones. It wraps the
injection points that already exist — the model port, the work agents and the verifier — and observes the runner through its optional observer.
It holds no ``MissionState`` and cannot write one: it proposes events to the log's intake, and only the reducer behind the intake writes state
(invariants 1 and 2). The runtime, the executors, the compiler, the agents and the verifier are unchanged, and the runtime emits nothing.

The one entry point for a single-attempt pass is ``record_baseline``. V1.1 Step 4 (D-199) additionally exposes
``record_attempt`` (one attempt's own dispatch, recorded live, never the mission's own terminal event) and
``terminal_payload_for`` (the pure classification of what that terminal event would be) — the two lower-level
pieces ``record_baseline`` itself is built from, reused rather than duplicated by within-mission replanning.
"""

from .adapters import ModelCallTracker, RecordingAgent, RecordingModel, RecordingVerifier, facts_of
from .ports import Clock, IdSource, SystemClock, UuidEventIds, UuidPlanIds, UuidStrategyIds
from .recorder import Recorder
from .run import RecordedRun, record_attempt, record_baseline, terminal_payload_for

__all__ = [
    "Clock",
    "IdSource",
    "ModelCallTracker",
    "RecordedRun",
    "Recorder",
    "RecordingAgent",
    "RecordingModel",
    "RecordingVerifier",
    "SystemClock",
    "UuidEventIds",
    "UuidPlanIds",
    "UuidStrategyIds",
    "facts_of",
    "record_attempt",
    "record_baseline",
    "terminal_payload_for",
]
