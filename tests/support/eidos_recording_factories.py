"""Fixtures for the V0.5 recording tests: a fixed clock, sequential ids, and a pure rig of the V0.4 agents over a scripted model.

Nothing here reaches a real model, the wall clock or a random source, and nothing here imports a backend, so the unit tests built on it run with
LangGraph blocked. A number produced by these fixtures is a fixed test value, never a measurement.
"""

import threading
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from eidos.agents import (
    AnalysisAgent,
    InMemoryArtifactStore,
    MeasuredFacts,
    ModelResponse,
    ResearchAgent,
    VerificationAgent,
)
from eidos.baseline import BaselineReport, run_baseline
from eidos.contracts import EventId, MissionState, Plan
from eidos.recording import ModelCallTracker, RecordedRun, RecordingModel, record_baseline
from eidos.runtime import SequentialExecutor
from eidos.validation import SystemLimits

from eidos_agents_factories import ScriptedModel, doc, make_settings
from eidos_mission_factories import make_mission, make_mission_plan
from eidos_runtime_factories import admit_all
from eidos_state_factories import T0
from eidos_v04_registry import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID, make_registry
from eidos_validation_factories import make_system_limits


class FixedClock:
    """Each ``now()`` is one second later than the last, and each ``monotonic_ns()`` reading is a fixed step after the last."""

    def __init__(self, *, step_seconds: int = 1, monotonic_step_ms: int = 1000):
        self._lock = threading.Lock()
        self._now = self._mono = 0
        self.step_seconds, self.monotonic_step_ms = step_seconds, monotonic_step_ms

    def now(self):
        with self._lock:
            self._now += 1
            return T0 + timedelta(seconds=self.step_seconds * self._now)

    def monotonic_ns(self) -> int:
        with self._lock:
            self._mono += 1
            return self._mono * self.monotonic_step_ms * 1_000_000

    @property
    def readings(self) -> tuple[int, int]:
        return self._now, self._mono


class SequentialIds:
    def __init__(self, start: int = 0):
        self._lock = threading.Lock()
        self._n = start

    def next_event_id(self) -> EventId:
        with self._lock:
            self._n += 1
            return EventId(UUID(int=7_000_000 + self._n))


def respond_with_facts(
    research="Findings [[doc:1]] [[doc:2]] [[doc:3]].", analysis="Analysis [[artifact:gather]] [[doc:1]].", prompt=100, output=200, seconds=0.5
):
    """A scripted model that answers a research prompt and an analysis prompt with fixed texts and fixed provider-style facts."""

    def respond(request):
        text = research if "Documents:" in request.prompt else analysis
        if not isinstance(text, str):
            return text  # a ModelFailure, or anything else the scenario wants the agents to face
        return ModelResponse(text=text, measured=MeasuredFacts(prompt_tokens=prompt, output_tokens=output, elapsed_seconds=seconds))

    return respond


def three_docs():
    return tuple(doc(f"doc:{n}", f"Source document {n}.") for n in (1, 2, 3))


@dataclass
class Rig:
    store: InMemoryArtifactStore
    scripted: ScriptedModel
    tracker: ModelCallTracker
    agents: dict
    verifier: VerificationAgent


def new_rig(state: MissionState, respond=None, docs=None) -> Rig:
    store = InMemoryArtifactStore()
    for document in three_docs() if docs is None else docs:
        store.put_supplied(state.execution_id, document)
    scripted = ScriptedModel(respond or respond_with_facts())
    tracker = ModelCallTracker()
    model = RecordingModel(scripted, tracker)
    settings = make_settings()
    agents = {
        RESEARCH_AGENT_ID: ResearchAgent(model=model, settings=settings, store=store),
        ANALYSIS_AGENT_ID: AnalysisAgent(model=model, settings=settings, store=store),
    }
    return Rig(store=store, scripted=scripted, tracker=tracker, agents=agents, verifier=VerificationAgent(store=store))


def baseline_mission() -> tuple[MissionState, Plan]:
    state = make_mission(capabilities=("research", "cost"))
    plan = make_mission_plan(state, {"gather": "", "analyse": "gather", "check": "analyse"}, verify=("check",),
                             capability_of={"gather": "research", "analyse": "cost"})
    return state, plan


def record(state, plan, rig=None, *, respond=None, guard=None, prior=None, registry=None, clock=None, ids=None, log=None,
           executor=SequentialExecutor, limits: SystemLimits | None = None, tracker=None) -> tuple[RecordedRun, Rig]:
    rig = rig or new_rig(state, respond)
    run = record_baseline(
        state=state, plan=plan, limits=limits or make_system_limits(), registry=registry or make_registry(),
        agents=rig.agents, verifier=rig.verifier, admission_guard=guard or admit_all(), executor_factory=executor,
        clock=clock or FixedClock(), ids=ids or SequentialIds(), prior=prior, log=log, tracker=tracker or rig.tracker,
    )
    return run, rig


def unrecorded(state, plan, rig=None, *, respond=None, guard=None, prior=None, registry=None, executor=SequentialExecutor) -> BaselineReport:
    """The same pass with nothing recording it, over a fresh rig — what the recorded report must equal."""
    rig = rig or new_rig(state, respond)
    return run_baseline(
        state=state, plan=plan, limits=make_system_limits(), registry=registry or make_registry(), agents=rig.agents,
        verifier=rig.verifier, admission_guard=guard or admit_all(), executor_factory=executor, prior=prior,
    )
