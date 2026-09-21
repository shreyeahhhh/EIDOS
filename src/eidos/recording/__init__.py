"""eidos.recording — turns a baseline pass into events (decisions.md D-152, D-158, D-160; V0.5 Step 5).

An **adapter** package, not a deterministic one: it takes an injected ``Clock`` and ``IdSource`` and may use the real ones. It wraps the
injection points that already exist — the model port, the work agents and the verifier — and observes the runner through its optional observer.
It holds no ``MissionState`` and cannot write one: it proposes events to the log's intake, and only the reducer behind the intake writes state
(invariants 1 and 2). The runtime, the executors, the compiler, the agents and the verifier are unchanged, and the runtime emits nothing.

The one entry point is ``record_baseline``.
"""

from .adapters import ModelCallTracker, RecordingAgent, RecordingModel, RecordingVerifier, facts_of
from .ports import Clock, IdSource, SystemClock, UuidEventIds
from .recorder import Recorder
from .run import RecordedRun, record_baseline

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
    "facts_of",
    "record_baseline",
]
