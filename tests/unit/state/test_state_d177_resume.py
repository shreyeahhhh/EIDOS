"""D-177 — the caller's explicit resume of a `paused` mission (decisions.md D-177; V0.6, following D-176/D-167).

`A2A_TASK_COMPLETED` being accepted (D-176, `EventLog.accept`, unchanged) never itself resumes anything: `status` stays
`paused` through it. `EventLog.accept_resumed` is the *distinct*, explicit boundary a caller uses to continue recording
the mission's remaining DAG on the *same* log — it inspects the log's own history (never a new `MissionState` field) to
find the mission's actual most recent pause, refuses outright if it was an admission-guard halt (D-176's terminality,
unconditionally preserved, regardless of any A2A activity), and otherwise requires every step the pause's `awaiting`
named to now show a concluded `AgentTask` before folding the proposal through `reduce_resumed`.
"""

from eidos.contracts import AgentTaskStatus, MissionEvent, PlanStepKind, StepId
from eidos.runtime import AwaitingInfo, HaltInfo, NodeResult, NodeStatus
from eidos.state import (
    A2ATaskCompletedPayload,
    A2ATaskStartedPayload,
    EventLog,
    EventProposal,
    EventRecord,
    MissionCompletedPayload,
    MissionFailedPayload,
    MissionFailureCause,
    MissionPausedPayload,
    NodeSettledPayload,
    NodeStartedPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    ReduceOutcome,
    checkpoint_at,
    records_after,
    reduce_resumed,
    replay,
    resume,
)

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


def proposal(state, payload, number: int) -> EventProposal:
    return EventProposal(
        event_id=event_id(number), tenant_id=state.tenant_id, mission_id=state.mission_id,
        occurred_at=at(number), recorded_at=at(number), payload=payload,
    )


def paused_awaiting_log(*, steps=("gather",), tasks=None) -> tuple[EventLog, object, object, int]:
    """A log holding created/generated/compiled, an A2A_TASK_STARTED per ``steps`` (task id from ``tasks``, default one
    per step), then a MISSION_PAUSED(awaiting=...) naming all of them. Returns ``(log, state, plan, next_number)``."""
    state, plan = baseline_state_and_plan()
    tasks = tasks or {step: a2a_task_id(i + 1) for i, step in enumerate(steps)}
    log = EventLog()
    n = 1
    for payload in (created(state), PlanGeneratedPayload(plan=plan), PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version)):
        result = log.accept(proposal(state, payload, n))
        assert result.applied, result.reason
        n += 1
    for step in steps:
        result = log.accept(proposal(state, A2ATaskStartedPayload(
            plan_id=plan.plan_id, step_id=StepId(step), agent_id=RESEARCH_AGENT, a2a_task_id=tasks[step],
        ), n))
        assert result.applied, result.reason
        n += 1
    awaiting = tuple(AwaitingInfo(step_id=StepId(step), level=1, reason=f"awaiting {step}") for step in steps)
    result = log.accept(proposal(state, MissionPausedPayload(plan_id=plan.plan_id, awaiting=awaiting), n))
    assert result.applied, result.reason
    n += 1
    return log, state, plan, n


def complete(log, state, plan, step: str, task, *, number: int, outcome=AgentTaskStatus.COMPLETED, artifact=None):
    return log.accept(proposal(
        state,
        A2ATaskCompletedPayload(plan_id=plan.plan_id, step_id=StepId(step), a2a_task_id=task, outcome=outcome, artifact=artifact, reason="x"),
        number,
    ))


def event_record_of(a_proposal: EventProposal, *, sequence: int) -> EventRecord:
    """A proposal, sequenced by hand — for calling ``reduce``/``reduce_resumed`` directly, bypassing ``EventLog``."""
    return EventRecord(
        event=MissionEvent(
            event_id=a_proposal.event_id, tenant_id=a_proposal.tenant_id, mission_id=a_proposal.mission_id,
            sequence=sequence, occurred_at=a_proposal.occurred_at, recorded_at=a_proposal.recorded_at,
            type=a_proposal.payload.event_type,
        ),
        payload=a_proposal.payload,
    )


# --- 1. submit -> await -> pause -> webhook completion -> explicit resume -> remaining execution ---------------------


def test_awaiting_pause_then_completion_then_explicit_resume_then_remaining_execution():
    log, state, plan, n = paused_awaiting_log()
    assert log.state.status.value == "paused"

    completed = complete(log, state, plan, "gather", a2a_task_id(1), number=n)
    assert completed.applied
    assert log.state.status.value == "paused"  # D-177: the completion alone never resumes anything
    n += 1

    resumed = log.accept_resumed(proposal(state, NodeSettledPayload(
        plan_id=plan.plan_id, result=work_result("gather"), dispatched=False,
    ), n))
    assert resumed.applied, resumed.reason
    assert log.state.status.value == "paused"  # still paused: only a terminal event changes it now
    n += 1

    finished = log.accept_resumed(proposal(state, MissionCompletedPayload(plan_id=plan.plan_id, verified=False), n))
    assert finished.applied, finished.reason
    assert log.state.status.value == "completed"


# --- 2 & 3. multiple A2A tasks: resume blocked until *all* conclude, rejected while one is still outstanding ----------


def test_multiple_awaiting_tasks_block_resume_until_every_one_concludes():
    log, state, plan, n = paused_awaiting_log(steps=("gather", "analyse"))
    tasks = {"gather": a2a_task_id(1), "analyse": a2a_task_id(2)}

    blocked = log.accept_resumed(proposal(state, NodeSettledPayload(plan_id=plan.plan_id, result=work_result("gather"), dispatched=False), n))
    assert blocked.outcome is ReduceOutcome.POST_TERMINAL
    assert "not yet resumable" in blocked.reason

    first = complete(log, state, plan, "gather", tasks["gather"], number=n)
    assert first.applied
    n += 1

    still_blocked = log.accept_resumed(proposal(state, NodeSettledPayload(plan_id=plan.plan_id, result=work_result("gather"), dispatched=False), n))
    assert still_blocked.outcome is ReduceOutcome.POST_TERMINAL  # analyse's task is still outstanding

    second = complete(log, state, plan, "analyse", tasks["analyse"], number=n)
    assert second.applied
    n += 1

    now_ok = log.accept_resumed(proposal(state, NodeSettledPayload(plan_id=plan.plan_id, result=work_result("gather"), dispatched=False), n))
    assert now_ok.applied, now_ok.reason


def test_one_task_still_outstanding_rejects_resume():
    log, state, plan, n = paused_awaiting_log(steps=("gather", "analyse"))
    complete(log, state, plan, "gather", a2a_task_id(1), number=n)  # only gather concludes; analyse stays SUBMITTED
    n += 1

    result = log.accept_resumed(proposal(state, NodeSettledPayload(plan_id=plan.plan_id, result=work_result("gather"), dispatched=False), n))
    assert result.outcome is ReduceOutcome.POST_TERMINAL
    assert "not yet resumable" in result.reason
    assert log.state.status.value == "paused"


# --- 4. admission halt + independently outstanding A2A task: completion accepted, accept_resumed rejected -------------


def test_admission_halt_with_an_independently_outstanding_task_accepts_completion_but_rejects_resume():
    state, plan = baseline_state_and_plan()
    log = EventLog()
    n = 1
    for payload in (created(state), PlanGeneratedPayload(plan=plan), PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version)):
        assert log.accept(proposal(state, payload, n)).applied
        n += 1
    assert log.accept(proposal(state, A2ATaskStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("gather"), agent_id=RESEARCH_AGENT, a2a_task_id=a2a_task_id(1),
    ), n)).applied
    n += 1
    # an admission-guard HALT, not an awaiting pause -- the A2A task above is independently still outstanding
    assert log.accept(proposal(state, MissionPausedPayload(
        plan_id=plan.plan_id, halt=HaltInfo(step_id=StepId("analyse"), level=2, reason="held for review"),
    ), n)).applied
    n += 1

    # D-176, unmodified: the genuinely outstanding completion is still accepted through ordinary accept().
    completed = complete(log, state, plan, "gather", a2a_task_id(1), number=n)
    assert completed.applied
    assert log.state.status.value == "paused" and log.state.status_reason == "held for review"
    n += 1

    # D-177's own invariant: accept_resumed must still refuse, because the log's history says this pause was a halt.
    blocked = log.accept_resumed(proposal(state, NodeStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("analyse"), kind=PlanStepKind.AGENT, capability=CAPABILITY_OF["analyse"], agent_id=ANALYSIS_AGENT,
    ), n))
    assert blocked.outcome is ReduceOutcome.POST_TERMINAL
    assert "admission-guard halt" in blocked.reason


# --- 5. a halt pause remains byte-for-byte terminal (no A2A activity at all) -------------------------------------------


def test_a_pure_admission_halt_pause_rejects_accept_resumed_outright():
    state, plan = baseline_state_and_plan()
    log = EventLog()
    n = 1
    for payload in (created(state), PlanGeneratedPayload(plan=plan), PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version)):
        assert log.accept(proposal(state, payload, n)).applied
        n += 1
    assert log.accept(proposal(state, MissionPausedPayload(
        plan_id=plan.plan_id, halt=HaltInfo(step_id=StepId("gather"), level=1, reason="held"),
    ), n)).applied
    n += 1

    ordinary_refused = log.accept(proposal(state, NodeStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("gather"), kind=PlanStepKind.AGENT, capability=CAPABILITY_OF["gather"], agent_id=RESEARCH_AGENT,
    ), n))
    assert ordinary_refused.outcome is ReduceOutcome.POST_TERMINAL  # unchanged: accept() itself was never modified

    resumed_refused = log.accept_resumed(proposal(state, NodeStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("gather"), kind=PlanStepKind.AGENT, capability=CAPABILITY_OF["gather"], agent_id=RESEARCH_AGENT,
    ), n))
    assert resumed_refused.outcome is ReduceOutcome.POST_TERMINAL
    assert "admission-guard halt" in resumed_refused.reason


# --- 6. repeated/duplicate resume proposal behavior ---------------------------------------------------------------------


def test_a_duplicate_event_id_via_accept_resumed_is_a_duplicate_not_a_fresh_apply():
    log, state, plan, n = paused_awaiting_log()
    complete(log, state, plan, "gather", a2a_task_id(1), number=n)
    n += 1
    settled = NodeSettledPayload(plan_id=plan.plan_id, result=work_result("gather"), dispatched=False)
    first = log.accept_resumed(proposal(state, settled, n))
    assert first.applied
    same_id = log.accept_resumed(EventProposal(
        event_id=event_id(n), tenant_id=state.tenant_id, mission_id=state.mission_id, occurred_at=at(n + 100), recorded_at=at(n + 100), payload=settled,
    ))
    assert same_id.outcome is ReduceOutcome.DUPLICATE


def test_a_repeated_node_event_via_accept_resumed_is_still_caught_by_the_d162_guard():
    log, state, plan, n = paused_awaiting_log()
    complete(log, state, plan, "gather", a2a_task_id(1), number=n)
    n += 1
    settled = NodeSettledPayload(plan_id=plan.plan_id, result=work_result("gather"), dispatched=False)
    assert log.accept_resumed(proposal(state, settled, n)).applied
    n += 1
    again = log.accept_resumed(proposal(state, settled, n))  # a new event_id, the same step's settlement again
    assert again.outcome is ReduceOutcome.REPEATED_STEP_EVENT


def test_a_repeated_a2a_completion_for_an_already_concluded_task_is_still_refused_by_unmodified_d176_machinery():
    """Once the first completion concludes the task, D-176's own `_resumable_completion` no longer exempts it (the
    task is no longer in the "not yet concluded" set) — so the reducer's ordinary terminal check refuses a second one
    directly (`POST_TERMINAL`), the same behaviour Step 4 already established and tests, before the D-172 intake-level
    `REPEATED_AGENT_TASK_EVENT` guard is ever reached. D-177 changes none of this: it is proved here, not assumed."""
    log, state, plan, n = paused_awaiting_log()
    first = complete(log, state, plan, "gather", a2a_task_id(1), number=n)
    assert first.applied
    n += 1
    again = log.accept(proposal(  # a new event_id, the same a2a_task_id's completion again -- via ordinary accept(), unchanged
        state, A2ATaskCompletedPayload(plan_id=plan.plan_id, step_id="gather", a2a_task_id=a2a_task_id(1), outcome=AgentTaskStatus.COMPLETED, artifact=None, reason="x"), n,
    ))
    assert again.outcome is ReduceOutcome.POST_TERMINAL


# --- 7. invalid/missing pause history --------------------------------------------------------------------------------


def test_accept_resumed_on_a_mission_that_was_never_paused_is_refused():
    state, plan = baseline_state_and_plan()
    log = EventLog()
    n = 1
    for payload in (created(state), PlanGeneratedPayload(plan=plan)):
        assert log.accept(proposal(state, payload, n)).applied
        n += 1
    result = log.accept_resumed(proposal(state, PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version), n))
    assert result.outcome is ReduceOutcome.POST_TERMINAL
    assert "not paused" in result.reason


def test_accept_resumed_before_the_mission_exists_is_refused():
    log = EventLog()
    state, plan = baseline_state_and_plan()
    result = log.accept_resumed(proposal(state, created(state), 1))
    assert result.outcome is ReduceOutcome.POST_TERMINAL
    assert "not paused" in result.reason


def test_accept_resumed_after_the_mission_has_finished_is_refused():
    log, state, plan, n = paused_awaiting_log()
    complete(log, state, plan, "gather", a2a_task_id(1), number=n)
    n += 1
    assert log.accept_resumed(proposal(state, MissionCompletedPayload(plan_id=plan.plan_id, verified=False), n)).applied
    n += 1
    late = log.accept_resumed(proposal(state, NodeStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("analyse"), kind=PlanStepKind.AGENT, capability=CAPABILITY_OF["analyse"], agent_id=ANALYSIS_AGENT,
    ), n))
    assert late.outcome is ReduceOutcome.POST_TERMINAL
    assert "not paused" in late.reason


# --- 8. existing normal accept() behavior remains unchanged ------------------------------------------------------------


def test_accept_still_refuses_an_ordinary_event_for_an_unresolved_awaiting_pause_exactly_as_before():
    log, state, plan, n = paused_awaiting_log()
    result = log.accept(proposal(state, NodeSettledPayload(plan_id=plan.plan_id, result=work_result("gather"), dispatched=False), n))
    assert result.outcome is ReduceOutcome.POST_TERMINAL
    assert result.reason == "the mission is paused, so it takes no further events"  # accept()'s own wording, untouched


def test_accept_still_takes_the_a2a_task_completed_exception_exactly_as_d176_shipped_it():
    log, state, plan, n = paused_awaiting_log()
    result = complete(log, state, plan, "gather", a2a_task_id(1), number=n)
    assert result.applied and log.state.status.value == "paused"


# --- 9. replay equivalence ------------------------------------------------------------------------------------------


def test_a_log_with_a_d177_resume_replays_to_the_same_state_as_live_intake():
    log, state, plan, n = paused_awaiting_log()
    complete(log, state, plan, "gather", a2a_task_id(1), number=n)
    n += 1
    log.accept_resumed(proposal(state, NodeSettledPayload(plan_id=plan.plan_id, result=work_result("gather"), dispatched=False), n))
    n += 1
    log.accept_resumed(proposal(state, MissionCompletedPayload(plan_id=plan.plan_id, verified=False), n))
    assert log.state.status.value == "completed"

    full = replay(log.records)
    assert full.state == log.state

    # checkpoint + tail equals full replay for a checkpoint taken before the pause or after the mission finished —
    # not for one taken strictly inside the unresolved pause window (a documented limitation, replay.py's own module
    # docstring): resume() is never given the records before its checkpoint, so it cannot know a pause it does not
    # see happened at all, exactly the same class of limitation `seen`/`task_seen` (D-162/D-172) already carry.
    for sequence in (1, 2, 3, len(log.records)):
        checkpoint = checkpoint_at(log.records, sequence)
        assert resume(checkpoint, records_after(log.records, checkpoint)).state == log.state


def test_the_checkpoint_plus_tail_limitation_inside_an_unresolved_pause_is_pinned_not_silent():
    log, state, plan, n = paused_awaiting_log()
    complete(log, state, plan, "gather", a2a_task_id(1), number=n)
    n += 1
    log.accept_resumed(proposal(state, NodeSettledPayload(plan_id=plan.plan_id, result=work_result("gather"), dispatched=False), n))
    n += 1
    log.accept_resumed(proposal(state, MissionCompletedPayload(plan_id=plan.plan_id, verified=False), n))

    checkpoint = checkpoint_at(log.records, 5)  # right after MISSION_PAUSED: state is paused, checkpoint carries no history
    resumed = resume(checkpoint, records_after(log.records, checkpoint))
    assert resumed.rejection is not None  # the tail's own A2A_TASK_COMPLETED is fine (D-176), but the NODE_SETTLED after it is not
    assert resumed.rejection.outcome is ReduceOutcome.POST_TERMINAL


# --- reduce_resumed on its own: completed/failed stay refused unconditionally, exactly as reduce refuses them --------


def test_reduce_resumed_still_refuses_a_completed_mission_unconditionally():
    """Defense in depth beyond accept_resumed's own precondition (which never even calls reduce_resumed once the
    mission is not paused): reduce_resumed itself must not treat allow_paused as a blanket "anything goes"."""
    log, state, plan, n = paused_awaiting_log()
    complete(log, state, plan, "gather", a2a_task_id(1), number=n)
    n += 1
    log.accept_resumed(proposal(state, NodeSettledPayload(plan_id=plan.plan_id, result=work_result("gather"), dispatched=False), n))
    n += 1
    log.accept_resumed(proposal(state, MissionCompletedPayload(plan_id=plan.plan_id, verified=False), n))
    assert log.state.status.value == "completed"
    n += 1

    record = proposal(state, NodeStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("analyse"), kind=PlanStepKind.AGENT, capability=CAPABILITY_OF["analyse"], agent_id=ANALYSIS_AGENT,
    ), n)
    event_record = event_record_of(record, sequence=log.state.state_version + 1)
    result = reduce_resumed(log.state, event_record, log.applied_event_ids)
    assert result.outcome is ReduceOutcome.POST_TERMINAL


def test_reduce_resumed_still_refuses_a_failed_mission_unconditionally():
    state, plan = baseline_state_and_plan()
    log = EventLog()
    n = 1
    for payload in (created(state), PlanGeneratedPayload(plan=plan), PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version)):
        assert log.accept(proposal(state, payload, n)).applied
        n += 1
    assert log.accept(proposal(state, MissionFailedPayload(
        plan_id=plan.plan_id, cause=MissionFailureCause.EXECUTION_FAILED, reason="a node failed",
    ), n)).applied
    n += 1
    assert log.state.status.value == "failed"

    record = proposal(state, NodeStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("gather"), kind=PlanStepKind.AGENT, capability=CAPABILITY_OF["gather"], agent_id=RESEARCH_AGENT,
    ), n)
    event_record = event_record_of(record, sequence=log.state.state_version + 1)
    result = reduce_resumed(log.state, event_record, log.applied_event_ids)
    assert result.outcome is ReduceOutcome.POST_TERMINAL


# --- most_recent_pause picks the latest pause, not the first: a genuinely new halt after a resume stays terminal -----


def test_a_fresh_admission_halt_recorded_after_a_resume_makes_further_events_terminal_again():
    """most_recent_pause must track the *latest* MISSION_PAUSED, not the first: once a genuinely new admission-guard
    halt is recorded during the resumed round, accept_resumed must refuse everything after it, exactly as it would
    for a mission that had only ever been halt-paused (D-176's terminality, unconditional)."""
    log, state, plan, n = paused_awaiting_log()
    complete(log, state, plan, "gather", a2a_task_id(1), number=n)
    n += 1
    assert log.accept_resumed(proposal(state, NodeSettledPayload(
        plan_id=plan.plan_id, result=work_result("gather"), dispatched=False,
    ), n)).applied
    n += 1

    # a genuinely new admission-guard halt, recorded through the resumed boundary (nothing is outstanding to block it)
    fresh_halt = log.accept_resumed(proposal(state, MissionPausedPayload(
        plan_id=plan.plan_id, halt=HaltInfo(step_id=StepId("analyse"), level=2, reason="held on the resumed round"),
    ), n))
    assert fresh_halt.applied, fresh_halt.reason
    assert log.state.status_reason == "held on the resumed round"
    n += 1

    blocked = log.accept_resumed(proposal(state, NodeStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("analyse"), kind=PlanStepKind.AGENT, capability=CAPABILITY_OF["analyse"], agent_id=ANALYSIS_AGENT,
    ), n))
    assert blocked.outcome is ReduceOutcome.POST_TERMINAL
    assert "admission-guard halt" in blocked.reason

    # replay agrees: most_recent_pause is computed fresh from the log's own history, the same either way (D-157)
    assert replay(log.records).state == log.state


# --- 10. full end-to-end: submit -> AWAITING -> PAUSED -> webhook completion -> accept_resumed -> finish --------------


def test_full_end_to_end_submit_await_pause_webhook_resume_finish():
    state, plan = baseline_state_and_plan()
    log = EventLog()
    n = 1
    for payload in (created(state), PlanGeneratedPayload(plan=plan), PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version)):
        assert log.accept(proposal(state, payload, n)).applied
        n += 1
    assert log.accept(proposal(state, NodeStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("gather"), kind=PlanStepKind.AGENT, capability=CAPABILITY_OF["gather"], agent_id=RESEARCH_AGENT,
    ), n)).applied  # the submission's own NODE_STARTED, alongside A2A_TASK_STARTED (D-174)
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

    # webhook completion
    assert complete(log, state, plan, "gather", a2a_task_id(1), number=n).applied
    n += 1
    assert log.state.status.value == "paused"

    # explicit resume: the remaining DAG runs (gather settled, analyse and check dispatched and settled)
    assert log.accept_resumed(proposal(state, NodeSettledPayload(
        plan_id=plan.plan_id, result=work_result("gather"), dispatched=False,
    ), n)).applied
    n += 1
    assert log.accept_resumed(proposal(state, NodeStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("analyse"), kind=PlanStepKind.AGENT, capability=CAPABILITY_OF["analyse"], agent_id=ANALYSIS_AGENT,
    ), n)).applied
    n += 1
    assert log.accept_resumed(proposal(state, NodeSettledPayload(
        plan_id=plan.plan_id, result=work_result("analyse"), dispatched=True, duration_ms=5, model_calls=(),
    ), n)).applied
    n += 1
    assert log.accept_resumed(proposal(state, NodeStartedPayload(
        plan_id=plan.plan_id, step_id=StepId("check"), kind=PlanStepKind.VERIFY,
    ), n)).applied
    n += 1
    assert log.accept_resumed(proposal(state, NodeSettledPayload(
        plan_id=plan.plan_id, result=NodeResult(step_id=StepId("check"), kind=PlanStepKind.VERIFY, status=NodeStatus.SUCCEEDED, reason="verified"),
        dispatched=True, duration_ms=5,
    ), n)).applied
    n += 1
    assert log.accept_resumed(proposal(state, MissionCompletedPayload(plan_id=plan.plan_id, verified=True), n)).applied

    assert log.state.status.value == "completed" and log.state.status_reason == "finished and verified"
    assert replay(log.records).state == log.state
