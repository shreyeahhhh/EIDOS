"""V0.6 Step 6 — ``eidos.recording.a2a.record_a2a_notification`` (decisions.md D-172, D-174, D-177).

Focused tests for the one thing this step adds: the narrow adapter that bridges one externally received A2A
push-notification delivery into a caller-owned ``EventLog``. The webhook parsing/correlation itself
(``eidos.a2a.webhook.notification_to_proposal``) and the log's own intake (``EventLog.accept``/``accept_resumed``)
are each already exhaustively tested on their own (``tests/unit/a2a/test_a2a_webhook.py``,
``tests/unit/state/test_state_d177_resume.py``) — these tests exercise the *composition*, and what it deliberately
does not do (resume, execute, own the log), never re-derive what either side already proves.
"""

from uuid import UUID

from eidos.a2a import WebhookOutcome
from eidos.agents import InMemoryArtifactStore
from eidos.contracts import AgentTaskStatus, MissionId, PlanStepKind, StepId
from eidos.recording.a2a import record_a2a_notification
from eidos.runtime import AwaitingInfo, NodeResult, NodeStatus
from eidos.state import (
    A2ATaskStartedPayload,
    EventLog,
    EventProposal,
    MissionCompletedPayload,
    MissionPausedPayload,
    NodeSettledPayload,
    NodeStartedPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    ReduceOutcome,
    checkpoint_at,
    records_after,
    replay,
    resume,
)

from eidos_a2a_factories import push_notification_body, wire_text_artifact
from eidos_state_factories import (
    ANALYSIS_AGENT,
    CAPABILITY_OF,
    RESEARCH_AGENT,
    a2a_task_id,
    at,
    baseline_state_and_plan,
    created,
    event_id,
    work_result,
)

TASK_ID = "remote-task-1"


def proposal(state, payload, number: int) -> EventProposal:
    return EventProposal(
        event_id=event_id(number), tenant_id=state.tenant_id, mission_id=state.mission_id,
        occurred_at=at(number), recorded_at=at(number), payload=payload,
    )


def paused_awaiting_log():
    """A log holding created/generated/compiled/A2A_TASK_STARTED(gather)/MISSION_PAUSED(awaiting=gather), and the
    store the (fictional) local run recorded its execution against. Returns ``(log, state, plan, next_number, store)``."""
    state, plan = baseline_state_and_plan()
    store = InMemoryArtifactStore()
    log = EventLog()
    n = 1
    for payload in (created(state), PlanGeneratedPayload(plan=plan), PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version)):
        assert log.accept(proposal(state, payload, n)).applied
        n += 1
    assert log.accept(proposal(state, A2ATaskStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("gather"), agent_id=RESEARCH_AGENT, a2a_task_id=a2a_task_id(1),
    ), n)).applied
    n += 1
    assert log.accept(proposal(state, MissionPausedPayload(
        plan_id=plan.plan_id, awaiting=(AwaitingInfo(step_id=StepId("gather"), level=1, reason="awaiting the remote gather task"),),
    ), n)).applied
    n += 1
    return log, state, plan, n, store


def record(log, store, state, *, body, number, tenant_id=None, mission_id=None):
    return record_a2a_notification(
        log, body, store=store, execution_id=state.execution_id,
        tenant_id=tenant_id or state.tenant_id, mission_id=mission_id or state.mission_id,
        event_id=event_id(number), occurred_at=at(number), recorded_at=at(number),
    )


# --- the ordinary path (A2A_TASK_STARTED) is untouched: the adapter is only ever needed for a completion ------------


def test_a2a_task_started_reaches_the_same_caller_owned_log_the_adapter_will_later_write_to():
    log, state, plan, n, store = paused_awaiting_log()
    assert log.state.status.value == "paused"
    assert log.state.agent_tasks[0].a2a_task_id == a2a_task_id(1)
    assert log.state.agent_tasks[0].status is AgentTaskStatus.SUBMITTED


# --- malformed / uncorrelated deliveries: parsed, but nothing is ever offered to the log -----------------------------


def test_a_malformed_delivery_is_reported_and_never_reaches_the_log():
    log, state, plan, n, store = paused_awaiting_log()
    before = len(log.records)
    result = record(log, store, state, body="not json at all {", number=n)
    assert result.webhook.outcome is WebhookOutcome.MALFORMED
    assert result.intake is None
    assert not result.recorded
    assert len(log.records) == before


def test_a_delivery_correlating_to_no_known_task_is_reported_and_never_reaches_the_log():
    log, state, plan, n, store = paused_awaiting_log()
    before = len(log.records)
    body = push_notification_body(task_id="never-started", state="TASK_STATE_COMPLETED")
    result = record(log, store, state, body=body, number=n)
    assert result.webhook.outcome is WebhookOutcome.UNKNOWN_TASK
    assert result.intake is None
    assert not result.recorded
    assert len(log.records) == before


# --- successful recording, including through an AWAITING pause, on the exact same log --------------------------------


def test_recording_a2a_task_completed_applies_through_the_adapter_and_never_auto_resumes():
    log, state, plan, n, store = paused_awaiting_log()
    before = len(log.records)
    body = push_notification_body(
        task_id=TASK_ID, state="TASK_STATE_COMPLETED", artifacts=[wire_text_artifact("a1", "Remote findings: confirmed.")],
    )
    result = record(log, store, state, body=body, number=n)
    assert result.webhook.outcome is WebhookOutcome.PROPOSED
    assert result.recorded and result.intake.applied
    assert len(log.records) == before + 1  # the SAME log, one record longer — not a second log
    assert log.state.agent_tasks[0].status is AgentTaskStatus.COMPLETED
    assert log.state.status.value == "paused"  # D-177/D-170: recording never itself resumes anything


# --- duplicate delivery: both idempotency shapes stay distinct, never collapsed --------------------------------------


def test_a_duplicate_delivery_is_refused_a_repeated_event_id_and_a_repeated_task_id_both_caught_but_kept_apart():
    state, plan = baseline_state_and_plan()
    store = InMemoryArtifactStore()
    log = EventLog()
    n = 1
    for payload in (created(state), PlanGeneratedPayload(plan=plan), PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version)):
        assert log.accept(proposal(state, payload, n)).applied
        n += 1
    assert log.accept(proposal(state, A2ATaskStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("gather"), agent_id=RESEARCH_AGENT, a2a_task_id=a2a_task_id(1),
    ), n)).applied
    n += 1
    body = push_notification_body(task_id=TASK_ID, state="TASK_STATE_COMPLETED")

    first = record(log, store, state, body=body, number=n)
    assert first.recorded

    same_event_id = record_a2a_notification(
        log, body, store=store, execution_id=state.execution_id, tenant_id=state.tenant_id, mission_id=state.mission_id,
        event_id=event_id(n), occurred_at=at(n + 1), recorded_at=at(n + 1),  # the identical event_id: a retried delivery
    )
    assert same_event_id.webhook.outcome is WebhookOutcome.PROPOSED
    assert same_event_id.intake.outcome is ReduceOutcome.DUPLICATE
    n += 1

    fresh_event_id = record(log, store, state, body=body, number=n)  # a fresh event_id, the SAME a2a_task_id again
    assert fresh_event_id.webhook.outcome is WebhookOutcome.PROPOSED
    assert fresh_event_id.intake.outcome is ReduceOutcome.REPEATED_AGENT_TASK_EVENT
    assert not fresh_event_id.recorded


# --- invalid event proposal: a well-formed delivery that does not fit the state it is offered to ----------------------


def test_a_delivery_recorded_against_the_wrong_missions_log_is_refused_as_an_invalid_proposal():
    log, state, plan, n, store = paused_awaiting_log()
    body = push_notification_body(task_id=TASK_ID, state="TASK_STATE_COMPLETED")
    result = record(log, store, state, body=body, number=n, mission_id=MissionId(UUID(int=999)))
    assert result.webhook.outcome is WebhookOutcome.PROPOSED  # correlation reads log.state, not the caller's mismatched id
    assert result.intake.outcome is ReduceOutcome.INVALID_FOR_STATE
    assert not result.recorded


# --- invalid state transition: a delivery for a mission that has already finished --------------------------------------


def test_a_delivery_after_the_mission_has_finished_is_refused_as_an_invalid_state_transition():
    state, plan = baseline_state_and_plan()
    store = InMemoryArtifactStore()
    log = EventLog()
    n = 1
    for payload in (created(state), PlanGeneratedPayload(plan=plan), PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version)):
        assert log.accept(proposal(state, payload, n)).applied
        n += 1
    assert log.accept(proposal(state, A2ATaskStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("gather"), agent_id=RESEARCH_AGENT, a2a_task_id=a2a_task_id(1),
    ), n)).applied
    n += 1
    body = push_notification_body(task_id=TASK_ID, state="TASK_STATE_COMPLETED")
    assert record(log, store, state, body=body, number=n).recorded
    n += 1
    assert log.accept(proposal(state, MissionCompletedPayload(plan_id=plan.plan_id, verified=False), n)).applied
    n += 1
    assert log.state.status.value == "completed"

    late = record(log, store, state, body=body, number=n)
    assert late.webhook.outcome is WebhookOutcome.PROPOSED
    assert late.intake.outcome is ReduceOutcome.POST_TERMINAL
    assert not late.recorded


# --- the adapter never resumes: only the caller's own, separate accept_resumed() call moves the round forward --------


def test_the_adapter_never_resumes_only_the_callers_own_accept_resumed_call_does():
    log, state, plan, n, store = paused_awaiting_log()
    body = push_notification_body(task_id=TASK_ID, state="TASK_STATE_COMPLETED")
    assert record(log, store, state, body=body, number=n).recorded
    n += 1
    assert log.state.status.value == "paused"

    still_refused = log.accept(proposal(state, NodeSettledPayload(plan_id=plan.plan_id, result=work_result("gather"), dispatched=False), n))
    assert still_refused.outcome is ReduceOutcome.POST_TERMINAL  # recorded, not resumed: an ordinary accept() still refuses

    resumed = log.accept_resumed(proposal(state, NodeSettledPayload(plan_id=plan.plan_id, result=work_result("gather"), dispatched=False), n))
    assert resumed.applied, resumed.reason  # only the caller's own explicit, separate call moves the round forward


# --- the adapter holds no state of its own: two callers, two logs, no crosstalk ---------------------------------------


def test_the_adapter_holds_no_state_of_its_own_two_calls_two_different_logs_stay_independent():
    log_a, state_a, _plan_a, n_a, store_a = paused_awaiting_log()
    log_b, _state_b, _plan_b, _n_b, _store_b = paused_awaiting_log()
    body = push_notification_body(task_id=TASK_ID, state="TASK_STATE_COMPLETED")
    assert record(log_a, store_a, state_a, body=body, number=n_a).recorded
    assert log_b.state.agent_tasks[0].status is AgentTaskStatus.SUBMITTED  # log_b, a wholly separate caller's log, is untouched


# --- replay equivalence: the log the adapter wrote to replays exactly as any other ------------------------------------


def test_replay_equivalence_after_a_notification_recorded_through_the_adapter():
    log, state, plan, n, store = paused_awaiting_log()
    body = push_notification_body(task_id=TASK_ID, state="TASK_STATE_COMPLETED")
    assert record(log, store, state, body=body, number=n).recorded

    assert replay(log.records).state == log.state
    for sequence in (1, 2, 3, len(log.records)):
        checkpoint = checkpoint_at(log.records, sequence)
        assert resume(checkpoint, records_after(log.records, checkpoint)).state == log.state


# --- full end-to-end: submit -> AWAITING -> PAUSED -> webhook -> recording adapter -> accept_resumed -> completed -----


def test_full_end_to_end_submit_await_pause_webhook_recording_adapter_resume_finish():
    state, plan = baseline_state_and_plan()
    store = InMemoryArtifactStore()
    log = EventLog()
    n = 1
    for payload in (created(state), PlanGeneratedPayload(plan=plan), PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version)):
        assert log.accept(proposal(state, payload, n)).applied
        n += 1
    assert log.accept(proposal(state, NodeStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("gather"), kind=PlanStepKind.AGENT, capability=CAPABILITY_OF["gather"], agent_id=RESEARCH_AGENT,
    ), n)).applied
    n += 1
    assert log.accept(proposal(state, A2ATaskStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("gather"), agent_id=RESEARCH_AGENT, a2a_task_id=a2a_task_id(1),
    ), n)).applied
    n += 1
    assert log.accept(proposal(state, MissionPausedPayload(
        plan_id=plan.plan_id, awaiting=(AwaitingInfo(step_id=StepId("gather"), level=1, reason="awaiting the remote gather task"),),
    ), n)).applied
    n += 1
    assert log.state.status.value == "paused"

    # --- the remote task concludes; a webhook delivers the news, carried in by the recording adapter -----------------
    body = push_notification_body(
        task_id=TASK_ID, state="TASK_STATE_COMPLETED", artifacts=[wire_text_artifact("a1", "Remote findings: confirmed.")],
    )
    recorded = record(log, store, state, body=body, number=n)
    assert recorded.webhook.outcome is WebhookOutcome.PROPOSED and recorded.recorded
    n += 1
    assert log.state.status.value == "paused"  # never auto-resumed; not auto-executed either

    # --- the caller's own, separate, explicit resume: the remaining DAG, recorded on the SAME log ----------------------
    assert log.accept_resumed(proposal(state, NodeSettledPayload(plan_id=plan.plan_id, result=work_result("gather"), dispatched=False), n)).applied
    n += 1
    assert log.accept_resumed(proposal(state, NodeStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("analyse"), kind=PlanStepKind.AGENT, capability=CAPABILITY_OF["analyse"], agent_id=ANALYSIS_AGENT,
    ), n)).applied
    n += 1
    assert log.accept_resumed(proposal(state, NodeSettledPayload(
        plan_id=plan.plan_id, result=work_result("analyse"), dispatched=True, duration_ms=5, model_calls=(),
    ), n)).applied
    n += 1
    assert log.accept_resumed(proposal(state, NodeStartedPayload(plan_id=plan.plan_id, step_id=StepId("check"), kind=PlanStepKind.VERIFY), n)).applied
    n += 1
    assert log.accept_resumed(proposal(state, NodeSettledPayload(
        plan_id=plan.plan_id,
        result=NodeResult(step_id=StepId("check"), kind=PlanStepKind.VERIFY, status=NodeStatus.SUCCEEDED, reason="verified"),
        dispatched=True, duration_ms=5,
    ), n)).applied
    n += 1
    assert log.accept_resumed(proposal(state, MissionCompletedPayload(plan_id=plan.plan_id, verified=True), n)).applied

    assert log.state.status.value == "completed" and log.state.status_reason == "finished and verified"
    assert replay(log.records).state == log.state
