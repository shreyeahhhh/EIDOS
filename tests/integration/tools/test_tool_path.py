"""The whole EIDOS-side tool path, end to end, over one port kind at a time (decisions.md D-203, D-204, D-205, D-206, D-207; V1.2 Step 4).

    Research -> tool gate (admission first) -> tool port -> ToolResult -> artifacts -> verification -> recording -> replay

Every scenario runs unchanged for every port kind listed in ``PORT_KINDS``. Phase A has one, the scripted port; Phase B adds the real one. That is the point
of the seam: the agent, the gate, the artifacts, the verifier and the recording are the same objects whichever port answers, so a scenario that passes
for both proves the transport is replaceable without changing a contract. The agents, the verifier, the store and the recorder are the real ones; only the
model and the tool provider are scripted or local.
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from eidos.agents import (
    AnalysisAgent,
    InMemoryArtifactStore,
    ResearchAgent,
    ToolFailure,
    ToolFailureKind,
    ToolGate,
    VerificationAgent,
    parse_tool_document_ref,
)
from eidos.contracts import AutonomyLevel, MissionEventType, MissionStatus, StepId
from eidos.recording import ModelCallTracker, RecordingModel, RecordingToolAccess, record_baseline
from eidos.runtime import NodeStatus, RunOutcome, SequentialExecutor, VerificationVerdict
from eidos.state import (
    MissionFailureCause,
    ToolCallOutcome,
    ToolDenialReason,
    dump_jsonl,
    execution_record,
    load_jsonl,
    replay,
    replay_jsonl,
)
from eidos.telemetry import project

from eidos_agents_factories import ScriptedModel, make_settings
from eidos_mcp_fixture import make_mcp_port
from eidos_mission_factories import make_mission_plan
from eidos_recording_factories import FixedClock, SequentialIds
from eidos_runtime_factories import admit_all
from eidos_search_fixture import (
    EXPECTED_DOCUMENT_IDS,
    GOAL,
    TOOL_ID,
    CountingPort,
    ScriptedToolPort,
    cite_every_document,
    make_tool_mission,
    search_registry,
    tool_mission_plan,
)
from eidos_v04_registry import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID, make_registry
from eidos_validation_factories import make_system_limits
from search_documents_corpus import keyword_search

ROOT = Path(__file__).resolve().parents[3]
PORT_KINDS = ["scripted", "mcp"]

# How the real reference server is made to fail in each typed way (the scripted port is simply told to). A timeout needs a short allowlist timeout, which
# ``failure_registry`` supplies for both kinds so the two are always compared under the same entry.
FAULT_FOR = {
    ToolFailureKind.TIMEOUT: "slow",
    ToolFailureKind.UNAVAILABLE: "crash",
    ToolFailureKind.TOOL_ERROR: "tool_error",
    ToolFailureKind.MALFORMED_RESULT: "malformed",
    ToolFailureKind.RESULT_TOO_LARGE: "oversize",
}


def failure_registry(kind):
    return search_registry(timeout_seconds=0.5) if kind is ToolFailureKind.TIMEOUT else search_registry()


@pytest.fixture(params=PORT_KINDS)
def make_port(request):
    """A factory for a counted port of the parametrized kind: ``make_port(failure=None)``. ``failure`` makes that kind of port fail in that typed way."""
    made = []

    def factory(failure=None):
        if request.param == "scripted":
            return CountingPort(ScriptedToolPort(ToolFailure(kind=failure, message="scripted") if failure else None))
        port = make_mcp_port(fault=FAULT_FOR[failure] if failure else "", registry=failure_registry(failure) if failure else None)
        made.append(port)
        return CountingPort(port)

    factory.kind = request.param
    yield factory
    for port in made:
        port.close()


@dataclass
class ToolPath:
    state: object
    plan: object
    store: InMemoryArtifactStore
    gate: ToolGate
    run: object
    port: object

    @property
    def log(self):
        return self.run.log

    def settled(self, step):
        return next(r.payload for r in self.log.records if r.event.type is MissionEventType.NODE_SETTLED and r.payload.result.step_id == step)


def run_path(port, *, state=None, plan=None, tools=True, search_tool_id=TOOL_ID, registry=None) -> ToolPath:
    state = state or make_tool_mission()
    plan = plan or tool_mission_plan(state)
    store, tracker, clock = InMemoryArtifactStore(), ModelCallTracker(), FixedClock()
    gate = ToolGate(registry=registry or search_registry(), port=port, store=store)
    model = RecordingModel(ScriptedModel(cite_every_document), tracker)
    research = ResearchAgent(
        model=model, settings=make_settings(), store=store,
        **(dict(tools=RecordingToolAccess(gate, tracker, clock), search_tool_id=search_tool_id) if tools else {}),
    )
    agents = {RESEARCH_AGENT_ID: research, ANALYSIS_AGENT_ID: AnalysisAgent(model=model, settings=make_settings(), store=store)}
    run = record_baseline(
        state=state, plan=plan, limits=make_system_limits(), registry=make_registry(), agents=agents, verifier=VerificationAgent(store=store),
        admission_guard=admit_all(), executor_factory=SequentialExecutor, clock=clock, ids=SequentialIds(), tracker=tracker,
    )
    assert run.refused == () and run.discrepancies == ()
    return ToolPath(state, plan, store, gate, run, port)


# --- a mission with no supplied documents completes verified, on the strength of what the tool retrieved -------------------------------


def test_a_mission_with_no_supplied_documents_completes_verified_because_the_tool_retrieved_the_evidence(make_port):
    path = run_path(make_port())
    assert path.run.report.run.outcome is RunOutcome.FINISHED and path.run.report.run.verified
    assert path.log.state.status is MissionStatus.COMPLETED
    check = path.settled("check")
    assert check.verification.verdict is VerificationVerdict.PASS
    assert "3 distinct supplied source(s) reached, 2 required" in check.verification.reason


def test_the_same_mission_without_tool_access_returns_no_result_as_it_always_did(make_port):
    path = run_path(make_port(), tools=False)
    assert path.port.calls == 0
    gather = path.settled("gather")
    assert gather.result.status is NodeStatus.NO_RESULT and gather.tool_calls == ()
    assert path.log.state.status is MissionStatus.FAILED and path.log.state.tool_calls_used == 0


def test_the_tool_call_is_recorded_with_its_identity_outcome_request_digest_references_size_and_elapsed_time(make_port):
    path = run_path(make_port())
    (fact,) = path.settled("gather").tool_calls
    found = keyword_search(GOAL)
    assert (fact.tool_id, fact.outcome) == (TOOL_ID, ToolCallOutcome.RESULT)
    assert [str(r).rsplit(":", 1)[1] for r in fact.result_refs] == [d for d, _ in found] == list(EXPECTED_DOCUMENT_IDS)
    assert fact.result_bytes == sum(len(d.encode()) + len(t.encode()) for d, t in found)
    assert fact.elapsed_ms == 1000 and len(fact.args_digest) == 64  # the recorder's fixed clock: one reading step across the call
    assert path.settled("analyse").tool_calls == () and path.settled("check").tool_calls == ()
    assert path.log.state.tool_calls_used == 1 and project(path.log.records).tool_calls_used == 1


def test_end_to_end_evidence_is_traceable_from_the_conclusion_to_the_tool_invocation_and_its_request_digest(make_port):
    path = run_path(make_port())
    (fact,) = path.settled("gather").tool_calls
    conclusion = path.store.get_step_artifact(path.state.execution_id, StepId("analyse"))  # the analysis is what the verifier read
    evidence = [r for r in conclusion.source_refs if r != "artifact:gather"]
    assert set(evidence) == set(fact.result_refs)  # conclusion -> evidence
    for ref in evidence:
        artifact = path.store.get(path.state.execution_id, ref)  # evidence -> the stored tool result
        tool_id, digest, document_id = parse_tool_document_ref(ref)
        assert (tool_id, digest) == (fact.tool_id, fact.args_digest)  # -> the invocation and its request digest, from the reference alone
        assert artifact.content == dict(keyword_search(GOAL))[document_id]
    record = execution_record(path.log.records)
    assert [c.args_digest for s in record.steps for c in s.tool_calls] == [fact.args_digest]  # the recorded fact, found in the step record
    assert path.settled("check").verification.verdict is VerificationVerdict.PASS  # -> verification


# --- admission is before invocation, and every refusal is typed and recorded -------------------------------------------------------


REFUSALS = [
    ("action not allowed", dict(state=dict(allowed_actions=())), {}, ToolDenialReason.ACTION_NOT_ALLOWED),
    ("autonomy too low", dict(state=dict(autonomy_level=AutonomyLevel.RECOMMEND_ONLY)), {}, ToolDenialReason.AUTONOMY_TOO_LOW),
    ("budget unresolved", dict(state=dict(max_tool_calls=None)), {}, ToolDenialReason.BUDGET_UNRESOLVED),
    ("budget of zero", dict(state=dict(max_tool_calls=0)), {}, ToolDenialReason.BUDGET_EXHAUSTED),
    ("goal too long to be a query", dict(state=dict(goal="w" * 300)), {}, ToolDenialReason.INVALID_ARGUMENTS),
    ("unknown tool", {}, dict(search_tool_id="docs/nope"), ToolDenialReason.UNKNOWN_TOOL),
    ("not read-only", {}, dict(registry=search_registry(read_only=False)), ToolDenialReason.NOT_READ_ONLY),
]


@pytest.mark.parametrize("build, options, reason", [r[1:] for r in REFUSALS], ids=[r[0] for r in REFUSALS])
def test_a_refused_call_never_reaches_the_port_is_recorded_typed_and_costs_nothing(make_port, build, options, reason):
    state = make_tool_mission(**build.get("state", {}))
    path = run_path(make_port(), state=state, **options)
    assert path.port.calls == 0 and path.port.starts == 0  # no request reached the port, and a real server was not even launched
    (fact,) = path.settled("gather").tool_calls
    assert (fact.outcome, fact.denial) == (ToolCallOutcome.DENIED, reason)
    assert fact.args_digest is None and fact.result_refs == () and fact.elapsed_ms is None
    assert path.log.state.tool_calls_used == 0 and path.store.supplied(state.execution_id) == ()
    gather = path.settled("gather")
    assert gather.result.status is NodeStatus.NO_RESULT and reason.value in gather.result.reason  # the agent reports the typed denial
    assert path.log.state.status is MissionStatus.FAILED


# --- a tool can fail in typed ways, and each is recorded --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", list(ToolFailureKind), ids=lambda k: k.value)
def test_a_failed_invocation_is_recorded_with_its_typed_outcome_and_is_charged(make_port, kind):
    path = run_path(make_port(kind), registry=failure_registry(kind))
    (fact,) = path.settled("gather").tool_calls
    assert fact.outcome is ToolCallOutcome(kind.value) and fact.result_refs == () and fact.elapsed_ms == 1000
    assert path.port.calls == 1 and path.log.state.tool_calls_used == 1
    expected = NodeStatus.FAILED if kind in (ToolFailureKind.UNAVAILABLE, ToolFailureKind.TIMEOUT, ToolFailureKind.TOOL_ERROR) else NodeStatus.NO_RESULT
    assert path.settled("gather").result.status is expected


def test_a_result_over_the_allowlist_size_bound_is_a_typed_failure_and_nothing_is_stored(make_port):
    path = run_path(make_port(), registry=search_registry(max_result_bytes=100))
    (fact,) = path.settled("gather").tool_calls
    assert fact.outcome is ToolCallOutcome.RESULT_TOO_LARGE and path.store.supplied(path.state.execution_id) == ()


# --- duplicates -------------------------------------------------------------------------------------------------------------------


def two_researchers(state):
    return make_mission_plan(
        state, {"gather": "", "gather2": "gather", "analyse": "gather2", "check": "analyse"}, verify=("check",),
        capability_of={"gather": "research", "gather2": "research", "analyse": "cost"},
    )


def test_a_repeated_call_in_the_execution_is_served_from_the_stored_artifacts_not_invoked_and_costs_no_budget(make_port):
    state = make_tool_mission(max_tool_calls=1)
    path = run_path(make_port(), state=state, plan=two_researchers(state))
    first, again = path.settled("gather").tool_calls[0], path.settled("gather2").tool_calls[0]
    assert (first.outcome, again.outcome) == (ToolCallOutcome.RESULT, ToolCallOutcome.SERVED_STORED)
    assert again.args_digest == first.args_digest and again.result_refs == first.result_refs and again.result_bytes == first.result_bytes
    assert again.elapsed_ms is None and first.elapsed_ms == 1000
    assert path.port.calls == 1 and path.log.state.tool_calls_used == 1 and len(path.gate.invocations) == 1
    assert path.log.state.status is MissionStatus.COMPLETED  # the budget of one was enough for two research steps


# --- recording and replay ---------------------------------------------------------------------------------------------------------


def test_replay_reproduces_the_state_and_the_tool_facts_from_the_log_alone_and_invokes_nothing(make_port):
    path = run_path(make_port())
    calls_before, starts_before, ledger_before = path.port.calls, path.port.starts, path.gate.invocations
    replayed = replay(path.log.records)
    assert replayed.state == path.log.state
    text = dump_jsonl(path.log.records)
    assert load_jsonl(text).records == path.log.records and replay_jsonl(text).state == path.log.state
    assert execution_record(load_jsonl(text).records) == execution_record(path.log.records)
    assert (path.port.calls, path.port.starts, path.gate.invocations) == (calls_before, starts_before, ledger_before)  # neither port, server nor gate was touched


def test_the_recorded_pass_reports_what_the_pass_reports(make_port):
    path = run_path(make_port())
    assert path.run.report.run.verified and path.run.report.stopped_at is None
    assert [r.result.status for r in (path.settled(s) for s in ("gather", "analyse", "check"))] == [NodeStatus.SUCCEEDED] * 3


def test_a_failed_tool_call_makes_a_failed_mission_with_the_cause_recorded(make_port):
    path = run_path(make_port(ToolFailureKind.TIMEOUT), registry=failure_registry(ToolFailureKind.TIMEOUT))
    (failed,) = [r.payload for r in path.log.records if r.event.type is MissionEventType.MISSION_FAILED]
    assert failed.cause is MissionFailureCause.EXECUTION_FAILED


def test_the_recorded_log_is_byte_identical_whichever_port_answers_the_transport_is_replaceable_behind_the_seam(make_port):
    with_this_port = dump_jsonl(run_path(make_port()).log.records)
    with_the_scripted_port = dump_jsonl(run_path(CountingPort(ScriptedToolPort())).log.records)
    assert with_this_port == with_the_scripted_port


STORY = r"""
import hashlib, sys
sys.path[:0] = ['src', 'tests/support', 'tests/integration/tools']
from test_tool_path import run_path
from eidos_search_fixture import CountingPort, ScriptedToolPort
from eidos_mcp_fixture import make_mcp_port
from eidos.state import dump_jsonl

kind = sys.argv[1]
port = CountingPort(ScriptedToolPort()) if kind == "scripted" else CountingPort(make_mcp_port())
try:
    path = run_path(port)
    print(hashlib.sha256(dump_jsonl(path.log.records).encode()).hexdigest())
finally:
    port.close()
"""


@pytest.mark.parametrize("kind", ["scripted", "mcp"])
@pytest.mark.parametrize("seed", ["1", "42", "112233", "2718281828"])
def test_the_recorded_log_of_the_whole_path_is_byte_identical_under_any_hash_seed(kind, seed):
    def digest(hash_seed):
        completed = subprocess.run(
            [sys.executable, "-c", STORY, kind], capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED=hash_seed),
        )
        assert completed.returncode == 0, completed.stderr
        return completed.stdout.strip().splitlines()[-1]

    assert digest(seed) == digest("0")
