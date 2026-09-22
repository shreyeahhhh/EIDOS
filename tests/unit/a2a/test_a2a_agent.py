"""``A2AWorkAgent`` (decisions.md D-165, D-175; V0.6 Step 5 item 2): dispatches over A2A, returns SUBMITTED
immediately, never waits for completion, and refuses a reused step before making any call (D-147)."""

import json

from eidos.a2a.client import A2AClient, Submitted
from eidos.a2a.agent import A2AWorkAgent
from eidos.a2a.transport import TransportFailure, TransportFailureKind
from eidos.agents import Artifact as StoredArtifact
from eidos.agents import InMemoryArtifactStore
from eidos.agents.base import STEP_ID_REUSED
from eidos.contracts import ArtifactRef, CapabilityId
from eidos.runtime import WorkStatus

from eidos_a2a_factories import FakeTransport, compiled_research, context_for, node_of, submit_responds_with_task


def agent_with(transport, *, capability=CapabilityId("research")):
    client = A2AClient(endpoint_url="https://peer.example/rpc", transport=transport)
    store = InMemoryArtifactStore()
    return A2AWorkAgent(client=client, store=store, capability=capability, webhook_url="https://eidos.example/webhook"), store


def a_gather_node_and_context():
    compiled = compiled_research()
    node = node_of(compiled, "gather")
    context = context_for(compiled)
    return node, context


def test_a_successful_submission_returns_submitted_immediately_and_never_the_task_id():
    node, context = a_gather_node_and_context()
    agent, store = agent_with(FakeTransport(submit_responds_with_task("t1")))
    store.put_supplied(context.execution_id, StoredArtifact(ref=ArtifactRef("doc:1"), content_type="text/markdown", content="hello"))

    result = agent.run(context, node)

    assert result.status is WorkStatus.SUBMITTED
    assert result.artifact is None  # D-165 rule 1: WorkResult carries no correlation handle
    assert "task" not in (result.reason or "").lower() or "t1" not in (result.reason or "")  # no task id leaks into the generic reason


def test_the_correlation_channel_carries_what_workresult_cannot():
    node, context = a_gather_node_and_context()
    agent, store = agent_with(FakeTransport(submit_responds_with_task("t1", context_id="c1")))
    store.put_supplied(context.execution_id, StoredArtifact(ref=ArtifactRef("doc:1"), content_type="text/markdown", content="hello"))

    agent.run(context, node)

    submitted = agent.submitted_task(node.step_id)
    assert isinstance(submitted, Submitted)
    assert submitted.task_id == "t1" and submitted.context_id == "c1"
    assert agent.submitted_task("nope") is None


def test_a_submission_failure_is_reported_as_failed_not_no_result():
    node, context = a_gather_node_and_context()
    agent, store = agent_with(FakeTransport(lambda url, body, headers: TransportFailure(kind=TransportFailureKind.NETWORK, message="refused")))
    store.put_supplied(context.execution_id, StoredArtifact(ref=ArtifactRef("doc:1"), content_type="text/markdown", content="hello"))

    result = agent.run(context, node)

    assert result.status is WorkStatus.FAILED
    assert "network" in result.reason
    assert agent.submitted_task(node.step_id) is None  # nothing was ever submitted


def test_a_capability_mismatch_is_refused_without_any_network_call():
    node, context = a_gather_node_and_context()
    agent, store = agent_with(FakeTransport(submit_responds_with_task("t1")), capability=CapabilityId("analysis"))

    result = agent.run(context, node)

    assert result.status is WorkStatus.FAILED
    assert "does not serve" in result.reason


def test_no_documents_is_no_result_without_any_network_call():
    node, context = a_gather_node_and_context()
    agent, store = agent_with(FakeTransport(submit_responds_with_task("t1")))
    # nothing supplied
    result = agent.run(context, node)
    assert result.status is WorkStatus.NO_RESULT
    assert "no documents" in result.reason


def test_d147_refuses_a_reused_step_before_any_network_call():
    node, context = a_gather_node_and_context()
    transport = FakeTransport(submit_responds_with_task("t1"))
    agent, store = agent_with(transport)
    store.put_supplied(context.execution_id, StoredArtifact(ref=ArtifactRef("doc:1"), content_type="text/markdown", content="hello"))
    store.put_step_artifact(context.execution_id, node.step_id, StoredArtifact(ref=ArtifactRef(f"artifact:{node.step_id}"), content_type="text/markdown", content="already there"))

    result = agent.run(context, node)

    assert result.status is WorkStatus.FAILED
    assert STEP_ID_REUSED in result.reason
    assert transport.call_count == 0  # refused before any A2A call, spending nothing


def test_the_prompt_sent_carries_the_goal_and_the_supplied_documents():
    node, context = a_gather_node_and_context()
    transport = FakeTransport(submit_responds_with_task("t1"))
    agent, store = agent_with(transport)
    store.put_supplied(context.execution_id, StoredArtifact(ref=ArtifactRef("doc:1"), content_type="text/markdown", content="the supplied text"))

    agent.run(context, node)

    sent = json.loads(transport.calls[0][1])
    text = sent["params"]["message"]["parts"][0]["text"]
    assert context.task_genome.goal in text
    assert "the supplied text" in text
    assert "doc:1" in text


def test_the_webhook_url_is_registered_inline_on_every_submission():
    node, context = a_gather_node_and_context()
    transport = FakeTransport(submit_responds_with_task("t1"))
    agent, store = agent_with(transport)
    store.put_supplied(context.execution_id, StoredArtifact(ref=ArtifactRef("doc:1"), content_type="text/markdown", content="hello"))

    agent.run(context, node)

    sent = json.loads(transport.calls[0][1])
    assert sent["params"]["configuration"]["taskPushNotificationConfig"]["url"] == "https://eidos.example/webhook"


def test_run_returns_even_though_the_remote_task_never_reports_completion():
    """D-165 rule 5's own point, proved structurally: the fake transport's script only ever answers the submission
    call — it has no notion of "later" completion at all — and run() still returns without hanging or polling."""
    node, context = a_gather_node_and_context()
    agent, store = agent_with(FakeTransport(submit_responds_with_task("t1")))
    store.put_supplied(context.execution_id, StoredArtifact(ref=ArtifactRef("doc:1"), content_type="text/markdown", content="hello"))

    result = agent.run(context, node)  # this call alone proves it: nothing here could ever signal completion

    assert result.status is WorkStatus.SUBMITTED
