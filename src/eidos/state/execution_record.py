"""``ExecutionRecord``: a thin, read-only, derived record of one execution (decisions.md D-159; invariants 1, 12, 13, 16 and 17).

``execution_record(records)`` is a **pure projection of an event log**. It is recomputed from the records every time, is never stored as truth
and never written to ``MissionState``: the log is authoritative (D-157) and this is one more view of it, next to the state the reducer folds.
It first replays the records, so a log the reducer would refuse, or one that repeats a step's start or settlement (D-162 item 1), gives that typed
rejection and never a record built on a log that does not hold. A record therefore has at most one start and one settlement per step.

What it holds is facts, each one a value the log recorded: identity; the plan's structure as recorded, with the agent each step was bound to;
per step, the typed result, whether a port was dispatched, the recorded duration, the model calls and the ``VERIFY`` verdict with its reason;
the mission's terminal status, its typed cause, and — for a paused mission — which of the two causes D-169 distinguishes, the halt or the
awaiting nodes; the folded counters; and the log's own bounds.

What it never holds (D-159 item 2): a quality, a confidence, a score, a rate, a signature, or anything aggregated across missions. The verifier's
reason is carried word for word, so the ``NOT_EVALUATED`` clauses it names (D-146) stay named and are never turned into a number. Every count
here is a count of recorded things, and the two the log cannot fully know say so: the folded token counter is a lower bound, and
``responses_missing_token_counts`` says by how many calls it may fall short.

It describes one execution. It is not strategy memory (V1.0) and not the telemetry platform (V0.9).
"""

from collections.abc import Iterable

from pydantic import Field, model_validator

from eidos.contracts import (
    AgentId,
    ArtifactRef,
    CapabilityId,
    EidosModel,
    ExecutionId,
    MissionId,
    MissionStatus,
    PlanId,
    PlanStepKind,
    StepId,
    TenantId,
)
from eidos.contracts._validators import UtcDateTime
from eidos.runtime import AwaitingInfo, HaltInfo, NodeResult, RunOutcome

from .payloads import (
    MissionCompletedPayload,
    MissionFailedPayload,
    MissionFailureCause,
    MissionPausedPayload,
    ModelCallFacts,
    ModelCallOutcome,
    NodeSettledPayload,
    NodeStartedPayload,
    PlanRejectedPayload,
    PlanRejectionStage,
    RejectionReason,
    RetrievalFacts,
    ToolCallFacts,
    VerificationFacts,
)
from .records import EventRecord
from .replay import ReplayRejection, replay


class StepRecord(EidosModel):
    """One step of the plan, as recorded. Everything after ``depends_on`` is absent until the log says it: nothing is filled in."""

    step_id: StepId
    kind: PlanStepKind
    capability: CapabilityId | None = None  # an ``AGENT`` step's capability; a ``VERIFY`` step has none
    depends_on: tuple[StepId, ...]
    agent_id: AgentId | None = None  # the agent the step was bound to, from its NODE_STARTED; absent if it never started
    started: bool
    result: NodeResult | None = None  # the typed outcome, from NODE_SETTLED; absent until the node has settled
    dispatched: bool | None = None  # whether a port was invoked for it; absent until it has settled
    duration_ms: int | None = Field(default=None, ge=0)  # the recorded duration; absent if none was observed
    model_calls: tuple[ModelCallFacts, ...] = ()
    tool_calls: tuple[ToolCallFacts, ...] = ()  # the tool calls made while the step ran, in call order (D-203, V1.2 Step 3)
    retrievals: tuple[RetrievalFacts, ...] = ()  # the knowledge retrievals made while the step ran, in call order (D-218, V1.3 Step 4)
    citations: tuple[ArtifactRef, ...] = ()  # the references the step's artifact cited, verbatim (D-218, V1.3 Step 4)
    verification: VerificationFacts | None = None  # the verifier's verdict and reason, on a ``VERIFY`` step

    @model_validator(mode="after")
    def _check_nothing_is_recorded_about_a_node_that_has_not_settled(self) -> "StepRecord":
        if self.result is None and (
            self.dispatched is not None or self.duration_ms is not None or self.model_calls or self.tool_calls
            or self.retrievals or self.citations or self.verification is not None
        ):
            raise ValueError("a step that has not settled carries no settlement facts")
        if self.result is not None and self.dispatched is None:
            raise ValueError("a settled step says whether it was dispatched")
        return self


class ExecutionRecord(EidosModel):
    tenant_id: TenantId
    mission_id: MissionId
    execution_id: ExecutionId

    plan_id: PlanId | None = None  # the active plan, else the last plan generated; absent before any plan
    plan_version: int | None = Field(default=None, ge=1)
    steps: tuple[StepRecord, ...] = ()  # in the plan's own step order
    plan_rejected_at: PlanRejectionStage | None = None
    plan_rejection_reasons: tuple[RejectionReason, ...] = ()

    mission_status: MissionStatus
    status_reason: str | None = None
    run_outcome: RunOutcome | None = None  # absent while no run has ended, and when the plan or the run was refused before anything ran
    verified: bool | None = None  # only a completed mission says; absent otherwise
    failure_cause: MissionFailureCause | None = None
    failure_reason: str | None = None
    halt: HaltInfo | None = None  # an admission-guard pause (D-169); absent for an awaiting pause, and vice versa for `awaiting`
    awaiting: tuple[AwaitingInfo, ...] = ()  # an A2A-awaiting pause (D-165, D-169); empty unless the mission paused for that reason

    agent_calls_used: int = Field(ge=0)
    tool_calls_used: int = Field(ge=0)
    retries_used: int = Field(ge=0)
    replans_used: int = Field(ge=0)
    tokens_used: int = Field(ge=0)  # provider-reported tokens only: a lower bound, never an estimate
    execution_time_used_ms: int = Field(ge=0)  # accumulated accounted node time, not wall-clock duration (D-160 item 6)
    model_calls: int = Field(ge=0)
    responses_missing_token_counts: int = Field(ge=0)  # responses whose provider reported no prompt or output tokens: ``tokens_used`` may fall short by these

    event_count: int = Field(ge=1)
    first_occurred_at: UtcDateTime  # of the first and the last record by sequence: bounds of the log, never an ordering
    last_occurred_at: UtcDateTime


_TERMINAL_PAYLOADS = (MissionCompletedPayload, MissionFailedPayload, MissionPausedPayload)


def execution_record(records: Iterable[EventRecord], *, plan_id: PlanId | None = None) -> ExecutionRecord | ReplayRejection:
    """Project a log into its execution record, or return the typed rejection if the log does not replay.

    ``plan_id``, when given, scopes the projection to one specific plan attempt — e.g. an earlier, since
    -abandoned plan version in a mission that has since moved on to a later one (D-199, V1.1 Step 2) — instead of
    the default "the active plan, or the last one" this function has always used. A ``plan_id`` unknown to this
    log (matching no plan in ``state.plans``) degrades exactly as an ordinary mission with no plan at all already
    does: ``plan=None``, every plan-derived field absent — never a rejection, mirroring the existing convention.

    Scoping only ever narrows what is already recorded; it invents nothing. ``steps``/``plan_rejected_at``/
    ``plan_rejection_reasons`` were already filtered by ``plan.plan_id`` before this parameter existed —
    unchanged. ``mission_status``/``run_outcome``/``verified``/``failure_cause``/``halt``/``awaiting`` now come
    from the last *plan-tagged* terminal payload, not simply the log's own last payload: under today's reducer, a
    plan other than the one that actually concluded the mission can never have one of its own (any terminal
    payload makes the whole mission terminal, D-176/D-177), so a scoped, not-yet-concluded attempt honestly
    reports ``MissionStatus.CREATED`` — the same value the *unscoped* case would already show for an in-progress
    mission — rather than borrowing the eventual winner's own outcome. ``agent_calls_used``/``tokens_used``/
    ``execution_time_used_ms`` are recomputed from the scoped ``steps`` alone when ``plan_id`` is given, mirroring
    the reducer's own per-``NodeSettledPayload`` folding formula exactly, applied to a subset — ``state``'s own
    counters are whole-mission cumulative totals, not per-plan. ``tool_calls_used``/``retries_used``/
    ``replans_used`` stay ``state``'s own mission-level totals regardless of scoping: ``tool_calls_used`` now has a
    per-step source (each ``StepRecord.tool_calls``, D-203 V1.2 Step 3) but deliberately keeps the whole-mission
    meaning V1.1 gave it (D-204 item 2), so an exact per-attempt count is read from the scoped steps, while
    nothing produces a per-node source for ``retries_used``/``replans_used`` (D-140, D-170). ``event_count``/``first_occurred_at``/
    ``last_occurred_at`` stay the whole log's own bounds either way, exactly as already documented — a scoped
    view narrows *which plan's facts* are reported, not *which events exist*.
    """
    materialized = tuple(records)
    replayed = replay(materialized)
    if replayed.rejection is not None:
        return replayed.rejection
    state = replayed.state
    payloads = tuple(record.payload for record in materialized)

    if plan_id is not None:
        plan = next((p for p in state.plans if p.plan_id == plan_id), None)
    else:
        plan = next((p for p in state.plans if p.plan_id == state.active_plan_id), state.plans[-1] if state.plans else None)

    started: dict[StepId, NodeStartedPayload] = {}
    settled: dict[StepId, NodeSettledPayload] = {}
    rejected: PlanRejectedPayload | None = None
    if plan is not None:
        # A replayed log holds at most one start and one settlement per step of a plan: replay refuses a repeat (D-162 item 1).
        started = {p.step_id: p for p in payloads if isinstance(p, NodeStartedPayload) and p.plan_id == plan.plan_id}
        settled = {p.result.step_id: p for p in payloads if isinstance(p, NodeSettledPayload) and p.plan_id == plan.plan_id}
        rejected = next(
            (p for p in reversed(payloads) if isinstance(p, PlanRejectedPayload) and p.plan_id == plan.plan_id), None
        )

    steps = tuple(_step_record(step, started.get(step.step_id), settled.get(step.step_id)) for step in (plan.steps if plan else ()))

    calls = [call for step in steps for call in step.model_calls]

    if plan_id is None:
        terminal = payloads[-1]  # unchanged from before this parameter existed
    elif plan is None:
        terminal = None
    else:
        terminal = next(
            (p for p in reversed(payloads) if isinstance(p, _TERMINAL_PAYLOADS) and p.plan_id == plan.plan_id), None
        )
    failed = terminal if isinstance(terminal, MissionFailedPayload) else None

    if plan_id is None:
        agent_calls_used = state.agent_calls_used
        tokens_used = state.tokens_used
        execution_time_used_ms = state.execution_time_used_ms
    else:
        agent_calls_used = sum(1 for step in steps if step.dispatched and step.kind is PlanStepKind.AGENT)
        tokens_used = sum((call.prompt_tokens or 0) + (call.output_tokens or 0) for call in calls)
        execution_time_used_ms = sum(step.duration_ms or 0 for step in steps)

    return ExecutionRecord(
        tenant_id=state.tenant_id,
        mission_id=state.mission_id,
        execution_id=state.execution_id,
        plan_id=plan.plan_id if plan else None,
        plan_version=plan.version if plan else None,
        steps=steps,
        plan_rejected_at=rejected.stage if rejected else None,
        plan_rejection_reasons=rejected.reasons if rejected else (),
        mission_status=state.status if (plan_id is None or terminal is not None) else MissionStatus.CREATED,
        status_reason=state.status_reason,
        run_outcome=_run_outcome(terminal),
        verified=terminal.verified if isinstance(terminal, MissionCompletedPayload) else None,
        failure_cause=failed.cause if failed else None,
        failure_reason=failed.reason if failed else None,
        halt=terminal.halt if isinstance(terminal, MissionPausedPayload) else None,
        awaiting=terminal.awaiting if isinstance(terminal, MissionPausedPayload) else (),
        agent_calls_used=agent_calls_used,
        tool_calls_used=state.tool_calls_used,
        retries_used=state.retries_used,
        replans_used=state.replans_used,
        tokens_used=tokens_used,
        execution_time_used_ms=execution_time_used_ms,
        model_calls=len(calls),
        responses_missing_token_counts=sum(
            1 for call in calls if call.outcome is ModelCallOutcome.RESPONSE and (call.prompt_tokens is None or call.output_tokens is None)
        ),
        event_count=len(materialized),
        first_occurred_at=materialized[0].event.occurred_at,
        last_occurred_at=materialized[-1].event.occurred_at,
    )


def _step_record(step, started: NodeStartedPayload | None, settled: NodeSettledPayload | None) -> StepRecord:
    return StepRecord(
        step_id=step.step_id,
        kind=step.kind,
        capability=getattr(step, "capability", None),
        depends_on=step.depends_on,
        agent_id=started.agent_id if started else None,
        started=started is not None,
        result=settled.result if settled else None,
        dispatched=settled.dispatched if settled else None,
        duration_ms=settled.duration_ms if settled else None,
        model_calls=settled.model_calls if settled else (),
        tool_calls=settled.tool_calls if settled else (),
        retrievals=settled.retrievals if settled else (),
        citations=settled.citations if settled else (),
        verification=settled.verification if settled else None,
    )


_NEVER_RAN = (MissionFailureCause.PLAN_REJECTED, MissionFailureCause.RUN_REJECTED)


def _run_outcome(terminal) -> RunOutcome | None:
    """The run's outcome as the terminal event implies it (the same mapping the recorder applies going the other way, D-160 item 5).

    A ``MissionPausedPayload`` maps to ``HALTED`` or ``AWAITING`` depending on which of its two causes is present (D-169) — never guessed,
    since the payload itself says which one applies.
    """
    if isinstance(terminal, MissionCompletedPayload):
        return RunOutcome.FINISHED
    if isinstance(terminal, MissionPausedPayload):
        return RunOutcome.HALTED if terminal.halt is not None else RunOutcome.AWAITING
    if isinstance(terminal, MissionFailedPayload) and terminal.cause not in _NEVER_RAN:
        return RunOutcome.FAILED
    return None
