"""``notification_to_proposal`` (decisions.md D-172, D-174; V0.6 Step 5 item 4): parses one push-notification
delivery, correlates it against ``MissionState.agent_tasks``, and produces an ``EventProposal`` or a typed reason
there is none. Nothing here touches ``MissionState``; the caller still carries the proposal to ``EventLog.accept``."""

from uuid import UUID

import pytest

from eidos.a2a.webhook import WebhookOutcome, notification_to_proposal
from eidos.agents import InMemoryArtifactStore
from eidos.contracts import AgentId, AgentTask, AgentTaskStatus, EventId, MissionId, PlanId, StepId, TenantId
from eidos.state import A2ATaskCompletedPayload

from eidos_a2a_factories import push_notification_body, wire_task, wire_text_artifact
from eidos_state_factories import at

TENANT = TenantId(UUID(int=1))
MISSION = MissionId(UUID(int=2))
EXECUTION = UUID(int=3)
PLAN = PlanId(UUID(int=4))
STEP = StepId("gather")
AGENT = AgentId(UUID(int=5))


def a_started_task(a2a_task_id: str = "t1", *, status: AgentTaskStatus = AgentTaskStatus.SUBMITTED) -> AgentTask:
    return AgentTask(
        agent_id=AGENT, status=status, a2a_task_id=a2a_task_id, a2a_context_id="c1",
        plan_id=PLAN, step_id=STEP, started_at=at(1),
    )


def convert(raw: str, *, agent_tasks=(), store=None, event_number: int = 9):
    return notification_to_proposal(
        raw, agent_tasks=agent_tasks, store=store or InMemoryArtifactStore(), execution_id=EXECUTION,
        tenant_id=TENANT, mission_id=MISSION, event_id=EventId(UUID(int=event_number)), occurred_at=at(2), recorded_at=at(2),
    )


# --- parsing and validation -----------------------------------------------------------------------------------------


def test_a_malformed_body_is_reported_not_raised():
    result = convert("not json at all {")
    assert result.outcome is WebhookOutcome.MALFORMED and result.proposal is None
    assert "not a valid push-notification payload" in result.reason


def test_an_invalid_task_payload_shape_is_malformed():
    result = convert('{"task": {"id": "t1"}}')  # missing the required "status"
    assert result.outcome is WebhookOutcome.MALFORMED


def test_a_message_only_payload_is_observed_not_an_error():
    result = convert('{"message": {"messageId": "m1", "role": "ROLE_AGENT", "parts": []}}')
    assert result.outcome is WebhookOutcome.OBSERVED and result.proposal is None


def test_a_standalone_artifact_update_carries_no_status_so_it_is_observed_not_an_error():
    result = convert('{"artifactUpdate": {"taskId": "t1", "contextId": "c1", "artifact": {"artifactId": "a1", "parts": []}}}')
    assert result.outcome is WebhookOutcome.OBSERVED


# --- D-174: only a conclusion is ever proposed --------------------------------------------------------------------


@pytest.mark.parametrize("state", ["TASK_STATE_SUBMITTED", "TASK_STATE_WORKING", "TASK_STATE_UNSPECIFIED"])
def test_a_non_concluding_status_update_is_observed_never_proposed(state):
    body = push_notification_body(task_id="t1", state=state)
    result = convert(body, agent_tasks=(a_started_task("t1"),))
    assert result.outcome is WebhookOutcome.OBSERVED
    assert result.proposal is None


@pytest.mark.parametrize(
    "state, expected",
    [
        ("TASK_STATE_COMPLETED", AgentTaskStatus.COMPLETED),
        ("TASK_STATE_FAILED", AgentTaskStatus.FAILED),
        ("TASK_STATE_CANCELED", AgentTaskStatus.CANCELED),
        ("TASK_STATE_REJECTED", AgentTaskStatus.REJECTED),
        ("TASK_STATE_INPUT_REQUIRED", AgentTaskStatus.INPUT_REQUIRED),
        ("TASK_STATE_AUTH_REQUIRED", AgentTaskStatus.AUTH_REQUIRED),
    ],
)
def test_every_concluding_status_update_is_proposed_as_a2a_task_completed(state, expected):
    body = push_notification_body(task_id="t1", state=state)
    result = convert(body, agent_tasks=(a_started_task("t1"),))
    assert result.outcome is WebhookOutcome.PROPOSED
    payload = result.proposal.payload
    assert isinstance(payload, A2ATaskCompletedPayload)
    assert payload.outcome is expected
    assert payload.plan_id == PLAN and payload.step_id == STEP and payload.a2a_task_id == "t1"
    assert payload.artifact is None  # only COMPLETED ever carries one


# --- correlation via MissionState.agent_tasks — no separate mechanism ------------------------------------------------


def test_a_concluding_update_for_an_unknown_task_id_is_unknown_task():
    body = push_notification_body(task_id="never-started", state="TASK_STATE_COMPLETED")
    result = convert(body, agent_tasks=(a_started_task("t1"),))  # a different task is known
    assert result.outcome is WebhookOutcome.UNKNOWN_TASK
    assert "never-started" in result.reason


def test_a_concluding_update_when_nothing_is_known_at_all_is_unknown_task():
    body = push_notification_body(task_id="t1", state="TASK_STATE_COMPLETED")
    result = convert(body, agent_tasks=())
    assert result.outcome is WebhookOutcome.UNKNOWN_TASK


def test_two_independent_tasks_correlate_to_their_own_plan_step():
    other = AgentTask(agent_id=AGENT, status=AgentTaskStatus.SUBMITTED, a2a_task_id="t2", plan_id=PLAN, step_id=StepId("analyse"), started_at=at(1))
    body = push_notification_body(task_id="t2", state="TASK_STATE_COMPLETED")
    result = convert(body, agent_tasks=(a_started_task("t1"), other))
    assert result.outcome is WebhookOutcome.PROPOSED
    assert result.proposal.payload.step_id == StepId("analyse")


# --- artifact extraction and the store -------------------------------------------------------------------------------


def test_a_completed_task_with_a_usable_artifact_writes_it_to_the_store_and_names_it_in_the_payload():
    store = InMemoryArtifactStore()
    body = push_notification_body(
        task_id="t1", state="TASK_STATE_COMPLETED",
        artifacts=[wire_text_artifact("a1", "Findings: [[doc:1]] support this.")],
    )
    result = convert(body, agent_tasks=(a_started_task("t1"),), store=store)
    assert result.outcome is WebhookOutcome.PROPOSED
    payload = result.proposal.payload
    assert payload.artifact == "artifact:gather"
    stored = store.get_step_artifact(EXECUTION, STEP)
    assert stored.content == "Findings: [[doc:1]] support this."
    assert stored.source_refs == ("doc:1",)


def test_only_a_completed_outcome_ever_attempts_an_artifact_even_if_one_is_offered():
    store = InMemoryArtifactStore()
    body = push_notification_body(
        task_id="t1", state="TASK_STATE_FAILED", artifacts=[wire_text_artifact("a1", "should never be written")],
    )
    result = convert(body, agent_tasks=(a_started_task("t1"),), store=store)
    assert result.outcome is WebhookOutcome.PROPOSED
    assert result.proposal.payload.artifact is None
    assert store.get_step_artifact(EXECUTION, STEP) is None


def test_a_completed_task_with_nothing_usable_carries_no_artifact_not_an_error():
    body = push_notification_body(task_id="t1", state="TASK_STATE_COMPLETED", artifacts=[])
    result = convert(body, agent_tasks=(a_started_task("t1"),))
    assert result.outcome is WebhookOutcome.PROPOSED
    assert result.proposal.payload.artifact is None
    assert "nothing usable" in result.proposal.payload.reason


def test_a_second_delivery_racing_the_same_artifact_write_does_not_crash():
    store = InMemoryArtifactStore()
    body = push_notification_body(task_id="t1", state="TASK_STATE_COMPLETED", artifacts=[wire_text_artifact("a1", "first")])
    first = convert(body, agent_tasks=(a_started_task("t1"),), store=store, event_number=9)
    assert first.outcome is WebhookOutcome.PROPOSED and first.proposal.payload.artifact == "artifact:gather"
    second = convert(body, agent_tasks=(a_started_task("t1"),), store=store, event_number=10)
    assert second.outcome is WebhookOutcome.PROPOSED  # still proposed; the D-172 intake guard is what refuses the repeat
    assert second.proposal.payload.artifact is None  # the store already held the step's artifact; not overwritten


# --- duplicate/late delivery: not this module's job (D-172's own guard handles it) ------------------------------------


def test_a_repeated_delivery_for_an_already_concluded_task_is_still_proposed_not_pre_filtered():
    """This module does not re-implement D-172's guard: it is still handed to the caller, who feeds it to
    EventLog.accept, which refuses it as REPEATED_AGENT_TASK_EVENT — the existing machinery, not a new one."""
    body = push_notification_body(task_id="t1", state="TASK_STATE_COMPLETED")
    result = convert(body, agent_tasks=(a_started_task("t1", status=AgentTaskStatus.COMPLETED),))
    assert result.outcome is WebhookOutcome.PROPOSED
