"""The Research and Analysis agents against a scripted model (decisions.md D-131, D-137, D-140, D-144, D-145)."""

from uuid import UUID

import pytest

from eidos.agents import (
    AnalysisAgent,
    InMemoryArtifactStore,
    ModelFailure,
    ModelFailureKind,
    ModelResponse,
    ResearchAgent,
    artifact_ref_for,
    cited_refs,
)
from eidos.contracts import ExecutionId, StepId
from eidos.runtime import WorkStatus

from eidos_agents_factories import ScriptedModel, compiled_with, doc, make_settings, node_of
from eidos_runtime_factories import context_for


def answer(text):
    return lambda request: ModelResponse(text=text)


def failing(kind):
    return lambda request: ModelFailure(kind=kind, message=f"scripted {kind.value}")


def research_setup(model=None, docs=("doc:b", "doc:a"), capability="research"):
    compiled = compiled_with({"gather": ""}, {"gather": capability})
    context = context_for(compiled)
    store = InMemoryArtifactStore()
    for ref in docs:
        store.put_supplied(context.execution_id, doc(ref, f"content of {ref}"))
    model = model or ScriptedModel(answer("Findings [[doc:a]] and [[doc:b]]."))
    agent = ResearchAgent(model=model, settings=make_settings(), store=store)
    return agent, model, store, context, node_of(compiled, StepId("gather"))


# --- citations ------------------------------------------------------------------------------------------------------------


def test_cited_refs_are_distinct_and_in_order_of_first_appearance():
    assert cited_refs("a [[x]] b [[y]] c [[x]] [[ z ]]") == ("x", "y", "z")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", ()), ("no citations", ()), ("[x]", ()), ("[[]]", ()), ("[[ ]]", ()),
        ("[[a" + chr(10) + "b]]", ()),  # a marker never spans lines
        ("[[[a]]", ("a",)),  # the inner, well-formed marker is the citation
    ],
)
def test_only_a_well_formed_marker_is_a_citation(text, expected):
    assert cited_refs(text) == expected


# --- the Research Agent --------------------------------------------------------------------------------------------------


def test_the_research_agent_serves_only_research():
    assert ResearchAgent.CAPABILITIES == ("research",)
    agent, model, _, context, _ = research_setup()
    other = compiled_with({"x": ""}, {"x": "cost"})
    result = agent.run(context_for(other), node_of(other, StepId("x")))
    assert result.status is WorkStatus.FAILED and "does not serve" in result.reason
    assert model.calls == 0


def test_a_research_step_reads_the_supplied_documents_asks_the_model_once_and_records_one_artifact():
    agent, model, store, context, node = research_setup()

    result = agent.run(context, node)

    assert result.status is WorkStatus.PRODUCED and result.artifact == artifact_ref_for(node.step_id) == "artifact:gather"
    assert model.calls == 1
    stored = store.get_step_artifact(context.execution_id, node.step_id)
    assert stored.ref == result.artifact
    assert stored.content == "Findings [[doc:a]] and [[doc:b]]."
    assert stored.content_type == "text/markdown"
    assert stored.source_refs == ("doc:a", "doc:b")  # what the model cited, in order of appearance
    assert store.get(context.execution_id, result.artifact) == stored


def test_the_prompt_carries_the_goal_and_every_supplied_document_under_its_exact_reference():
    agent, model, _, context, node = research_setup()
    agent.run(context, node)

    request = model.requests[0]
    assert context.task_genome.goal in request.prompt
    a, b = request.prompt.index("[[doc:a]]"), request.prompt.index("[[doc:b]]")
    assert a < b  # ordered by reference, whatever order they were supplied in
    assert "content of doc:a" in request.prompt and "content of doc:b" in request.prompt
    assert "cite" in request.system.lower()
    assert request.settings == make_settings()  # the caller's explicit settings, unchanged


def test_the_same_inputs_give_the_same_prompt():
    prompts = []
    for docs in (("doc:b", "doc:a"), ("doc:a", "doc:b")):
        agent, model, _, context, node = research_setup(docs=docs)
        agent.run(context, node)
        prompts.append(model.requests[0].prompt)
    assert prompts[0] == prompts[1]


def test_with_nothing_supplied_there_is_nothing_to_research_and_the_model_is_never_asked():
    agent, model, store, context, node = research_setup(docs=())
    result = agent.run(context, node)
    assert result.status is WorkStatus.NO_RESULT and "nothing to research" in result.reason
    assert model.calls == 0
    assert store.get_step_artifact(context.execution_id, node.step_id) is None


def test_documents_supplied_to_another_execution_are_not_read():
    agent, model, store, context, node = research_setup(docs=())
    store.put_supplied(ExecutionId(UUID(int=999)), doc("doc:elsewhere"))
    assert agent.run(context, node).status is WorkStatus.NO_RESULT
    assert model.calls == 0


def test_a_citation_of_something_that_does_not_exist_is_recorded_for_verification_to_catch():
    agent, _, store, context, node = research_setup(model=ScriptedModel(answer("Claim [[ghost]].")))
    agent.run(context, node)
    assert store.get_step_artifact(context.execution_id, node.step_id).source_refs == ("ghost",)


def test_an_output_never_cites_itself():
    agent, _, store, context, node = research_setup(model=ScriptedModel(answer("See [[artifact:gather]] and [[doc:a]].")))
    assert agent.run(context, node).status is WorkStatus.PRODUCED
    assert store.get_step_artifact(context.execution_id, node.step_id).source_refs == ("doc:a",)


@pytest.mark.parametrize(
    "kind, status",
    [
        (ModelFailureKind.TIMEOUT, WorkStatus.FAILED),
        (ModelFailureKind.UNAVAILABLE, WorkStatus.FAILED),
        (ModelFailureKind.MALFORMED_RESPONSE, WorkStatus.NO_RESULT),
        (ModelFailureKind.EMPTY_RESPONSE, WorkStatus.NO_RESULT),
    ],
)
def test_a_model_failure_becomes_the_work_status_it_means_and_writes_nothing(kind, status):
    agent, _, store, context, node = research_setup(model=ScriptedModel(failing(kind)))
    result = agent.run(context, node)
    assert result.status is status
    assert kind.value in result.reason and f"scripted {kind.value}" in result.reason
    assert store.get_step_artifact(context.execution_id, node.step_id) is None


def test_a_model_that_raises_is_not_swallowed_by_the_agent_the_executor_contains_it():
    def boom(request):
        raise RuntimeError("adapter bug")

    agent, _, store, context, node = research_setup(model=ScriptedModel(boom))
    with pytest.raises(RuntimeError, match="adapter bug"):
        agent.run(context, node)
    assert store.get_step_artifact(context.execution_id, node.step_id) is None


def test_running_a_step_twice_fails_the_second_time_rather_than_overwriting():
    agent, _, store, context, node = research_setup()
    first = agent.run(context, node)
    second = agent.run(context, node)
    assert first.status is WorkStatus.PRODUCED
    assert second.status is WorkStatus.FAILED and "could not be recorded" in second.reason
    assert store.get_step_artifact(context.execution_id, node.step_id).ref == first.artifact


# --- the Analysis Agent ---------------------------------------------------------------------------------------------------


def analysis_setup(capability="cost", model=None, produce_predecessor=True, supplied=("doc:s",)):
    compiled = compiled_with({"gather": "", "analyse": "gather"}, {"gather": "research", "analyse": capability})
    context = context_for(compiled)
    store = InMemoryArtifactStore()
    for ref in supplied:
        store.put_supplied(context.execution_id, doc(ref, f"content of {ref}"))
    if produce_predecessor:
        store.put_step_artifact(context.execution_id, StepId("gather"), doc("artifact:gather", "research output", sources=supplied))
    model = model or ScriptedModel(answer("Analysis [[artifact:gather]] [[doc:s]]."))
    agent = AnalysisAgent(model=model, settings=make_settings(), store=store)
    return agent, model, store, context, node_of(compiled, StepId("analyse"))


def test_the_analysis_agent_serves_architecture_security_and_cost_only():
    assert AnalysisAgent.CAPABILITIES == ("architecture", "security", "cost")
    for other in ("research", "verification"):
        agent, model, _, context, node = analysis_setup(capability=other)
        result = agent.run(context, node)
        assert result.status is WorkStatus.FAILED and "does not serve" in result.reason
        assert model.calls == 0


@pytest.mark.parametrize("capability, word", [("architecture", "architecture"), ("security", "security"), ("cost", "cost")])
def test_each_capability_asks_for_its_own_kind_of_analysis(capability, word):
    agent, model, _, context, node = analysis_setup(capability=capability)
    assert agent.run(context, node).status is WorkStatus.PRODUCED
    assert word in model.requests[0].prompt.split("Task:")[1].lower()


def test_the_analysis_reads_its_predecessors_artifact_and_the_supplied_documents_and_records_one_artifact():
    agent, model, store, context, node = analysis_setup()

    result = agent.run(context, node)

    assert result.status is WorkStatus.PRODUCED and result.artifact == "artifact:analyse"
    prompt = model.requests[0].prompt
    assert prompt.index("[[artifact:gather]]") < prompt.index("[[doc:s]]")  # predecessors first, then supplied
    assert "research output" in prompt and "content of doc:s" in prompt
    stored = store.get_step_artifact(context.execution_id, node.step_id)
    assert stored.source_refs == ("artifact:gather", "doc:s")


def test_an_analysis_with_no_predecessor_can_work_from_supplied_documents_alone():
    compiled = compiled_with({"analyse": ""}, {"analyse": "security"})
    context = context_for(compiled)
    store = InMemoryArtifactStore()
    store.put_supplied(context.execution_id, doc("doc:s"))
    agent = AnalysisAgent(model=ScriptedModel(answer("Risks [[doc:s]].")), settings=make_settings(), store=store)
    assert agent.run(context, node_of(compiled, StepId("analyse"))).status is WorkStatus.PRODUCED


def test_a_predecessor_with_no_artifact_is_a_failure_and_the_model_is_not_asked():
    agent, model, _, context, node = analysis_setup(produce_predecessor=False)
    result = agent.run(context, node)
    assert result.status is WorkStatus.FAILED and "'gather' has no artifact" in result.reason
    assert model.calls == 0


def test_with_no_material_at_all_there_is_nothing_to_analyse():
    compiled = compiled_with({"analyse": ""}, {"analyse": "cost"})
    agent = AnalysisAgent(model=ScriptedModel(), settings=make_settings(), store=InMemoryArtifactStore())
    result = agent.run(context_for(compiled), node_of(compiled, StepId("analyse")))
    assert result.status is WorkStatus.NO_RESULT and "no material" in result.reason


@pytest.mark.parametrize(
    "kind, status",
    [
        (ModelFailureKind.TIMEOUT, WorkStatus.FAILED),
        (ModelFailureKind.UNAVAILABLE, WorkStatus.FAILED),
        (ModelFailureKind.MALFORMED_RESPONSE, WorkStatus.NO_RESULT),
        (ModelFailureKind.EMPTY_RESPONSE, WorkStatus.NO_RESULT),
    ],
)
def test_an_analysis_model_failure_becomes_the_work_status_it_means_and_writes_nothing(kind, status):
    agent, _, store, context, node = analysis_setup(model=ScriptedModel(failing(kind)))
    assert agent.run(context, node).status is status
    assert store.get_step_artifact(context.execution_id, node.step_id) is None


def test_the_agents_hold_no_state_of_their_own_so_they_are_safe_on_worker_threads():
    import threading

    agent, model, store, context, node = research_setup()
    compiled = compiled_with({f"s{n}": "" for n in range(40)})
    results = []
    lock = threading.Lock()

    def work(step):
        found = agent.run(context, node_of(compiled, StepId(step)))
        with lock:
            results.append(found)

    threads = [threading.Thread(target=work, args=(f"s{n}",)) for n in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(r.artifact for r in results) == sorted(f"artifact:s{n}" for n in range(40))
    assert model.calls == 40
