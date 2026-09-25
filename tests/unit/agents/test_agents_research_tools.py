"""The Research agent's optional tool access (decisions.md D-140, D-203, D-207; V1.2 Step 4, Phase A).

Real agent, real gate, real allowlist entry and real artifact store over a scripted model and a scripted tool provider. The agent asks the one approved
tool once per run with the mission goal as the query, and works from whatever documents then exist; it never knows which provider answered.
"""

import ast
from pathlib import Path

import pytest

from eidos.agents import (
    InMemoryArtifactStore,
    ResearchAgent,
    ToolDocument,
    ToolFailureKind,
    ToolGate,
    ToolResult,
)
from eidos.runtime import WorkStatus

from eidos_agents_factories import ScriptedModel, compiled_with, doc, make_settings, node_of
from eidos_search_fixture import (
    EXPECTED_DOCUMENT_IDS,
    GOAL,
    TOOL_ID,
    ScriptedToolPort,
    attempt_context,
    cite_every_document,
    failing_port,
    make_tool_mission,
    search_registry,
)
from eidos.contracts import StepId

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"


def build(*, port=None, supplied=(), tool_id=TOOL_ID, with_tools=True, **mission):
    state = make_tool_mission(**mission)
    port = port if port is not None else ScriptedToolPort()
    store = InMemoryArtifactStore()
    for document in supplied:
        store.put_supplied(state.execution_id, document)
    gate = ToolGate(registry=search_registry(), port=port, store=store)
    model = ScriptedModel(cite_every_document)
    kwargs = dict(tools=gate, search_tool_id=tool_id) if with_tools else {}
    agent = ResearchAgent(model=model, settings=make_settings(), store=store, **kwargs)
    return state, agent, model, port, store, gate


def run(agent, state, step="gather", plan=1):
    compiled = compiled_with({step: ""})
    return agent.run(attempt_context(state, plan), node_of(compiled, StepId(step)))


# --- a run that uses the tool ----------------------------------------------------------------------------------------------------


def test_with_no_documents_supplied_the_agent_searches_and_researches_what_it_found():
    state, agent, model, port, store, gate = build()
    result = run(agent, state)
    assert result.status is WorkStatus.PRODUCED and result.artifact == "artifact:gather"
    assert port.calls == 1 and len(model.requests) == 1
    (request,) = port.requests
    assert [(a.name, a.value) for a in request.arguments] == [("query", GOAL)]  # the goal itself, verbatim
    produced = store.get_step_artifact(state.execution_id, StepId("gather"))
    retrieved = [a.ref for a in store.supplied(state.execution_id)]
    assert [str(r).rsplit(":", 1)[1] for r in retrieved] and set(produced.source_refs) == set(retrieved)
    assert sorted(str(r).rsplit(":", 1)[1] for r in retrieved) == sorted(EXPECTED_DOCUMENT_IDS)


def test_the_model_is_shown_exactly_the_documents_the_tool_returned_each_under_its_own_reference():
    state, agent, model, _, store, _ = build()
    run(agent, state)
    prompt = model.requests[0].prompt
    for artifact in store.supplied(state.execution_id):
        assert f"[[{artifact.ref}]] (text/plain)\n{artifact.content}" in prompt
    assert f"Mission goal: {GOAL}" in prompt


def test_the_query_is_the_goal_with_its_surrounding_whitespace_removed_and_nothing_else():
    state, agent, _, port, _, _ = build(goal="  Explain replay  \n")
    run(agent, state)
    assert [(a.name, a.value) for a in port.requests[0].arguments] == [("query", "Explain replay")]


def test_a_second_research_step_of_the_same_execution_is_served_the_stored_documents_and_the_tool_is_not_reached_again():
    state, agent, model, port, store, gate = build(max_tool_calls=1)
    first, second = run(agent, state, "gather"), run(agent, state, "gather_two")
    assert first.status is second.status is WorkStatus.PRODUCED
    assert port.calls == 1 and len(gate.invocations) == 1 and len(model.requests) == 2
    assert model.requests[0].prompt == model.requests[1].prompt  # the same documents, in the same order


def test_the_agent_hands_the_gate_the_context_of_the_plan_attempt_it_is_running_in():
    state, agent, _, _, _, gate = build()
    run(agent, state, plan=3)
    (record,) = gate.invocations
    assert record.plan_id == attempt_context(state, 3).plan_id and record.execution_id == state.execution_id


# --- when the tool gives nothing usable -------------------------------------------------------------------------------------------


def test_a_refused_call_with_nothing_to_work_from_is_no_result_naming_the_typed_denial_and_the_model_is_never_asked():
    state, agent, model, port, _, _ = build(max_tool_calls=None)
    result = run(agent, state)
    assert result.status is WorkStatus.NO_RESULT and "denied (budget_unresolved)" in result.reason
    assert port.calls == 0 and model.requests == []


@pytest.mark.parametrize("kind, status", [
    (ToolFailureKind.UNAVAILABLE, WorkStatus.FAILED),
    (ToolFailureKind.TIMEOUT, WorkStatus.FAILED),
    (ToolFailureKind.TOOL_ERROR, WorkStatus.FAILED),
    (ToolFailureKind.MALFORMED_RESULT, WorkStatus.NO_RESULT),
    (ToolFailureKind.RESULT_TOO_LARGE, WorkStatus.NO_RESULT),
], ids=lambda x: getattr(x, "value", None))
def test_a_tool_failure_with_nothing_to_work_from_is_read_like_a_model_failure(kind, status):
    state, agent, model, _, _, _ = build(port=failing_port(kind))
    result = run(agent, state)
    assert result.status is status and f"the tool failed ({kind.value})" in result.reason and model.requests == []


def test_a_search_that_found_nothing_is_no_result():
    state, agent, model, _, _, _ = build(port=ScriptedToolPort(ToolResult(documents=())))
    result = run(agent, state)
    assert result.status is WorkStatus.NO_RESULT and "found no documents" in result.reason and model.requests == []


def test_a_goal_the_allowlist_entry_will_not_accept_as_a_query_is_refused_typed_not_truncated():
    state, agent, _, port, _, _ = build(goal="w" * 300)
    result = run(agent, state)
    assert result.status is WorkStatus.NO_RESULT and "denied (invalid_arguments)" in result.reason and port.calls == 0


def test_a_goal_that_is_only_whitespace_is_no_query_the_tool_is_not_called_and_it_says_what_it_always_said():
    state, agent, model, port, _, gate = build(goal="   	 ")
    result = run(agent, state)
    assert result.status is WorkStatus.NO_RESULT and result.reason == "no documents were supplied, so there is nothing to research"
    assert port.calls == 0 and gate.invocations == () and model.requests == []


def test_a_failed_or_refused_tool_never_stops_a_run_that_has_documents_to_work_from():
    for kwargs in (dict(port=failing_port(ToolFailureKind.TIMEOUT)), dict(max_tool_calls=None), dict(max_tool_calls=0)):
        state, agent, model, _, _, _ = build(supplied=(doc("doc:1", "Supplied text about replay."),), **kwargs)
        result = run(agent, state)
        assert result.status is WorkStatus.PRODUCED and len(model.requests) == 1 and "[[doc:1]]" in model.requests[0].prompt


def test_supplied_documents_and_retrieved_ones_are_read_together_in_a_stable_order():
    state, agent, model, _, store, _ = build(supplied=(doc("doc:1", "Supplied text."),))
    run(agent, state)
    shown = [artifact.ref for artifact in store.supplied(state.execution_id)]
    assert shown == sorted(shown) and str(shown[0]).startswith("doc:") and len(shown) == 1 + len(EXPECTED_DOCUMENT_IDS)


# --- an agent without tool access is what it always was ---------------------------------------------------------------------------


def test_an_agent_built_without_tools_never_searches_and_says_what_it_always_said():
    state, agent, model, port, _, gate = build(with_tools=False)
    result = run(agent, state)
    assert result.status is WorkStatus.NO_RESULT and result.reason == "no documents were supplied, so there is nothing to research"
    assert port.calls == 0 and model.requests == [] and gate.invocations == ()


def test_tool_access_and_the_tool_to_search_with_are_given_together_or_not_at_all():
    store = InMemoryArtifactStore()
    gate = ToolGate(registry=search_registry(), port=ScriptedToolPort(), store=store)
    with pytest.raises(ValueError):
        ResearchAgent(model=ScriptedModel(), settings=make_settings(), store=store, tools=gate)
    with pytest.raises(ValueError):
        ResearchAgent(model=ScriptedModel(), settings=make_settings(), store=store, search_tool_id=TOOL_ID)


def test_the_research_agent_imports_no_transport_no_policy_and_no_provider_only_the_gate_seam():
    imported = set()
    for node in ast.walk(ast.parse((SRC / "agents" / "research.py").read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            imported.add(("." * node.level) + (node.module or ""))
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any(name.startswith(("eidos.mcp", "eidos.policy", "eidos.providers", "eidos.a2a", "eidos.recording", "eidos.state")) for name in imported), imported
    assert ".tool_gate" in imported
