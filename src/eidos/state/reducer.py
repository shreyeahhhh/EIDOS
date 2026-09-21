"""The state reducer (decisions.md D-155, D-156, D-160; invariants 1, 2 and 8).

``reduce(state, record, applied)`` is a **pure function**: it does no I/O, reads no clock, holds no hidden state, and never raises for
expected traffic. It returns the new state **and an outcome** (D-155 item 2), so a duplicate, a late event and a rejection are observable and
countable instead of being indistinguishable from a no-op (D-039's reason). A non-applied outcome leaves the state byte-identical.

**Only this module constructs or updates a ``MissionState``** (invariants 1 and 2; a guard test enforces it). It rebuilds a state through the
contract's own constructor, so every V0.1 consistency check (plan identity, uniqueness, lineage, tenant) still runs on the result.

Checks run in a fixed order, and the first that fails decides the outcome:

1. **duplicate** — the ``event_id`` was already applied (D-011): ignored;
2. **identity** — the record belongs to another mission or tenant;
3. **sequence** — the event applies only if ``sequence == state_version + 1`` (D-097): a later one is *out of order*, an earlier one *stale*.
   Ordering is the EIDOS-assigned sequence and nothing else; **no ordering is ever inferred from a timestamp** (D-160 item 7);
4. **terminal** — ``completed`` and ``failed`` reject every later event, and so does ``paused``, which is terminal in V0.5 because resume is
   deferred (D-160 item 9);
5. **the event's own rules** — a plan or step the event names must exist in the state, and the state's own validators must accept the result.

One more check is **not the reducer's**: a repeated ``NODE_STARTED`` or ``NODE_SETTLED`` for the same step. The reducer cannot see it, because per-node
state never enters ``MissionState`` (D-010a, D-113) and none is added; the intake and a fold from scratch refuse it, after the reducer has accepted
the event (``eidos.state.step_events``, D-162 item 1). A record offered to ``reduce`` directly is therefore judged by the five checks above only.

What each event does to the state (D-160 item 4). Per-node execution state never enters ``MissionState`` (D-010a, D-113), so ``NODE_STARTED``
changes only ``state_version`` and ``updated_at``; ``NODE_SETTLED`` folds the counters (D-156):

* ``agent_calls_used`` grows by one for each *dispatched* work node — a node carried over from prior outcomes is not a call;
* ``tokens_used`` grows by the prompt and output tokens the provider **reported**; a token count nobody reported adds nothing, so the counter is
  a lower bound and never an estimate;
* ``execution_time_used_ms`` grows by the node's recorded ``duration_ms`` — accumulated accounted node execution time, **not** wall-clock
  duration; a node with no recorded duration adds nothing (D-160 item 6);
* ``retries_used``, ``replans_used`` and ``tool_calls_used`` are never changed: nothing produces them.

Nothing is enforced against a limit: the counters are recorded, not checked (D-156 item 5).
"""

from enum import StrEnum

from pydantic import ValidationError, model_validator

from eidos.contracts import (
    EidosModel,
    EventId,
    MissionState,
    MissionStatus,
    Plan,
    PlanId,
    PlanStepKind,
    StepId,
)

from .payloads import (
    MissionCompletedPayload,
    MissionCreatedPayload,
    MissionFailedPayload,
    MissionPausedPayload,
    NodeSettledPayload,
    NodeStartedPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    PlanRejectedPayload,
)
from .records import EventRecord

_TERMINAL = (MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.PAUSED)


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
    if state.status in _TERMINAL:
        return _no(state, ReduceOutcome.POST_TERMINAL, f"the mission is {state.status.value}, so it takes no further events")

    outcome = _apply(state, record)
    if isinstance(outcome, _Reject):
        return _no(state, ReduceOutcome.INVALID_FOR_STATE, outcome.reason)
    return ReduceResult(state=outcome, outcome=ReduceOutcome.APPLIED)


def _no(state: MissionState | None, outcome: ReduceOutcome, reason: str) -> ReduceResult:
    return ReduceResult(state=state, outcome=outcome, reason=reason)


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

    if isinstance(payload, MissionPausedPayload):
        problem = _check_node(state, payload.plan_id, payload.halt.step_id, None)
        if problem is not None:
            return problem
        return _evolved(state, record, status=MissionStatus.PAUSED, status_reason=payload.halt.reason)

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
