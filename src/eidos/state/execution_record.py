"""``ExecutionRecord``: a thin, read-only, derived record of one execution (decisions.md D-159; invariants 1, 12, 13, 16 and 17).

``execution_record(records)`` is a **pure projection of an event log**. It is recomputed from the records every time, is never stored as truth
and never written to ``MissionState``: the log is authoritative (D-157) and this is one more view of it, next to the state the reducer folds.
It first replays the records, so a log the reducer would refuse gives that typed rejection and never a record built on a log that does not hold.

What it holds is facts, each one a value the log recorded: identity; the plan's structure as recorded, with the agent each step was bound to;
per step, the typed result, whether a port was dispatched, the recorded duration, the model calls and the ``VERIFY`` verdict with its reason;
the mission's terminal status, its typed cause and the halt; the folded counters; and the log's own bounds.

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
from eidos.runtime import HaltInfo, NodeResult, RunOutcome

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
    verification: VerificationFacts | None = None  # the verifier's verdict and reason, on a ``VERIFY`` step

    @model_validator(mode="after")
    def _check_nothing_is_recorded_about_a_node_that_has_not_settled(self) -> "StepRecord":
        if self.result is None and (
            self.dispatched is not None or self.duration_ms is not None or self.model_calls or self.verification is not None
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
    halt: HaltInfo | None = None

    agent_calls_used: int = Field(ge=0)
    tool_calls_used: int = Field(ge=0)
    retries_used: int = Field(ge=0)
    replans_used: int = Field(ge=0)
    tokens_used: int = Field(ge=0)  # provider-reported tokens only: a lower bound, never an estimate
    execution_time_used_ms: int = Field(ge=0)  # accumulated accounted node time, not wall-clock duration (D-160 item 6)
    model_calls: int = Field(ge=0)
    responses_missing_token_counts: int = Field(ge=0)  # responses whose provider reported no prompt or output tokens: ``tokens_used`` may fall short by these

    repeated_step_events: int = Field(ge=0)  # NODE_STARTED / NODE_SETTLED records for a step beyond its first: always 0 in a log the recorder wrote
    event_count: int = Field(ge=1)
    first_occurred_at: UtcDateTime  # of the first and the last record by sequence: bounds of the log, never an ordering
    last_occurred_at: UtcDateTime


def execution_record(records: Iterable[EventRecord]) -> ExecutionRecord | ReplayRejection:
    """Project a log into its execution record, or return the typed rejection if the log does not replay."""
    materialized = tuple(records)
    replayed = replay(materialized)
    if replayed.rejection is not None:
        return replayed.rejection
    state = replayed.state
    payloads = tuple(record.payload for record in materialized)

    plan = next((p for p in state.plans if p.plan_id == state.active_plan_id), state.plans[-1] if state.plans else None)
    started: dict[StepId, NodeStartedPayload] = {}
    settled: dict[StepId, NodeSettledPayload] = {}
    repeated = 0
    rejected: PlanRejectedPayload | None = None
    if plan is not None:
        # The first record of a step is the one shown. The reducer keeps no per-node state (D-113), so it cannot refuse a repeat; a repeat is
        # therefore counted and reported, never dropped without a trace (decisions.md D-162 item 1).
        for p in payloads:
            if isinstance(p, NodeStartedPayload) and p.plan_id == plan.plan_id:
                repeated += p.step_id in started
                started.setdefault(p.step_id, p)
            elif isinstance(p, NodeSettledPayload) and p.plan_id == plan.plan_id:
                repeated += p.result.step_id in settled
                settled.setdefault(p.result.step_id, p)
        rejected = next(
            (p for p in reversed(payloads) if isinstance(p, PlanRejectedPayload) and p.plan_id == plan.plan_id), None
        )

    steps = tuple(_step_record(step, started.get(step.step_id), settled.get(step.step_id)) for step in (plan.steps if plan else ()))

    calls = [call for step in steps for call in step.model_calls]
    terminal = payloads[-1]
    failed = terminal if isinstance(terminal, MissionFailedPayload) else None

    return ExecutionRecord(
        tenant_id=state.tenant_id,
        mission_id=state.mission_id,
        execution_id=state.execution_id,
        plan_id=plan.plan_id if plan else None,
        plan_version=plan.version if plan else None,
        steps=steps,
        plan_rejected_at=rejected.stage if rejected else None,
        plan_rejection_reasons=rejected.reasons if rejected else (),
        mission_status=state.status,
        status_reason=state.status_reason,
        run_outcome=_run_outcome(terminal),
        verified=terminal.verified if isinstance(terminal, MissionCompletedPayload) else None,
        failure_cause=failed.cause if failed else None,
        failure_reason=failed.reason if failed else None,
        halt=terminal.halt if isinstance(terminal, MissionPausedPayload) else None,
        agent_calls_used=state.agent_calls_used,
        tool_calls_used=state.tool_calls_used,
        retries_used=state.retries_used,
        replans_used=state.replans_used,
        tokens_used=state.tokens_used,
        execution_time_used_ms=state.execution_time_used_ms,
        model_calls=len(calls),
        responses_missing_token_counts=sum(
            1 for call in calls if call.outcome is ModelCallOutcome.RESPONSE and (call.prompt_tokens is None or call.output_tokens is None)
        ),
        repeated_step_events=repeated,
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
        verification=settled.verification if settled else None,
    )


_NEVER_RAN = (MissionFailureCause.PLAN_REJECTED, MissionFailureCause.RUN_REJECTED)


def _run_outcome(terminal) -> RunOutcome | None:
    """The run's outcome as the terminal event implies it (the same mapping the recorder applies going the other way, D-160 item 5)."""
    if isinstance(terminal, MissionCompletedPayload):
        return RunOutcome.FINISHED
    if isinstance(terminal, MissionPausedPayload):
        return RunOutcome.HALTED
    if isinstance(terminal, MissionFailedPayload) and terminal.cause not in _NEVER_RAN:
        return RunOutcome.FAILED
    return None
