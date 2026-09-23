"""``ExecutionExperience`` — the smallest immutable representation of one completed mission's measured facts
(V1.0 Step 1; decisions.md D-198, the V1.0 architecture approved 2026-09-23).

A core layer, joining ``eidos.contracts``, ``eidos.runtime``, ``eidos.state``, ``eidos.telemetry`` and
``eidos.planning``: deterministic, no I/O, no clock, no hidden state, no model/vendor name (invariant 9). Every
field here is either copied verbatim from an already-recorded ``TelemetryRecord`` or extracted structurally from
the ``Strategy``/``TaskGenome`` the caller already held when the mission that produced that telemetry ran —
nothing is measured here that was not already measured upstream, and nothing is judged: no quality, no
confidence, no score, no rate, no "trust" value (D-198, decision item 7: "keep `ExecutionExperience` immutable
and factual").

**Strategy identity is never reconstructed from telemetry.** ``TelemetryRecord`` carries no ``strategy_id``
(deliberately, V0.9 Step 4) and none is added to it, to ``Plan``, to ``MissionState``, to ``ExecutionRecord`` or
to any ``MissionEvent`` by this module or any other (D-198, decision item 8). The Strategy<->execution linkage
exists *only* inside this type, made once, by the one caller who already holds both objects in scope at the
moment a mission concludes — the identical "external correlation suffices" reasoning V0.9 Step 4 and the V0.9
benchmark harness already used, one layer further.

    from eidos.memory.experience import ExecutionExperience, evaluate_experience

``evaluate_experience`` is a pure function of its three arguments plus an injected ``recorded_at`` — it reads no
clock itself, mirroring ``eidos.recording``'s own "the clock is injected, never read inside a deterministic
component" discipline (D-158 item 3), applied here one layer after execution rather than during it.

**What is directly observed vs. derived** (every field is one or the other, never a third thing): every field on
``ExecutionExperience`` is a **copy** of an already-recorded fact from ``TelemetryRecord``, or a **structural
extraction** from ``Strategy``/``TaskGenome`` (``strategy_stage_shapes``, ``strategy_verification``,
``task_required_capabilities``, ``task_risk_level``, ``task_autonomy_level``) — nothing here performs
arithmetic, aggregation or judgment of any kind. "What evidence is actually trustworthy" is answered
structurally, not by a synthesized trust score: ``mission_status``/``verified``/``failure_cause`` already say,
precisely, whether the recorded outcome came from a completed, verified run, a failed run, or a rejected plan —
a later consumer (relevance/selection) reads these typed facts directly.
"""

from pydantic import Field

from eidos.contracts import (
    AutonomyLevel,
    CapabilityId,
    EidosModel,
    ExecutionId,
    MissionId,
    MissionStatus,
    PlanId,
    RiskLevel,
    StrategyId,
    TaskGenome,
    TenantId,
)
from eidos.contracts._validators import UtcDateTime
from eidos.planning import Strategy, VerificationPosture
from eidos.runtime import RunOutcome
from eidos.state import MissionFailureCause, PlanRejectionStage
from eidos.telemetry import TelemetryRecord


class ExecutionExperience(EidosModel):
    """One completed mission's measured facts, immutable and factual. See the module docstring for what each
    field is copied or extracted from, and for what is deliberately excluded."""

    # --- identity ------------------------------------------------------------------------------------------
    tenant_id: TenantId
    mission_id: MissionId
    execution_id: ExecutionId
    plan_id: PlanId | None = None
    plan_version: int | None = Field(default=None, ge=1)
    strategy_id: StrategyId
    recorded_at: UtcDateTime  # when this record was constructed; injected, never read from a clock here

    # --- what strategy was attempted: structural facts only, no signature (D-021 stays Open, untouched) -----
    strategy_stage_shapes: tuple[tuple[CapabilityId, ...], ...]
    strategy_verification: VerificationPosture

    # --- what task characteristics were present: the only fields usable for relevance (eidos.memory.relevance) -
    task_required_capabilities: tuple[CapabilityId, ...]
    task_risk_level: RiskLevel
    task_autonomy_level: AutonomyLevel

    # --- what execution outcome occurred --------------------------------------------------------------------
    mission_status: MissionStatus
    run_outcome: RunOutcome | None = None
    verified: bool | None = None
    failure_cause: MissionFailureCause | None = None
    plan_rejected_at: PlanRejectionStage | None = None

    # --- what measurable execution cost existed ---------------------------------------------------------------
    execution_time_used_ms: int = Field(ge=0)
    mission_wall_clock_ms: int  # signed — mirrors TelemetryRecord's own field exactly, see its own docstring
    model_call_count: int = Field(ge=0)
    tokens_used: int = Field(ge=0)
    responses_missing_token_counts: int = Field(ge=0)
    agent_calls_used: int = Field(ge=0)
    tool_calls_used: int = Field(ge=0)
    retries_used: int = Field(ge=0)
    replans_used: int = Field(ge=0)


def evaluate_experience(
    strategy: Strategy, task_genome: TaskGenome, telemetry: TelemetryRecord, *, recorded_at: UtcDateTime
) -> ExecutionExperience:
    """Construct the ``ExecutionExperience`` for one completed mission. Pure: no I/O, no clock read, no
    randomness — ``recorded_at`` is supplied by the caller, exactly as ``eidos.recording``'s own injected
    ``Clock`` is never read inside a deterministic component."""
    return ExecutionExperience(
        tenant_id=telemetry.tenant_id,
        mission_id=telemetry.mission_id,
        execution_id=telemetry.execution_id,
        plan_id=telemetry.plan_id,
        plan_version=telemetry.plan_version,
        strategy_id=strategy.strategy_id,
        recorded_at=recorded_at,
        strategy_stage_shapes=tuple(stage.capabilities for stage in strategy.stages),
        strategy_verification=strategy.verification,
        task_required_capabilities=task_genome.required_capabilities,
        task_risk_level=task_genome.risk_level,
        task_autonomy_level=task_genome.autonomy_level,
        mission_status=telemetry.mission_status,
        run_outcome=telemetry.run_outcome,
        verified=telemetry.verified,
        failure_cause=telemetry.failure_cause,
        plan_rejected_at=telemetry.plan_rejected_at,
        execution_time_used_ms=telemetry.execution_time_used_ms,
        mission_wall_clock_ms=telemetry.mission_wall_clock_ms,
        model_call_count=telemetry.model_call_count,
        tokens_used=telemetry.tokens_used,
        responses_missing_token_counts=telemetry.responses_missing_token_counts,
        agent_calls_used=telemetry.agent_calls_used,
        tool_calls_used=telemetry.tool_calls_used,
        retries_used=telemetry.retries_used,
        replans_used=telemetry.replans_used,
    )
