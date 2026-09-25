"""The tool path across a within-mission replan (decisions.md D-199, D-203, D-204, D-205; V1.2 Step 4).

Real ``run_with_replanning``, real candidate generation and selection, real agents, real gate and store; the tool provider is scripted. Each plan attempt has
its own tool-call budget, scoped by ``(execution_id, plan_id)``, and a duplicate is recognised across the attempts of the execution.

What this deliberately does not assert: tool-call *facts* through this path. ``run_with_replanning`` does not propagate a caller's tracker to the recorder it
builds per attempt, so neither model-call facts nor tool-call facts are captured through it (D-204, Open and deferred and not touched by V1.2); the
recorded-facts scenarios run through ``record_baseline``, where a tracker is accepted.
"""

import tempfile
from pathlib import Path

import pytest

from eidos.agents import AnalysisAgent, InMemoryArtifactStore, ResearchAgent, ToolFailure, ToolFailureKind, ToolGate, VerificationAgent
from eidos.contracts import MissionStatus
from eidos.memory import JsonlExperienceStore
from eidos.planning import DeterministicSelector, RuleBasedCandidateGenerator
from eidos.recording import UuidEventIds, UuidPlanIds, UuidStrategyIds
from eidos.replanning import ReplanRun, run_with_replanning
from eidos.runtime import SequentialExecutor

from eidos_agents_factories import ScriptedModel, make_settings
from eidos_mcp_fixture import make_mcp_port
from eidos_planning_factories import GENEROUS_LIMITS
from eidos_recording_factories import FixedClock
from eidos_replanning_factories import ScriptedCalls, always_fails
from eidos_runtime_factories import admit_all
from eidos_search_fixture import TOOL_ID, CountingPort, ScriptedToolPort, cite_every_document, make_tool_mission, search_registry
from eidos_v04_registry import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID, make_registry


def replanned(state, port, registry=None):
    store = InMemoryArtifactStore()
    gate = ToolGate(registry=registry or search_registry(), port=port, store=store)
    model = ScriptedModel(cite_every_document)
    agents = {
        RESEARCH_AGENT_ID: ResearchAgent(model=model, settings=make_settings(), store=store, tools=gate, search_tool_id=TOOL_ID),
        ANALYSIS_AGENT_ID: AnalysisAgent(model=model, settings=make_settings(), store=store),
    }
    with tempfile.TemporaryDirectory() as directory:
        outcome = run_with_replanning(
            state=state, limits=GENEROUS_LIMITS, registry=make_registry(), agents=agents, verifier=VerificationAgent(store=store),
            admission_guard_factory=admit_all, executor_factory=SequentialExecutor, clock=FixedClock(), ids=UuidEventIds(),
            strategy_ids=UuidStrategyIds(), plan_ids=UuidPlanIds(), candidate_generator=RuleBasedCandidateGenerator(), max_candidates=3,
            selector=DeterministicSelector(), store=JsonlExperienceStore.open(Path(directory) / "experience.jsonl"),
        )
    assert isinstance(outcome, ReplanRun), outcome
    return outcome, gate, store


class FirstCallFails:
    """A provider whose first call times out and whose later calls answer from the fixture: enough to make attempt one fail and attempt two succeed."""

    def __init__(self):
        self.real, self.seen = ScriptedToolPort(), 0
        self.port = ScriptedToolPort(self)

    def __call__(self, request):
        self.seen += 1
        return ToolFailure(kind=ToolFailureKind.TIMEOUT, message="the first call is slow") if self.seen == 1 else self.real.call(request)


@pytest.fixture(params=["scripted", "mcp"])
def first_call_times_out(request, tmp_path):
    """``(port, registry)`` for a provider whose first call runs past a short allowlist timeout and whose later calls answer: the scripted kind is told to, the
    real kind is a real server process that sleeps on its first call only (a marker file remembers)."""
    registry = search_registry(timeout_seconds=0.5)
    if request.param == "scripted":
        yield CountingPort(FirstCallFails().port), registry
        return
    port = CountingPort(make_mcp_port(fault="slow_once", argument=str(tmp_path / "marker"), registry=registry))
    yield port, registry
    port.close()


def test_a_replanned_attempt_receives_its_own_tool_budget_and_the_mission_then_completes_verified(first_call_times_out):
    port, registry = first_call_times_out
    state = make_tool_mission(max_tool_calls=1, max_replans=2)
    run, gate, _ = replanned(state, port, registry)
    assert run.replans_used == 1 and len(run.plans) == 2
    first_plan, second_plan = run.plans
    first, second = gate.invocations  # one invocation in each attempt, though the budget of each attempt is one
    assert (first.plan_id, first.result_stored) == (first_plan.plan_id, False)  # the timed-out call: charged to attempt one, stores nothing
    assert (second.plan_id, second.result_stored) == (second_plan.plan_id, True)  # not a duplicate (nothing was stored), and attempt two's budget was untouched
    assert first.args_digest == second.args_digest
    assert run.log.state.status is MissionStatus.COMPLETED and port.calls == 2


@pytest.fixture(params=["scripted", "mcp"])
def plain_port(request):
    port = CountingPort(ScriptedToolPort() if request.param == "scripted" else make_mcp_port())
    yield port
    port.close()


def test_a_duplicate_is_recognised_across_the_replanned_attempts_and_costs_no_budget(plain_port):
    # attempt one retrieves and succeeds at research but its analysis fails, so the mission replans; attempt two asks the same question and is served.
    state = make_tool_mission(max_tool_calls=1, max_replans=2)
    store = InMemoryArtifactStore()
    port = plain_port
    gate = ToolGate(registry=search_registry(), port=port, store=store)
    model = ScriptedModel(ScriptedCalls((cite_every_document, always_fails), then=cite_every_document))  # research ok, analysis fails, then everything ok
    agents = {
        RESEARCH_AGENT_ID: ResearchAgent(model=model, settings=make_settings(), store=store, tools=gate, search_tool_id=TOOL_ID),
        ANALYSIS_AGENT_ID: AnalysisAgent(model=model, settings=make_settings(), store=store),
    }
    with tempfile.TemporaryDirectory() as directory:
        run = run_with_replanning(
            state=state, limits=GENEROUS_LIMITS, registry=make_registry(), agents=agents, verifier=VerificationAgent(store=store),
            admission_guard_factory=admit_all, executor_factory=SequentialExecutor, clock=FixedClock(), ids=UuidEventIds(),
            strategy_ids=UuidStrategyIds(), plan_ids=UuidPlanIds(), candidate_generator=RuleBasedCandidateGenerator(), max_candidates=3,
            selector=DeterministicSelector(), store=JsonlExperienceStore.open(Path(directory) / "experience.jsonl"),
        )
    assert isinstance(run, ReplanRun) and run.replans_used == 1
    assert port.calls == 1 and len(gate.invocations) == 1  # attempt two's identical question was served, not invoked
    assert run.log.state.status is MissionStatus.COMPLETED
