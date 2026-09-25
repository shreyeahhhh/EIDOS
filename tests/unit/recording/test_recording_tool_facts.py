"""Recording tool-call facts: the tracker's tool collection, the recorder's hand-off, and a live recorded pass (decisions.md D-203, D-204; V1.2 Step 3).

No tool is invoked here. The facts are handed to a wrapper agent, which adds them through the tracker exactly as a recording tool port will; what is
under test is that they reach the right node's ``NODE_SETTLED`` in call order, are folded by the reducer, replay from the log alone, and that a run
without tools records exactly what it always recorded.
"""

import inspect
import threading

import pytest

from eidos.contracts import ArtifactRef, CapabilityId, MissionEventType, PlanStepKind, StepId
from eidos.recording import ModelCallTracker, Recorder, RecordingAgent, record_attempt, record_baseline
from eidos.replanning import run_with_replanning
from eidos.runtime import NodeResult, NodeStatus, WorkResult
from eidos.state import (
    EventLog,
    NodeSettledPayload,
    NodeStartedPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    dump_jsonl,
    execution_record,
    load_jsonl,
    replay,
)
from eidos.telemetry import project

from eidos_agents_factories import compiled_with, node_of
from eidos_recording_factories import FixedClock, SequentialIds, baseline_mission, new_rig, record, unrecorded
from eidos_runtime_factories import context_for
from eidos_state_factories import RESEARCH_AGENT, created
from eidos_tool_fact_factories import ToolFactsInjector, denied_call, failed_call, result_call, served_call
from eidos_v04_registry import RESEARCH_AGENT_ID


def settled_payload(log, step: str) -> NodeSettledPayload:
    return next(r.payload for r in log.records if r.event.type is MissionEventType.NODE_SETTLED and r.payload.result.step_id == step)


# --- the tracker's tool collection ------------------------------------------------------------------------------------------------


def test_the_tracker_collects_a_nodes_tool_calls_in_call_order_and_hands_them_over_once():
    tracker = ModelCallTracker()
    calls = (result_call(number=1), denied_call(), served_call(number=1))
    tracker.begin()
    for call in calls:
        tracker.current_tool_calls().append(call)
    assert tracker.end_tool_calls() == calls
    assert tracker.end_tool_calls() == ()  # ended: nothing is carried into the next node
    assert tracker.current_tool_calls() is None


def test_a_tool_call_outside_any_node_is_attributed_to_nothing():
    assert ModelCallTracker().current_tool_calls() is None


def test_beginning_a_node_starts_both_collections_empty_and_discards_what_a_previous_node_left():
    tracker = ModelCallTracker()
    tracker.begin()
    tracker.current_tool_calls().append(result_call())
    tracker.begin()
    assert tracker.current_tool_calls() == [] and tracker.current() == []


def test_the_two_collections_are_independent_ending_one_leaves_the_other():
    tracker = ModelCallTracker()
    tracker.begin()
    tracker.current_tool_calls().append(result_call())
    assert tracker.end() == ()  # the model calls, exactly as always
    assert tracker.current_tool_calls() == [result_call()]
    assert tracker.end_tool_calls() == (result_call(),)


def test_each_thread_collects_only_its_own_nodes_tool_calls():
    tracker = ModelCallTracker()
    collected, barrier = {}, threading.Barrier(2)

    def node(name, calls):
        tracker.begin()
        barrier.wait()
        tracker.current_tool_calls().extend(calls)
        barrier.wait()
        collected[name] = tracker.end_tool_calls()

    threads = [
        threading.Thread(target=node, args=("a", (result_call(number=1),))),
        threading.Thread(target=node, args=("b", (failed_call(number=2), denied_call()))),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert collected == {"a": (result_call(number=1),), "b": (failed_call(number=2), denied_call())}


# --- the recorder's hand-off ------------------------------------------------------------------------------------------------------


def open_recorder():
    state, plan = baseline_mission()
    log = EventLog()
    recorder = Recorder(log=log, clock=FixedClock(), ids=SequentialIds(), tenant_id=state.tenant_id, mission_id=state.mission_id)
    recorder.record(created(state))
    return state, plan, log, recorder


def test_a_node_settled_live_carries_the_tool_calls_the_recorder_was_handed_for_it():
    state, plan, log, recorder = open_recorder()
    recorder.record(PlanGeneratedPayload(plan=plan))
    recorder.record(PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version))
    recorder.record(NodeStartedPayload(plan_id=plan.plan_id, step_id=StepId("gather"), kind=PlanStepKind.AGENT, capability=CapabilityId("research"), agent_id=RESEARCH_AGENT))
    calls = (result_call(number=1), denied_call())
    assert recorder.tool_calls(StepId("gather")) == ()  # nothing handed over yet
    recorder.note_tool_calls(StepId("gather"), calls)
    result = NodeResult(step_id=StepId("gather"), kind=PlanStepKind.AGENT, status=NodeStatus.SUCCEEDED, artifact=ArtifactRef("artifact:gather"))
    assert recorder.settle_live(plan.plan_id, result, 10, (), None).applied
    assert settled_payload(log, "gather").tool_calls == calls
    assert log.state.tool_calls_used == 1
    assert recorder.tool_calls(StepId("gather")) == calls and recorder.tool_calls(StepId("analyse")) == ()


# --- the agent wrapper: exactly the recorder calls it always made, plus one only when there is something to say ----------------------


class Recording:
    """A recorder double that notes what it is asked. ``with_tools`` decides whether it has the tool hand-off at all."""

    def __init__(self, *, with_tools: bool):
        self.calls, self._ticks = [], 0
        if with_tools:
            self.note_tool_calls = lambda step_id, tool_calls: self.calls.append(("tools", step_id, tool_calls))

    def record(self, payload):
        self.calls.append(("record", payload))

    def monotonic_ns(self):
        self._ticks += 1
        return self._ticks * 1_000_000_000

    def duration_ms(self, started):
        return (self.monotonic_ns() - started) // 1_000_000

    def note_observation(self, step_id, duration_ms, calls):
        self.calls.append(("observe", step_id, duration_ms, calls))

    def settle_live(self, plan_id, result, duration_ms, calls, verification):
        self.calls.append(("settle", result, duration_ms, calls, verification))

    def kinds(self):
        return [call[0] for call in self.calls]


class Inner:
    """A work agent that adds ``calls`` through the tracker and returns ``result`` (or raises ``error``)."""

    def __init__(self, tracker, calls, result=None, error=None):
        self.tracker, self.calls, self.result, self.error = tracker, calls, result, error

    def run(self, context, node):
        self.tracker.current_tool_calls().extend(self.calls)
        if self.error is not None:
            raise self.error
        return self.result


def wrapper_setup():
    compiled = compiled_with({"a": ""})
    return context_for(compiled), node_of(compiled, StepId("a"))


def test_a_node_that_made_no_tool_calls_makes_exactly_the_recorder_calls_it_always_made():
    context, node = wrapper_setup()
    recorder, tracker = Recording(with_tools=False), ModelCallTracker()  # a double with no tool hand-off at all: it must never be asked for one
    result = WorkResult.produced("artifact:a")
    RecordingAgent(RESEARCH_AGENT_ID, Inner(tracker, (), result), recorder, tracker).run(context, node)
    assert recorder.kinds() == ["record", "observe", "settle"]


def test_a_node_that_made_tool_calls_hands_them_over_before_it_is_observed_and_settled():
    context, node = wrapper_setup()
    recorder, tracker = Recording(with_tools=True), ModelCallTracker()
    calls = (result_call(number=1), failed_call(number=2))
    result = WorkResult.produced("artifact:a")
    RecordingAgent(RESEARCH_AGENT_ID, Inner(tracker, calls, result), recorder, tracker).run(context, node)
    assert recorder.kinds() == ["record", "tools", "observe", "settle"]
    assert recorder.calls[1][1:] == (node.step_id, calls)


def test_an_agent_that_raises_after_making_tool_calls_still_hands_them_over_and_the_exception_passes_through_untouched():
    context, node = wrapper_setup()
    recorder, tracker, error = Recording(with_tools=True), ModelCallTracker(), RuntimeError("the agent gave up")
    calls = (result_call(),)
    with pytest.raises(RuntimeError) as raised:
        RecordingAgent(RESEARCH_AGENT_ID, Inner(tracker, calls, error=error), recorder, tracker).run(context, node)
    assert raised.value is error
    assert recorder.kinds() == ["record", "tools", "observe"]  # nothing settled live: the executor's own FAILED result is recorded after the run
    assert recorder.calls[1][1:] == (node.step_id, calls) and tracker.current_tool_calls() is None


# --- a live recorded pass over the real agents ------------------------------------------------------------------------------------


GATHER = (result_call(number=1, documents=2), denied_call())
ANALYSE = (served_call(number=1, documents=2),)


def run_with_tools(facts=None):
    state, plan = baseline_mission()
    rig = new_rig(state)
    rig.agents = {agent_id: ToolFactsInjector(agent, rig.tracker, facts or {"gather": GATHER, "analyse": ANALYSE}) for agent_id, agent in rig.agents.items()}
    run, _ = record(state, plan, rig)
    return state, plan, run


def test_the_recorded_pass_settles_each_node_with_the_tool_calls_it_made_in_call_order():
    _, _, run = run_with_tools()
    assert settled_payload(run.log, "gather").tool_calls == GATHER
    assert settled_payload(run.log, "analyse").tool_calls == ANALYSE
    assert settled_payload(run.log, "check").tool_calls == ()
    assert run.refused == () and run.discrepancies == ()


def test_the_counter_is_folded_live_and_replay_reproduces_the_state_and_the_facts_without_any_tool():
    _, _, run = run_with_tools()
    assert run.log.state.tool_calls_used == 1  # one invocation; the denial and the served duplicate reached no tool
    replayed = replay(run.log.records)
    assert replayed.state == run.log.state
    record_of = execution_record(run.log.records)
    assert record_of.tool_calls_used == 1
    assert [step.tool_calls for step in record_of.steps] == [GATHER, ANALYSE, ()]
    reloaded = load_jsonl(dump_jsonl(run.log.records))
    assert reloaded.records == run.log.records and replay(reloaded.records).state == run.log.state


def test_the_recorded_pass_reports_exactly_what_the_same_pass_unrecorded_reports():
    state, plan, run = run_with_tools()
    assert run.report == unrecorded(state, plan)


def test_the_model_calls_and_every_other_counter_are_what_they_are_without_tool_facts():
    state, plan, run = run_with_tools()
    plain, _ = record(state, plan)
    for step in ("gather", "analyse", "check"):
        assert settled_payload(run.log, step).model_calls == settled_payload(plain.log, step).model_calls
        assert settled_payload(run.log, step).duration_ms == settled_payload(plain.log, step).duration_ms
    with_tools, without = run.log.state, plain.log.state
    assert (with_tools.agent_calls_used, with_tools.tokens_used, with_tools.execution_time_used_ms) == (
        without.agent_calls_used, without.tokens_used, without.execution_time_used_ms,
    )
    assert without.tool_calls_used == 0


def test_a_pass_with_no_tool_facts_records_a_log_that_differs_from_before_only_by_the_empty_new_field():
    state, plan = baseline_mission()
    run, _ = record(state, plan)
    text = dump_jsonl(run.log.records)
    assert text.count('"tool_calls":[]') == 3 and '"result_refs"' not in text
    assert run.log.state.tool_calls_used == 0


def test_telemetry_reports_the_recorded_counter_through_its_existing_field():
    _, _, run = run_with_tools()
    assert project(run.log.records).tool_calls_used == 1


def test_the_same_pass_twice_records_byte_identical_logs():
    _, _, first = run_with_tools()
    _, _, second = run_with_tools()
    assert dump_jsonl(first.log.records) == dump_jsonl(second.log.records)


def test_an_agent_that_raises_has_its_tool_calls_recorded_with_the_settlement_the_executor_reports():
    state, plan = baseline_mission()
    rig = new_rig(state)
    facts = {"gather": (result_call(number=1), failed_call(number=2, elapsed_ms=None))}
    rig.agents = {
        agent_id: ToolFactsInjector(agent, rig.tracker, facts, raise_after=RuntimeError("the agent failed")) for agent_id, agent in rig.agents.items()
    }
    run, _ = record(state, plan, rig)
    gather = settled_payload(run.log, "gather")
    assert gather.result.status is NodeStatus.FAILED and gather.dispatched
    assert gather.tool_calls == facts["gather"]
    assert run.log.state.tool_calls_used == 2 and run.discrepancies == ()
    assert replay(run.log.records).state == run.log.state


def test_a_node_that_never_ran_carries_no_tool_calls_even_when_an_earlier_node_made_some():
    state, plan = baseline_mission()
    rig = new_rig(state)
    facts = {"gather": (result_call(number=1),)}
    rig.agents = {
        agent_id: ToolFactsInjector(agent, rig.tracker, facts, raise_after=RuntimeError("the agent failed")) for agent_id, agent in rig.agents.items()
    }
    run, _ = record(state, plan, rig)
    for step in ("analyse", "check"):
        skipped = settled_payload(run.log, step)
        assert not skipped.dispatched and skipped.tool_calls == ()


def test_two_recorded_passes_do_not_share_tool_facts():
    # a fresh Recorder per pass keeps tool facts, like every other observation, out of another pass's nodes
    state, plan = baseline_mission()
    first_rig, second_rig = new_rig(state), new_rig(state)
    for rig, facts in ((first_rig, {"gather": (result_call(number=1),)}), (second_rig, {})):
        rig.agents = {agent_id: ToolFactsInjector(agent, rig.tracker, facts) for agent_id, agent in rig.agents.items()}
    first, _ = record(state, plan, first_rig)
    second, _ = record(state, plan, second_rig)
    assert first.log.state.tool_calls_used == 1 and second.log.state.tool_calls_used == 0


# --- what this step did not touch (D-204 stays open) --------------------------------------------------------------------------------


def test_the_public_recording_and_replanning_entry_points_keep_their_signatures():
    assert list(inspect.signature(record_baseline).parameters) == [
        "state", "plan", "limits", "registry", "agents", "verifier", "admission_guard", "executor_factory", "clock", "ids", "prior", "log", "tracker",
    ]
    assert list(inspect.signature(record_attempt).parameters) == [
        "state", "plan", "limits", "registry", "agents", "verifier", "admission_guard", "executor_factory", "clock", "ids", "log", "prior", "tracker",
    ]
    assert "tracker" not in inspect.signature(run_with_replanning).parameters  # D-204 item 1: not fixed here
