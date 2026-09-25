"""``tool_facts_of`` and ``RecordingToolAccess``: how a call to the tool gate becomes a recorded fact (decisions.md D-203, D-206, D-207; V1.2 Step 4).

The mapping is pure and is checked outcome by outcome against real gate outcomes from the real gate; the wrapper is checked for what it returns, what it leaves
alone and what it hands the tracker. Nothing here reaches a real tool.
"""

import threading

import pytest

from eidos.agents import InMemoryArtifactStore, ToolFailureKind, ToolGate, ToolGateKind
from eidos.recording import ModelCallTracker, RecordingToolAccess, tool_facts_of
from eidos.state import ToolCallOutcome, ToolDenialReason

from eidos_recording_factories import FixedClock
from eidos_search_fixture import TOOL_ID, ScriptedToolPort, attempt_context, failing_port, make_tool_mission, search_registry


def outcome_of(*, port=None, arguments=None, registry=None, **mission):
    state = make_tool_mission(**mission)
    gate = ToolGate(registry=registry or search_registry(), port=port or ScriptedToolPort(), store=InMemoryArtifactStore())
    return state, gate, gate.call(attempt_context(state), TOOL_ID, {"query": "mission replay"} if arguments is None else arguments)


# --- the pure mapping, one gate outcome at a time ---------------------------------------------------------------------------------


def test_an_invoked_result_is_a_result_fact_with_its_digest_references_size_and_the_elapsed_time_it_was_given():
    _, _, outcome = outcome_of()
    fact = tool_facts_of(outcome, 37)
    assert (fact.tool_id, fact.outcome, fact.denial) == (TOOL_ID, ToolCallOutcome.RESULT, None)
    assert fact.args_digest == outcome.admission.args_digest and fact.result_refs == outcome.refs
    assert fact.result_bytes == outcome.result.size_bytes and fact.elapsed_ms == 37 and fact.invoked


@pytest.mark.parametrize("kind", list(ToolFailureKind), ids=lambda k: k.value)
def test_an_invoked_failure_is_the_same_named_outcome_with_its_digest_and_elapsed_time_and_no_answer(kind):
    _, _, outcome = outcome_of(port=failing_port(kind))
    fact = tool_facts_of(outcome, 5)
    assert fact.outcome is ToolCallOutcome(kind.value) and fact.args_digest == outcome.admission.args_digest
    assert (fact.result_refs, fact.result_bytes, fact.elapsed_ms, fact.denial) == ((), None, 5, None) and fact.invoked


def test_a_served_duplicate_is_a_served_fact_with_the_stored_references_and_size_and_no_elapsed_time_whatever_is_passed():
    state, gate, first = outcome_of()
    again = gate.call(attempt_context(state, 2), TOOL_ID, {"query": "mission replay"})
    assert again.kind is ToolGateKind.SERVED
    fact = tool_facts_of(again, 999)
    assert fact.outcome is ToolCallOutcome.SERVED_STORED and fact.result_refs == first.refs and fact.result_bytes == first.result.size_bytes
    assert fact.args_digest == first.admission.args_digest and fact.elapsed_ms is None and not fact.invoked


@pytest.mark.parametrize("arguments, mission, registry, reason", [
    ({}, {}, None, ToolDenialReason.INVALID_ARGUMENTS),
    (None, dict(allowed_actions=()), None, ToolDenialReason.ACTION_NOT_ALLOWED),
    (None, dict(max_tool_calls=None), None, ToolDenialReason.BUDGET_UNRESOLVED),
    (None, dict(max_tool_calls=0), None, ToolDenialReason.BUDGET_EXHAUSTED),
    (None, {}, search_registry(read_only=False), ToolDenialReason.NOT_READ_ONLY),
])
def test_a_denial_is_a_denied_fact_carrying_its_reason_and_nothing_else_whatever_elapsed_time_is_passed(arguments, mission, registry, reason):
    _, _, outcome = outcome_of(arguments=arguments, registry=registry, **mission)
    fact = tool_facts_of(outcome, 999)
    assert (fact.outcome, fact.denial) == (ToolCallOutcome.DENIED, reason)
    assert (fact.args_digest, fact.result_refs, fact.result_bytes, fact.elapsed_ms) == (None, (), None, None) and not fact.invoked


def test_a_call_that_named_no_valid_tool_is_recorded_with_the_id_it_named_verbatim():
    state = make_tool_mission()
    gate = ToolGate(registry=search_registry(), port=ScriptedToolPort(), store=InMemoryArtifactStore())
    fact = tool_facts_of(gate.call(attempt_context(state), " Not/A Tool ", {"query": "x"}), None)
    assert (fact.tool_id, fact.denial) == (" Not/A Tool ", ToolDenialReason.UNKNOWN_TOOL)


# --- the wrapper ------------------------------------------------------------------------------------------------------------------


class Inner:
    def __init__(self, outcome=None, error=None):
        self.outcome, self.error, self.seen = outcome, error, []

    def call(self, context, tool_id, arguments):
        self.seen.append((context, tool_id, dict(arguments)))
        if self.error is not None:
            raise self.error
        return self.outcome


def test_the_wrapper_returns_the_very_outcome_it_wrapped_and_passes_its_arguments_through_unchanged():
    state, _, outcome = outcome_of()
    inner, context = Inner(outcome), attempt_context(state)
    returned = RecordingToolAccess(inner, ModelCallTracker(), FixedClock()).call(context, TOOL_ID, {"query": "q", "limit": 2})
    assert returned is outcome and inner.seen == [(context, TOOL_ID, {"query": "q", "limit": 2})]


def test_inside_a_node_the_fact_is_added_for_that_node_and_outside_any_node_it_is_attributed_to_nothing():
    state, _, outcome = outcome_of()
    tracker = ModelCallTracker()
    access = RecordingToolAccess(Inner(outcome), tracker, FixedClock())
    access.call(attempt_context(state), TOOL_ID, {})
    assert tracker.current_tool_calls() is None  # outside any node: nothing was collected, and nothing was raised
    tracker.begin()
    access.call(attempt_context(state), TOOL_ID, {})
    access.call(attempt_context(state), TOOL_ID, {})
    assert [f.outcome for f in tracker.end_tool_calls()] == [ToolCallOutcome.RESULT] * 2


def test_the_elapsed_time_is_what_the_injected_monotonic_clock_measured_around_an_invocation_only():
    state, _, invoked = outcome_of()
    _, gate, _ = outcome_of()
    denied = gate.call(attempt_context(state), TOOL_ID, {})
    tracker = ModelCallTracker()
    clock = FixedClock(monotonic_step_ms=250)  # every reading is 250 ms after the last
    tracker.begin()
    RecordingToolAccess(Inner(invoked), tracker, clock).call(attempt_context(state), TOOL_ID, {})
    RecordingToolAccess(Inner(denied), tracker, clock).call(attempt_context(state), TOOL_ID, {})
    facts = tracker.end_tool_calls()
    assert [f.elapsed_ms for f in facts] == [250, None]


def test_an_exception_from_the_wrapped_access_passes_through_untouched_and_records_nothing():
    state = make_tool_mission()
    error, tracker = RuntimeError("the gate broke"), ModelCallTracker()
    tracker.begin()
    with pytest.raises(RuntimeError) as raised:
        RecordingToolAccess(Inner(error=error), tracker, FixedClock()).call(attempt_context(state), TOOL_ID, {})
    assert raised.value is error and tracker.end_tool_calls() == ()


def test_each_thread_records_only_its_own_nodes_calls():
    state, _, outcome = outcome_of()
    tracker, collected, barrier = ModelCallTracker(), {}, threading.Barrier(2)
    access = RecordingToolAccess(Inner(outcome), tracker, FixedClock())

    def node(name, calls):
        tracker.begin()
        barrier.wait()
        for _ in range(calls):
            access.call(attempt_context(state), TOOL_ID, {})
        barrier.wait()
        collected[name] = len(tracker.end_tool_calls())

    threads = [threading.Thread(target=node, args=("a", 1)), threading.Thread(target=node, args=("b", 3))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert collected == {"a": 1, "b": 3}
