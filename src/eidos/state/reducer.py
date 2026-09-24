"""The state reducer (decisions.md D-155, D-156, D-160, D-166, D-172, D-176, D-177, D-199; invariants 1, 2 and 8).

``reduce(state, record, applied)`` is a **pure function**: it does no I/O, reads no clock, holds no hidden state, and never raises for
expected traffic. It returns the new state **and an outcome** (D-155 item 2), so a duplicate, a late event and a rejection are observable and
countable instead of being indistinguishable from a no-op (D-039's reason). A non-applied outcome leaves the state byte-identical. **Its
signature is unchanged by V0.6** (D-155 is not reopened): it still takes only ``(state, record, applied)`` and nothing more.

**Only this module constructs or updates a ``MissionState``** (invariants 1 and 2; a guard test enforces it). It rebuilds a state through the
contract's own constructor, so every V0.1 consistency check (plan identity, uniqueness, lineage, tenant) still runs on the result.

Checks run in a fixed order, and the first that fails decides the outcome:

1. **duplicate** — the ``event_id`` was already applied (D-011): ignored;
2. **identity** — the record belongs to another mission or tenant;
3. **sequence** — the event applies only if ``sequence == state_version + 1`` (D-097): a later one is *out of order*, an earlier one *stale*.
   Ordering is the EIDOS-assigned sequence and nothing else; **no ordering is ever inferred from a timestamp** (D-160 item 7);
4. **terminal** — ``completed`` and ``failed`` reject every later event, and so does ``paused``, with **one narrow exception** (D-176, below);
5. **the event's own rules** — a plan or step the event names must exist in the state, and the state's own validators must accept the result.

One more check is **not the reducer's**: a repeated ``NODE_STARTED``/``NODE_SETTLED`` for the same step, or a repeated ``A2A_TASK_STARTED``/
``A2A_TASK_COMPLETED`` for the same ``a2a_task_id``. The reducer cannot see either kind, because per-node and per-task state never enters
``MissionState`` (D-010a, D-113) and none is added; the intake and a fold from scratch refuse both, after the reducer has accepted the event
(``eidos.state.step_events`` for D-162 item 1; ``eidos.state.agent_task_events`` for D-172). A record offered to ``reduce`` directly is
therefore judged by the five checks above only.

**The D-176 exception, exactly.** A ``paused`` mission still refuses everything **except** an ``A2A_TASK_COMPLETED`` whose ``a2a_task_id``
correlates to an ``AgentTask`` the state already holds in a **non-concluded** status (``SUBMITTED``, ``WORKING`` or ``UNSPECIFIED``, D-166).
This is deliberately **not** keyed on *why* the mission paused — ``MissionState`` carries no field recording that, and adding one would be a
``MissionState`` contract change this step does not make (D-176 explicitly named only the ``agent_tasks`` fold as new). It does not need one:
completing a task changes only ``agent_tasks``, **never** ``status`` — an admission-guard pause's own terminality is not reopened by this,
regardless of whether that pause happens to coexist with an independently outstanding task (D-165 item shows this is possible: a halt can
take precedence over an awaiting node in the same run). A ``paused`` mission with nothing genuinely outstanding for the named task — the
ordinary admission-halt case — refuses the event exactly as V0.5 shipped it, ``POST_TERMINAL``, unchanged.

**``reduce_resumed``, D-177's own narrow addition, exactly.** ``A2A_TASK_COMPLETED`` being accepted (above) never itself resumes anything —
``status`` stays ``paused`` through it, unconditionally (D-177). A caller resumes **explicitly**, through a *different* boundary entirely:
``eidos.state.log.EventLog.accept_resumed``, the only place with the log's own record history, not this module. ``reduce_resumed`` is what
``accept_resumed`` folds the resumed proposal through once it has already verified — from the log's own history, never a new ``MissionState``
field, which D-177 rules out exactly as D-176 did — that the mission's most recent pause was awaiting-caused and everything it named has now
concluded. ``reduce_resumed`` differs from ``reduce`` in exactly one respect: a ``paused`` mission is not refused *for that reason alone*
(``completed``/``failed`` stay refused, unconditionally, precisely as ``reduce`` refuses them — D-177 narrows only the ``paused`` case). Every
other check — duplicate, identity, sequence, the event's own fit — is the same check, shared by both functions, not forked (see ``_reduce``).

What each event does to the state (D-160 item 4, extended by D-166/D-176). Per-node execution state never enters ``MissionState`` (D-010a,
D-113), so ``NODE_STARTED``/``A2A_TASK_STARTED`` change only ``state_version`` and ``updated_at`` (plus, for the latter, folding
``agent_tasks``); ``NODE_SETTLED`` folds the counters (D-156):

* ``agent_calls_used`` grows by one for each *dispatched* work node — a node carried over from prior outcomes is not a call;
* ``tokens_used`` grows by the prompt and output tokens the provider **reported**; a token count nobody reported adds nothing, so the counter is
  a lower bound and never an estimate;
* ``execution_time_used_ms`` grows by the node's recorded ``duration_ms`` — accumulated accounted node execution time, **not** wall-clock
  duration; a node with no recorded duration adds nothing (D-160 item 6);
* ``retries_used`` and ``tool_calls_used`` are never changed: nothing produces them. ``replans_used`` grows by
  exactly one per accepted ``REPLAN_TRIGGERED`` (D-199, below) — the only counter this module changes outside a
  ``NODE_SETTLED`` fold.

``A2A_TASK_STARTED`` and ``A2A_TASK_COMPLETED`` fold **only** ``agent_tasks`` (D-176's find-and-replace-or-append, ``eidos.state.agent_tasks``)
— **no counter changes here**. The eventual ``agent_calls_used``/``execution_time_used_ms`` contribution of the node an A2A task serves is
folded later, by that node's own ``NODE_SETTLED``, produced through the existing V0.5 machinery once the caller resumes the mission (D-167) —
not invented here, and not duplicated.

Nothing is enforced against a limit: the counters are recorded, not checked (D-156 item 5).

**``REPLAN_TRIGGERED``, D-199's own addition, needs no terminal-state exception at all — unlike D-176/D-177
above.** It is not one of the three terminal payloads (``MISSION_COMPLETED``/``MISSION_FAILED``/
``MISSION_PAUSED``), so check 4 above never engages for it in the first place: a mission recording this event is
still ``created`` (D-052 gives ``MissionStatus`` only four values, no ``EXECUTING`` state, so a mission sits in
``created`` throughout its whole run). Its own rule (check 5) is the same shape every other plan-naming event
already uses: ``failed_plan_id`` must name a plan the mission already holds (mirrors ``PlanRejectedPayload``'s
own check exactly). ``next_plan_id`` is not checked against anything here — there is nothing to check it
against yet; its own ``PLAN_GENERATED`` follows as an ordinary, separately-checked later event, exactly as a
first plan's own does. This is why no ``accept_replanned``/``reduce_replanned`` sibling exists: D-177 needed one
because an A2A-awaiting pause is genuinely terminal-shaped and needs an explicit, checked escape; a replan never
makes the mission terminal in the first place, so there is nothing to escape.
"""

from enum import StrEnum

from pydantic import ValidationError, model_validator

from eidos.contracts import (
    AgentTask,
    AgentTaskStatus,
    EidosModel,
    EventId,
    MissionState,
    MissionStatus,
    Plan,
    PlanId,
    PlanStepKind,
    StepId,
)

from .agent_tasks import fold_agent_task, node_status_for
from .payloads import (
    A2ATaskCompletedPayload,
    A2ATaskStartedPayload,
    MissionCompletedPayload,
    MissionCreatedPayload,
    MissionFailedPayload,
    MissionPausedPayload,
    NodeSettledPayload,
    NodeStartedPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    PlanRejectedPayload,
    ReplanTriggeredPayload,
)
from .records import EventRecord

_TERMINAL = (MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.PAUSED)
# D-166: the AgentTaskStatus values a task can still be in before it has concluded — the only ones an A2A_TASK_COMPLETED may legitimately
# advance from (D-176's PAUSED exception checks this; the payload's own validator separately forbids these three as an *outcome*, D-174).
_NOT_YET_CONCLUDED_AGENT_TASK_STATUSES = (AgentTaskStatus.SUBMITTED, AgentTaskStatus.WORKING, AgentTaskStatus.UNSPECIFIED)


class ReduceOutcome(StrEnum):
    APPLIED = "applied"
    DUPLICATE = "duplicate"  # the event_id was already applied: ignored
    OUT_OF_ORDER = "out_of_order"  # a sequence beyond the next one: rejected
    STALE = "stale"  # a sequence already applied, by a different event: rejected
    POST_TERMINAL = "post_terminal"  # the mission is completed, failed or paused: rejected
    INVALID_FOR_STATE = "invalid_for_state"  # the event does not fit the state it was offered to: rejected
    # Not returned by ``reduce``, which holds no per-node state (D-113): the intake and a fold from scratch return it when a step's start or
    # settlement is recorded a second time (D-162 item 1; ``step_events``).
    REPEATED_STEP_EVENT = "repeated_step_event"
    # Not returned by ``reduce``, which holds no per-task event history (D-113): the intake and a fold from scratch return it when an A2A
    # task's start or completion is recorded a second time for the same ``a2a_task_id`` (D-172; ``agent_task_events``).
    REPEATED_AGENT_TASK_EVENT = "repeated_agent_task_event"


class ReduceResult(EidosModel):
    """The state after the event, and what happened to it. ``state`` is ``None`` only if there was no state and the event did not create one."""

    state: MissionState | None
    outcome: ReduceOutcome
    reason: str | None = None

    @model_validator(mode="after")
    def _check_a_reason_accompanies_exactly_a_non_applied_outcome(self) -> "ReduceResult":
        if self.outcome is ReduceOutcome.APPLIED:
            if self.reason is not None or self.state is None:
                raise ValueError("an applied event yields a state and needs no reason")
        elif not self.reason:
            raise ValueError(f"a {self.outcome.value} outcome states why")
        return self

    @property
    def applied(self) -> bool:
        return self.outcome is ReduceOutcome.APPLIED


class _Reject:
    """An event the state cannot take (internal): carries the reason the outcome will state."""

    def __init__(self, reason: str):
        self.reason = reason


def reduce(state: MissionState | None, record: EventRecord, applied: frozenset[EventId] = frozenset()) -> ReduceResult:
    """Apply one record to ``state`` (``None`` before the mission exists), given the ids of the events already applied to it."""
    return _reduce(state, record, applied, allow_paused=False)


def reduce_resumed(state: MissionState | None, record: EventRecord, applied: frozenset[EventId] = frozenset()) -> ReduceResult:
    """D-177: exactly ``reduce``, except a ``paused`` mission is not refused for that reason alone.

    Only ``eidos.state.log.EventLog.accept_resumed`` calls this — it is the sole place that has already checked the log's own
    history and confirmed the mission's most recent pause was awaiting-caused (never a halt) and everything it named has
    concluded. This function does not, and cannot, re-derive that from ``state`` alone (``MissionState`` carries no field
    for *why* it paused, by design — D-176, D-177); it trusts its caller's precondition the same way ``_apply`` already
    trusts ``reduce``'s. ``completed``/``failed`` remain refused, unconditionally, exactly as ``reduce`` refuses them.
    """
    return _reduce(state, record, applied, allow_paused=True)


def _reduce(state: MissionState | None, record: EventRecord, applied: frozenset[EventId], *, allow_paused: bool) -> ReduceResult:
    event = record.event
    if event.event_id in applied:
        return _no(state, ReduceOutcome.DUPLICATE, f"event {str(event.event_id)!r} was already applied")

    if state is None:
        return _create(record)

    if event.tenant_id != state.tenant_id or event.mission_id != state.mission_id:
        return _no(state, ReduceOutcome.INVALID_FOR_STATE, "the event belongs to another mission or tenant")
    expected = state.state_version + 1
    if event.sequence > expected:
        return _no(state, ReduceOutcome.OUT_OF_ORDER, f"sequence {event.sequence} arrived while {expected} was next")
    if event.sequence < expected:
        return _no(state, ReduceOutcome.STALE, f"sequence {event.sequence} is already applied; {expected} is next")
    resumable = _resumable_completion(state, record.payload) or (allow_paused and state.status is MissionStatus.PAUSED)
    if state.status in _TERMINAL and not resumable:
        return _no(state, ReduceOutcome.POST_TERMINAL, f"the mission is {state.status.value}, so it takes no further events")

    outcome = _apply(state, record)
    if isinstance(outcome, _Reject):
        return _no(state, ReduceOutcome.INVALID_FOR_STATE, outcome.reason)
    return ReduceResult(state=outcome, outcome=ReduceOutcome.APPLIED)


def _no(state: MissionState | None, outcome: ReduceOutcome, reason: str) -> ReduceResult:
    return ReduceResult(state=state, outcome=outcome, reason=reason)


def _resumable_completion(state: MissionState, payload) -> bool:
    """D-176: the one event a terminal mission still takes — an ``A2A_TASK_COMPLETED`` that concludes a task the state itself still shows
    outstanding. False for ``completed``/``failed`` (only ``paused`` can hold an outstanding task at all) and false for an ordinary
    admission-halt pause with nothing outstanding for the named task: this checks what the state already holds, never *why* it paused, since
    ``MissionState`` records no such reason and none is added here (D-176 named only the ``agent_tasks`` fold as new)."""
    if state.status is not MissionStatus.PAUSED or not isinstance(payload, A2ATaskCompletedPayload):
        return False
    task = next((t for t in state.agent_tasks if t.a2a_task_id == payload.a2a_task_id), None)
    return task is not None and task.status in _NOT_YET_CONCLUDED_AGENT_TASK_STATUSES


def most_recent_pause(records) -> MissionPausedPayload | None:
    """D-177: the last ``MISSION_PAUSED`` payload among ``records``, or ``None`` — the log's own answer to *why* a mission most recently
    paused, since ``MissionState`` itself never records that (D-176). Shared by ``eidos.state.log.EventLog.accept_resumed`` (which already
    holds the log) and ``eidos.state.replay._fold`` (which folds one record at a time and tracks this as it goes) — one rule, not two."""
    pause = None
    for record in records:
        if isinstance(record.payload, MissionPausedPayload):
            pause = record.payload
    return pause


def resumable_pause(state: MissionState, pause: MissionPausedPayload | None) -> bool:
    """D-177: whether ``pause`` — the mission's actual, most recently recorded pause — is one ``reduce_resumed`` may now be used for.

    Never true for a halt (D-176's terminality is absolute, regardless of any A2A activity); true for an awaiting pause only once every
    step it named shows a concluded ``AgentTask`` (D-166), read the same way the reducer's own fold reads conclusion (``node_status_for``).
    """
    if pause is None or pause.halt is not None:
        return False
    for info in pause.awaiting:
        task = next((t for t in state.agent_tasks if t.step_id == info.step_id), None)
        if task is None or node_status_for(task.status, artifact=task.latest_artifact) is None:
            return False
    return True


def _create(record: EventRecord) -> ReduceResult:
    payload, event = record.payload, record.event
    if not isinstance(payload, MissionCreatedPayload):
        return _no(None, ReduceOutcome.INVALID_FOR_STATE, "no mission exists yet: the first event must be MISSION_CREATED")
    if event.sequence != 1:
        return _no(None, ReduceOutcome.OUT_OF_ORDER, f"MISSION_CREATED must be sequence 1, not {event.sequence}")
    try:
        created = MissionState(
            tenant_id=event.tenant_id,
            mission_id=event.mission_id,
            execution_id=payload.execution_id,
            created_at=event.occurred_at,
            updated_at=event.recorded_at,
            state_version=event.sequence,
            task_genome=payload.task_genome,
            reliability_contract=payload.reliability_contract,
            status=MissionStatus.CREATED,
            status_reason=None,
            plans=(),
            active_plan_id=None,
            agent_tasks=(),
            retries_used=0,
            replans_used=0,
            agent_calls_used=0,
            tool_calls_used=0,
            execution_time_used_ms=0,
            tokens_used=0,
        )
    except ValidationError as error:
        return _no(None, ReduceOutcome.INVALID_FOR_STATE, _why(error))
    return ReduceResult(state=created, outcome=ReduceOutcome.APPLIED)


def _evolved(state: MissionState, record: EventRecord, **changes) -> MissionState | _Reject:
    """The next state: every field carried over, ``changes`` applied, and the version and time taken from the event."""
    fields = {name: getattr(state, name) for name in MissionState.model_fields}
    fields.update(changes)
    fields["updated_at"] = record.event.recorded_at
    fields["state_version"] = record.event.sequence
    try:
        return MissionState(**fields)
    except ValidationError as error:
        return _Reject(_why(error))


def _why(error: ValidationError) -> str:
    first = error.errors()[0]
    return str(first["msg"]).removeprefix("Value error, ")


def _plan(state: MissionState, plan_id: PlanId) -> Plan | None:
    return next((plan for plan in state.plans if plan.plan_id == plan_id), None)


def _steps(plan: Plan) -> dict[StepId, PlanStepKind]:
    return {step.step_id: step.kind for step in plan.steps}


def _apply(state: MissionState, record: EventRecord) -> MissionState | _Reject:
    payload = record.payload

    if isinstance(payload, MissionCreatedPayload):
        return _Reject("the mission already exists")

    if isinstance(payload, PlanGeneratedPayload):
        return _evolved(state, record, plans=state.plans + (payload.plan,))

    if isinstance(payload, PlanRejectedPayload):
        if _plan(state, payload.plan_id) is None:
            return _Reject(f"plan {str(payload.plan_id)!r} is not in the mission")
        return _evolved(state, record)

    if isinstance(payload, PlanCompiledPayload):
        plan = _plan(state, payload.plan_id)
        if plan is None:
            return _Reject(f"plan {str(payload.plan_id)!r} is not in the mission")
        if plan.version != payload.plan_version:
            return _Reject(f"plan {str(payload.plan_id)!r} is version {plan.version}, not {payload.plan_version}")
        return _evolved(state, record, active_plan_id=payload.plan_id)

    if isinstance(payload, NodeStartedPayload):
        problem = _check_node(state, payload.plan_id, payload.step_id, payload.kind)
        return problem if problem is not None else _evolved(state, record)

    if isinstance(payload, NodeSettledPayload):
        result = payload.result
        problem = _check_node(state, payload.plan_id, result.step_id, result.kind)
        if problem is not None:
            return problem
        calls = 1 if payload.dispatched and result.kind is PlanStepKind.AGENT else 0
        tokens = sum((call.prompt_tokens or 0) + (call.output_tokens or 0) for call in payload.model_calls)
        return _evolved(
            state,
            record,
            agent_calls_used=state.agent_calls_used + calls,
            tokens_used=state.tokens_used + tokens,
            execution_time_used_ms=state.execution_time_used_ms + (payload.duration_ms or 0),
        )

    if isinstance(payload, A2ATaskStartedPayload):
        problem = _check_node(state, payload.plan_id, payload.step_id, PlanStepKind.AGENT)
        if problem is not None:
            return problem
        started = AgentTask(
            agent_id=payload.agent_id,
            status=AgentTaskStatus.SUBMITTED,
            a2a_task_id=payload.a2a_task_id,
            a2a_context_id=payload.a2a_context_id,
            last_event=record.event.event_id,
            plan_id=payload.plan_id,
            step_id=payload.step_id,
            started_at=record.event.occurred_at,
        )
        return _evolved(state, record, agent_tasks=fold_agent_task(state.agent_tasks, started))

    if isinstance(payload, A2ATaskCompletedPayload):
        problem = _check_node(state, payload.plan_id, payload.step_id, PlanStepKind.AGENT)
        if problem is not None:
            return problem
        existing = next((t for t in state.agent_tasks if t.a2a_task_id == payload.a2a_task_id), None)
        if existing is None:
            return _Reject(f"a2a_task {str(payload.a2a_task_id)!r} has no recorded A2A_TASK_STARTED to complete (D-172)")
        if existing.plan_id != payload.plan_id or existing.step_id != payload.step_id:
            return _Reject(f"a2a_task {str(payload.a2a_task_id)!r} started for a different plan step")
        completed = AgentTask(
            agent_id=existing.agent_id,
            status=payload.outcome,
            a2a_task_id=existing.a2a_task_id,
            a2a_context_id=existing.a2a_context_id,
            latest_artifact=payload.artifact,
            last_event=record.event.event_id,
            plan_id=existing.plan_id,
            step_id=existing.step_id,
            started_at=existing.started_at,
        )
        return _evolved(state, record, agent_tasks=fold_agent_task(state.agent_tasks, completed))

    if isinstance(payload, ReplanTriggeredPayload):
        # D-199: an accepted within-mission replan. failed_plan_id must be a real, already-recorded plan; nothing
        # is checked about next_plan_id here (there is nothing to check it against yet — its own PLAN_GENERATED
        # follows as an ordinary later event). status is deliberately never touched: this is not one of the three
        # terminal payloads, so _reduce's own _TERMINAL check never engages for it, and no allow_paused-style
        # exemption is needed the way D-177's reduce_resumed needed one for a genuinely terminal-shaped pause.
        if _plan(state, payload.failed_plan_id) is None:
            return _Reject(f"plan {str(payload.failed_plan_id)!r} is not in the mission")
        return _evolved(state, record, replans_used=state.replans_used + 1)

    if isinstance(payload, MissionPausedPayload):
        step_ids = (payload.halt.step_id,) if payload.halt is not None else tuple(info.step_id for info in payload.awaiting)
        for step_id in step_ids:
            problem = _check_node(state, payload.plan_id, step_id, None)
            if problem is not None:
                return problem
        reason = payload.halt.reason if payload.halt is not None else "; ".join(info.reason for info in payload.awaiting)
        return _evolved(state, record, status=MissionStatus.PAUSED, status_reason=reason)

    if isinstance(payload, MissionCompletedPayload):
        if state.active_plan_id != payload.plan_id:
            return _Reject("the plan that finished is not the active plan")
        reason = "finished and verified" if payload.verified else "finished without a successful VERIFY (verified is false)"
        return _evolved(state, record, status=MissionStatus.COMPLETED, status_reason=reason)

    if isinstance(payload, MissionFailedPayload):
        if payload.plan_id is not None and _plan(state, payload.plan_id) is None:
            return _Reject(f"plan {str(payload.plan_id)!r} is not in the mission")
        return _evolved(state, record, status=MissionStatus.FAILED, status_reason=f"{payload.cause.value}: {payload.reason}")

    return _Reject(f"no rule for {record.event.type.value}")  # unreachable while every emitted payload is handled above


def _check_node(state: MissionState, plan_id: PlanId, step_id: StepId, kind: PlanStepKind | None) -> _Reject | None:
    """A node event must name the active plan and one of its steps, and say the kind that step has."""
    if state.active_plan_id != plan_id:
        return _Reject(f"plan {str(plan_id)!r} is not the active plan")
    plan = _plan(state, plan_id)
    if plan is None:  # unreachable: the state's own validator keeps the active plan among its plans
        return _Reject(f"plan {str(plan_id)!r} is not in the mission")
    steps = _steps(plan)
    if step_id not in steps:
        return _Reject(f"step {str(step_id)!r} is not in plan {str(plan_id)!r}")
    if kind is not None and steps[step_id] is not kind:
        return _Reject(f"step {str(step_id)!r} is a {steps[step_id].value} step, not {kind.value}")
    return None
