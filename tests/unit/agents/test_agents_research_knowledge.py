"""The Research agent's optional knowledge access (decisions.md D-140, D-217, D-228; V1.3 Step 7).

Real agent, real gate, real ledger and artifact store over a scripted model and either the real exact lexical retriever or a scripted port. The agent asks the gate once per run with the
mission goal as the query and works from whatever documents then exist; it never knows which retriever answered, and it cites what it was shown as ``[[evidence:...]]``. An agent built
without knowledge access is what it always was.
"""

import ast
from pathlib import Path

import pytest

from eidos.agents import EvidenceLedger, InMemoryArtifactStore, KnowledgeGate, ResearchAgent, ToolDocument, ToolFailureKind, ToolGate, ToolResult
from eidos.contracts import StepId
from eidos.knowledge import LexicalKnowledgePort, RetrievalFailureKind
from eidos.runtime import WorkStatus

from eidos_agents_factories import ScriptedModel, compiled_with, doc, make_settings, node_of
from eidos_knowledge_gate_fixture import GOAL, KB, SNAPSHOT, ScriptedKnowledgePort, answer_with, attempt_context, descriptor_for, failing_port, make_rag_mission
from eidos_search_fixture import ScriptedToolPort, cite_every_document, failing_port as failing_tool, search_registry, TOOL_ID

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"


def build(*, port=None, supplied=(), with_knowledge=True, with_tools=False, tool_port=None, goal=GOAL, top_k=4):
    state = make_rag_mission(goal=goal)
    store = InMemoryArtifactStore()
    for document in supplied:
        store.put_supplied(state.execution_id, document)
    port = port if port is not None else ScriptedKnowledgePort(LexicalKnowledgePort(SNAPSHOT, kb_id=KB).retrieve)
    ledger = EvidenceLedger()
    gate = KnowledgeGate(descriptor=descriptor_for(top_k=top_k), port=port, ledger=ledger, store=store)
    model = ScriptedModel(cite_every_document)
    kwargs = {}
    if with_knowledge:
        kwargs["knowledge"] = gate
    if with_tools:
        kwargs |= dict(tools=ToolGate(registry=search_registry(), port=tool_port or ScriptedToolPort(), store=store), search_tool_id=TOOL_ID)
    agent = ResearchAgent(model=model, settings=make_settings(), store=store, **kwargs)
    return state, agent, model, port, store, ledger


def run(agent, state, step="gather", plan=1):
    compiled = compiled_with({step: ""})
    return agent.run(attempt_context(state, plan), node_of(compiled, StepId(step)))


# --- a run that uses knowledge ----------------------------------------------------------------------------------------------------


def test_with_no_documents_supplied_the_agent_retrieves_and_researches_the_evidence_and_cites_it_by_evidence_reference():
    state, agent, model, port, store, ledger = build()
    result = run(agent, state)
    assert result.status is WorkStatus.PRODUCED and result.artifact == "artifact:gather"
    assert port.calls == 1 and len(model.requests) == 1 and port.requests[0].text == GOAL  # the goal itself, verbatim
    produced = store.get_step_artifact(state.execution_id, StepId("gather"))
    evidence = [artifact.ref for artifact in store.supplied(state.execution_id)]
    assert len(evidence) == 4 and all(str(ref).startswith("evidence:") for ref in evidence)
    assert set(produced.source_refs) == set(evidence) and {record.evidence_ref for record in ledger.records(state.execution_id)} == {str(ref) for ref in evidence}


def test_the_model_is_shown_exactly_the_evidence_the_gate_stored_each_under_its_own_reference():
    state, agent, model, _, store, _ = build()
    run(agent, state)
    prompt = model.requests[0].prompt
    for artifact in store.supplied(state.execution_id):
        assert f"[[{artifact.ref}]] (text/plain)\n{artifact.content}" in prompt
    assert f"Mission goal: {GOAL}" in prompt


def test_the_query_is_the_goal_with_its_surrounding_whitespace_removed_and_nothing_else():
    state, agent, _, port, _, _ = build(goal="  " + GOAL + "  \n")
    run(agent, state)
    assert [request.text for request in port.requests] == [GOAL]


def test_the_agent_cannot_tell_which_retriever_answered():
    scripted = ScriptedKnowledgePort(lambda request: answer_with(request, tuple(hit.chunk for hit in LexicalKnowledgePort(SNAPSHOT, kb_id=KB).retrieve(request).hits)))
    state_a, agent_a, model_a, _, store_a, _ = build()
    state_b, agent_b, model_b, _, store_b, _ = build(port=scripted)
    run(agent_a, state_a), run(agent_b, state_b)
    assert model_a.requests[0].prompt == model_b.requests[0].prompt
    assert store_a.get_step_artifact(state_a.execution_id, StepId("gather")) == store_b.get_step_artifact(state_b.execution_id, StepId("gather"))


def test_a_second_research_step_of_the_same_execution_is_served_the_stored_evidence_and_the_port_is_not_asked_again():
    state, agent, model, port, store, ledger = build()
    first, second = run(agent, state, "gather"), run(agent, state, "gather_two", plan=2)
    assert first.status is second.status is WorkStatus.PRODUCED
    assert port.calls == 1 and len(model.requests) == 2 and model.requests[0].prompt == model.requests[1].prompt
    assert len(store.supplied(state.execution_id)) == 4 and len(ledger.records(state.execution_id)) == 4


def test_supplied_documents_and_retrieved_evidence_are_read_together_in_a_stable_order():
    state, agent, _, _, store, _ = build(supplied=(doc("doc:1", "Supplied text."),))
    run(agent, state)
    shown = [artifact.ref for artifact in store.supplied(state.execution_id)]
    assert shown == sorted(shown) and str(shown[0]).startswith("doc:") and len(shown) == 5


def test_tools_and_knowledge_may_both_be_given_and_both_are_asked():
    tool_port = ScriptedToolPort(ToolResult(documents=(ToolDocument(document_id="d1", content="Tool text about restart checklists."),)))
    state, agent, model, port, store, _ = build(with_tools=True, tool_port=tool_port)
    result = run(agent, state)
    refs = [str(artifact.ref) for artifact in store.supplied(state.execution_id)]
    assert result.status is WorkStatus.PRODUCED and any(ref.startswith("tool:") for ref in refs) and any(ref.startswith("evidence:") for ref in refs) and port.calls == 1


def test_a_step_that_already_has_its_artifact_is_refused_before_anything_is_retrieved():
    state, agent, model, port, store, _ = build()
    run(agent, state, "gather")
    port_calls_before = port.calls
    refused = run(agent, state, "gather")  # the same step id again: D-147
    assert refused.status is WorkStatus.FAILED and "step_id_reused" in refused.reason
    assert port.calls == port_calls_before and len(model.requests) == 1


# --- when knowledge gives nothing usable -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind, status",
    [
        (RetrievalFailureKind.UNAVAILABLE, WorkStatus.FAILED),
        (RetrievalFailureKind.REQUEST_MISMATCH, WorkStatus.NO_RESULT),
        (RetrievalFailureKind.RESULT_TOO_LARGE, WorkStatus.NO_RESULT),
        (RetrievalFailureKind.MALFORMED_RESULT, WorkStatus.NO_RESULT),
    ],
    ids=lambda x: getattr(x, "value", None),
)
def test_a_retrieval_failure_with_nothing_to_work_from_is_read_like_a_model_failure_and_the_model_is_never_asked(kind, status):
    state, agent, model, _, _, _ = build(port=failing_port(kind))
    result = run(agent, state)
    assert result.status is status and f"the knowledge retrieval failed ({kind.value})" in result.reason and result.reason.startswith("no documents were supplied and ")
    assert model.requests == []


def test_a_port_that_raises_is_an_unavailable_retrieval_and_a_failed_step_not_an_exception():
    state, agent, model, _, _, _ = build(port=ScriptedKnowledgePort(RuntimeError("boom")))
    result = run(agent, state)
    assert result.status is WorkStatus.FAILED and "the knowledge port raised RuntimeError" in result.reason and model.requests == []


def test_a_retrieval_that_found_nothing_is_no_result():
    state, agent, model, _, store, _ = build(port=ScriptedKnowledgePort(lambda request: answer_with(request, ())))
    result = run(agent, state)
    assert result.status is WorkStatus.NO_RESULT and "the knowledge base returned no evidence" in result.reason and model.requests == [] and store.supplied(state.execution_id) == ()


def test_a_wrong_answer_from_the_port_is_a_no_result_that_stored_nothing():
    wrong = ScriptedKnowledgePort(lambda request: answer_with(request, (SNAPSHOT.chunks[0],)).model_copy(update={"query_id": "e" * 64}))
    state, agent, model, _, store, ledger = build(port=wrong)
    result = run(agent, state)
    assert result.status is WorkStatus.NO_RESULT and "malformed_result" in result.reason and model.requests == []
    assert store.supplied(state.execution_id) == () and ledger.records(state.execution_id) == ()


def test_a_goal_that_is_only_whitespace_is_no_query_the_port_is_not_asked_and_it_says_what_it_always_said():
    state, agent, model, port, _, _ = build(goal="   \t ")
    result = run(agent, state)
    assert result.status is WorkStatus.NO_RESULT and result.reason == "no documents were supplied, so there is nothing to research"
    assert port.calls == 0 and model.requests == []


def test_a_failed_retrieval_never_stops_a_run_that_has_documents_to_work_from():
    for port in (failing_port(RetrievalFailureKind.UNAVAILABLE), ScriptedKnowledgePort(RuntimeError("boom")), ScriptedKnowledgePort(lambda request: answer_with(request, ()))):
        state, agent, model, _, _, _ = build(port=port, supplied=(doc("doc:1", "Supplied text about restart."),))
        result = run(agent, state)
        assert result.status is WorkStatus.PRODUCED and len(model.requests) == 1 and "[[doc:1]]" in model.requests[0].prompt


def test_when_a_tool_and_knowledge_both_give_nothing_the_reason_names_both_and_either_incomplete_retrieval_fails_the_step():
    state, agent, model, _, _, _ = build(with_tools=True, tool_port=failing_tool(ToolFailureKind.MALFORMED_RESULT), port=failing_port(RetrievalFailureKind.UNAVAILABLE))
    result = run(agent, state)
    assert result.status is WorkStatus.FAILED and "the tool failed (malformed_result)" in result.reason and "the knowledge retrieval failed (unavailable)" in result.reason
    assert result.reason.count("no documents were supplied and ") == 1 and "; and " in result.reason and model.requests == []
    state, agent, model, _, _, _ = build(with_tools=True, tool_port=ScriptedToolPort(ToolResult(documents=())), port=ScriptedKnowledgePort(lambda request: answer_with(request, ())))
    result = run(agent, state)
    assert result.status is WorkStatus.NO_RESULT and "found no documents" in result.reason and "returned no evidence" in result.reason


# --- an agent without knowledge access is what it always was ----------------------------------------------------------------------


def test_an_agent_built_without_knowledge_never_retrieves_and_says_what_it_always_said():
    state, agent, model, port, _, _ = build(with_knowledge=False)
    result = run(agent, state)
    assert result.status is WorkStatus.NO_RESULT and result.reason == "no documents were supplied, so there is nothing to research"
    assert port.calls == 0 and model.requests == []


def test_the_research_agent_imports_nothing_of_the_knowledge_package_only_the_gates_protocol():
    imported = set()
    for node in ast.walk(ast.parse((SRC / "agents" / "research.py").read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            imported.add(("." * node.level) + (node.module or ""))
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not [name for name in imported if name.startswith("eidos.knowledge")]
    assert ".knowledge_gate" in imported and ".tool_gate" in imported
