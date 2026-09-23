"""``project`` — the deterministic multi-execution telemetry projection (decisions.md D-159, D-196; V0.9 Steps 2-4).

**Event Log is authoritative. ``ExecutionRecord`` is a derived, single-execution projection of it (D-159). Telemetry
is one more projection, over the same already-recorded facts, generalized to be read alongside other executions'
own telemetry** — never a second authoritative state store, never written back, never richer than what the log
already proved happened. ``project`` composes ``eidos.state.execution_record`` rather than re-folding events
itself: every fact below is either copied straight from ``ExecutionRecord``, or derived from the same ``records``
``execution_record`` was already given.

**Pure and deterministic, exactly like ``execution_record`` itself.** No I/O, no clock, no randomness, no model
call, no filesystem access. ``project`` takes an in-memory ``Iterable[EventRecord]`` — precisely
``execution_record``'s own signature — and returns a value, or propagates the identical typed ``ReplayRejection``
``execution_record`` already returns for a log that does not replay. If a filesystem or other outer loader is
ever needed to gather those records from durable storage, it belongs strictly outside this function, exactly as
the brief requires: nothing here opens a file, and nothing ever should.

**Only genuinely derived facts are added, nothing new is captured.** Per-status node counts, the count of
remote-task submissions recorded, and a mission wall-clock span are all computable from data ``execution_record`` (and the
``records`` it was built from) already carries — none of it is a new measurement. Three things this module
deliberately does **not** do, each already flagged in the V0.9 Step 1 proposal as a separate, later, unbuilt
question, not decided here: it does not add a model identifier to any recorded fact (``ModelCallFacts`` is
unchanged); it does not attempt to name a ``Strategy`` (no execution today is produced from one, D-129/D-185
stay untouched); and it computes no quality, confidence, rate or score of any kind (D-159 item 2's own exclusion,
applied identically one layer up).

**V0.9 Step 4 adds two fields, both already computed by ``ExecutionRecord`` and simply copied through, not newly
measured.** ``execution_time_used_ms`` is the sixth ``MissionState`` counter — present on ``ExecutionRecord``
since D-159, missing here since Step 2 (an implementation gap found by inspection, not a deliberate scope
decision anyone had ruled on). It matters specifically because it is **not** the same signal as
``mission_wall_clock_ms``: the reducer sums each node's own ``duration_ms``, so a strategy whose stages run in
parallel can show a wall-clock span shorter than its own accumulated node time, while a sequential strategy's
two numbers track closely — the distinction between "fast because parallel" and "fast because cheap." Never
combined with ``mission_wall_clock_ms`` into a third number (D-158 item 4's "labelled by source, never
combined," applied here too). ``plan_rejected_at`` is copied from ``ExecutionRecord.plan_rejected_at`` alone —
deliberately **not** ``plan_rejection_reasons``, which stays a per-case, free-text-bearing detail one hop away in
``ExecutionRecord``/the raw log, consistent with this type's own "counts and typed enums, not per-case detail"
shape.

**``mission_wall_clock_ms`` may be negative.** ``ExecutionRecord.first_occurred_at``/``last_occurred_at`` are
documented as "bounds of the log, never an ordering" — ``occurred_at`` is the producer's own domain timestamp
(D-086), not the log's own monotonic ``sequence``, so a pathological or externally-produced log could record an
earlier bound after a later one. Clamping that away would hide a real anomaly (D-158 item 4's "facts only," never
a guess); the field is left a signed value on purpose, and its own sign is itself a fact worth keeping.
"""

from collections.abc import Iterable

from pydantic import Field

from eidos.contracts import EidosModel, ExecutionId, MissionId, MissionStatus, PlanId, TenantId
from eidos.contracts._validators import UtcDateTime
from eidos.runtime import NodeStatus, RunOutcome
from eidos.state import (
    A2ATaskStartedPayload,
    EventRecord,
    MissionFailureCause,
    PlanRejectionStage,
    ReplayRejection,
    execution_record,
)


class TelemetryRecord(EidosModel):
    """One execution's already-recorded facts, gathered for reading alongside other executions' own telemetry.
    Nothing here is a new measurement — every field is copied or derived from ``ExecutionRecord``/the log it was
    built from. No quality, confidence, rate, score or ``strategy_id`` — see the module docstring."""

    tenant_id: TenantId
    mission_id: MissionId
    execution_id: ExecutionId
    plan_id: PlanId | None = None
    plan_version: int | None = Field(default=None, ge=1)

    agent_calls_used: int = Field(ge=0)
    tool_calls_used: int = Field(ge=0)
    retries_used: int = Field(ge=0)
    replans_used: int = Field(ge=0)
    tokens_used: int = Field(ge=0)
    execution_time_used_ms: int = Field(ge=0)  # accumulated accounted node time (sum of each node's own duration_ms), not wall-clock (D-160 item 6)
    responses_missing_token_counts: int = Field(ge=0)

    mission_status: MissionStatus
    run_outcome: RunOutcome | None = None
    failure_cause: MissionFailureCause | None = None
    plan_rejected_at: PlanRejectionStage | None = None
    verified: bool | None = None

    succeeded_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    no_result_count: int = Field(ge=0)
    verification_failed_count: int = Field(ge=0)
    verification_inconclusive_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    not_reached_count: int = Field(ge=0)
    awaiting_count: int = Field(ge=0)

    model_call_count: int = Field(ge=0)
    remote_task_count: int = Field(ge=0)  # remote-task submissions recorded, from whichever remote-execution boundary produced them

    event_count: int = Field(ge=1)
    first_occurred_at: UtcDateTime
    last_occurred_at: UtcDateTime
    mission_wall_clock_ms: int  # signed — see the module docstring


def project(records: Iterable[EventRecord]) -> TelemetryRecord | ReplayRejection:
    """Project ``records`` into a ``TelemetryRecord``, or the typed rejection if the log does not replay."""
    materialized = tuple(records)
    record = execution_record(materialized)
    if isinstance(record, ReplayRejection):
        return record

    counts: dict[NodeStatus, int] = {status: 0 for status in NodeStatus}
    for step in record.steps:
        if step.result is not None:
            counts[step.result.status] += 1

    remote_task_count = sum(1 for r in materialized if isinstance(r.payload, A2ATaskStartedPayload))
    span = record.last_occurred_at - record.first_occurred_at
    wall_clock_ms = round(span.total_seconds() * 1000)

    return TelemetryRecord(
        tenant_id=record.tenant_id,
        mission_id=record.mission_id,
        execution_id=record.execution_id,
        plan_id=record.plan_id,
        plan_version=record.plan_version,
        agent_calls_used=record.agent_calls_used,
        tool_calls_used=record.tool_calls_used,
        retries_used=record.retries_used,
        replans_used=record.replans_used,
        tokens_used=record.tokens_used,
        execution_time_used_ms=record.execution_time_used_ms,
        responses_missing_token_counts=record.responses_missing_token_counts,
        mission_status=record.mission_status,
        run_outcome=record.run_outcome,
        failure_cause=record.failure_cause,
        plan_rejected_at=record.plan_rejected_at,
        verified=record.verified,
        succeeded_count=counts[NodeStatus.SUCCEEDED],
        failed_count=counts[NodeStatus.FAILED],
        no_result_count=counts[NodeStatus.NO_RESULT],
        verification_failed_count=counts[NodeStatus.VERIFICATION_FAILED],
        verification_inconclusive_count=counts[NodeStatus.VERIFICATION_INCONCLUSIVE],
        skipped_count=counts[NodeStatus.SKIPPED],
        not_reached_count=counts[NodeStatus.NOT_REACHED],
        awaiting_count=counts[NodeStatus.AWAITING],
        model_call_count=record.model_calls,
        remote_task_count=remote_task_count,
        event_count=record.event_count,
        first_occurred_at=record.first_occurred_at,
        last_occurred_at=record.last_occurred_at,
        mission_wall_clock_ms=wall_clock_ms,
    )
