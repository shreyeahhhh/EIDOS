"""AgentTask (decisions.md D-033, D-036, D-048, D-081, D-095, D-096, D-098, D-166, D-168)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from eidos.contracts import (
    A2AContextId,
    A2ATaskId,
    AgentId,
    AgentTask,
    AgentTaskStatus,
    ArtifactRef,
    EventId,
    PlanId,
    StepId,
)

from eidos_factories import make_agent_task


def test_valid_construction_with_only_required_fields():
    task = make_agent_task()
    assert task.a2a_task_id is None
    assert task.a2a_context_id is None
    assert task.latest_artifact is None
    assert task.last_event is None
    assert task.plan_id is None
    assert task.step_id is None
    assert task.started_at is None


def test_valid_construction_with_all_optional_fields_populated():
    started = datetime(2026, 9, 22, tzinfo=timezone.utc)
    task = make_agent_task(
        a2a_task_id=A2ATaskId("remote-task-1"),
        a2a_context_id=A2AContextId("remote-context-1"),
        latest_artifact=ArtifactRef("artifact-abc"),
        last_event=EventId(uuid4()),
        plan_id=PlanId(uuid4()),
        step_id=StepId("gather"),
        started_at=started,
    )
    assert task.a2a_task_id == "remote-task-1"
    assert task.latest_artifact == "artifact-abc"
    assert task.step_id == "gather"
    assert task.started_at == started


@pytest.mark.parametrize("status", list(AgentTaskStatus), ids=lambda s: s.value)
def test_every_member_of_the_closed_status_vocabulary_is_a_valid_status(status):
    # decisions.md D-166 (resolving D-036): the real ten-value A2A TaskState vocabulary, never
    # collapsed early. Every member — including TIMED_OUT, which no wire message ever reports — is
    # a legitimate status.
    task = make_agent_task(status=status)
    assert task.status is status


def test_status_is_closed_an_unenumerated_string_is_rejected():
    # decisions.md D-081's reason for keeping status opaque (D-036 undefined) is discharged by
    # D-166: status is now a closed enumeration, and nothing outside it is accepted.
    with pytest.raises(ValidationError):
        make_agent_task(status="pending")
    with pytest.raises(ValidationError):
        make_agent_task(status="anything-at-all")


def test_missing_agent_id_is_rejected():
    with pytest.raises(ValidationError):
        AgentTask(status=AgentTaskStatus.SUBMITTED)


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


# --- D-168: plan_id, step_id, started_at ---------------------------------------------------------------------------------------------


def test_plan_id_step_id_and_started_at_are_each_independently_optional():
    # No cross-field requirement was approved (D-168 adds three independent optional fields);
    # a step_id with no plan_id, and vice versa, are each legal on their own.
    assert make_agent_task(step_id=StepId("gather")).plan_id is None
    assert make_agent_task(plan_id=PlanId(uuid4())).step_id is None
    assert make_agent_task(started_at=datetime(2026, 9, 22, tzinfo=timezone.utc)).plan_id is None


def test_started_at_rejects_a_naive_datetime():
    with pytest.raises(ValidationError, match="D-083"):
        make_agent_task(started_at=datetime(2026, 9, 22))


def test_started_at_rejects_a_non_utc_offset():
    with pytest.raises(ValidationError, match="D-083"):
        make_agent_task(started_at=datetime(2026, 9, 22, tzinfo=timezone(timedelta(hours=5))))
