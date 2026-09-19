"""AgentTask (decisions.md D-033, D-036, D-048, D-081, D-095, D-096, D-098)."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from eidos.contracts import A2AContextId, A2ATaskId, AgentId, AgentTask, ArtifactRef, EventId

from eidos_factories import make_agent_task


def test_valid_construction_with_only_required_fields():
    task = make_agent_task()
    assert task.a2a_task_id is None
    assert task.a2a_context_id is None
    assert task.latest_artifact is None
    assert task.last_event is None


def test_valid_construction_with_all_optional_fields_populated():
    task = make_agent_task(
        a2a_task_id=A2ATaskId("remote-task-1"),
        a2a_context_id=A2AContextId("remote-context-1"),
        latest_artifact=ArtifactRef("artifact-abc"),
        last_event=EventId(uuid4()),
    )
    assert task.a2a_task_id == "remote-task-1"
    assert task.latest_artifact == "artifact-abc"


def test_status_is_an_opaque_string_no_enumeration():
    # decisions.md D-081: any string is structurally valid; nothing here
    # constrains it to a known set, since D-036 has not defined one.
    task = make_agent_task(status="anything-at-all")
    assert task.status == "anything-at-all"


def test_missing_agent_id_is_rejected():
    with pytest.raises(ValidationError):
        AgentTask(status="pending")


def test_missing_status_is_rejected():
    with pytest.raises(ValidationError):
        AgentTask(agent_id=AgentId(uuid4()))


def test_does_not_carry_tenant_id():
    # decisions.md D-033: AgentTask is a nested model and does not carry
    # tenant_id.
    with pytest.raises(ValidationError):
        make_agent_task(tenant_id=uuid4())


def test_a2a_task_id_and_context_id_accept_plain_opaque_strings():
    # decisions.md D-095: externally assigned, not required to be
    # EIDOS-generated UUIDs.
    task = make_agent_task(a2a_task_id="not-a-uuid-at-all")
    assert task.a2a_task_id == "not-a-uuid-at-all"


def test_last_event_is_a_reference_not_an_embedded_event():
    event_id = EventId(uuid4())
    task = make_agent_task(last_event=event_id)
    assert task.last_event == event_id
    with pytest.raises(ValidationError):
        make_agent_task(last_event={"event_id": str(event_id)})


def test_no_artifact_model_exists_latest_artifact_is_a_bare_reference():
    task = make_agent_task(latest_artifact=ArtifactRef("ref-1"))
    assert task.latest_artifact == "ref-1"
    with pytest.raises(ValidationError):
        make_agent_task(latest_artifact={"content": "not a model"})


def test_model_is_immutable():
    task = make_agent_task()
    with pytest.raises(ValidationError):
        task.status = "changed"


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        make_agent_task(unexpected_field=123)
