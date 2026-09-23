"""``ExecutionExperience``/``evaluate_experience`` (decisions.md D-198; V1.0 Step 1).

Built the same way ``tests/unit/telemetry/test_telemetry_project.py`` builds its own inputs: a hand-built log via
``LogBuilder`` (``eidos_state_factories.py``), projected with the real, unmodified ``project``, so this suite
stays independent of everything above ``eidos.state``/``eidos.telemetry`` — no agent, backend or provider import.
"""

from datetime import timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from eidos.contracts import AutonomyLevel, CapabilityId, ExecutionId, MissionId, MissionStatus, RiskLevel, TenantId
from eidos.memory import ExecutionExperience, evaluate_experience
from eidos.planning import StrategyStage, VerificationPosture
from eidos.telemetry import TelemetryRecord, project

from eidos_factories import make_task_genome
from eidos_planning_factories import make_strategy
from eidos_state_factories import T0, at, verified_baseline


def _telemetry() -> TelemetryRecord:
    result = project(verified_baseline().records)
    assert isinstance(result, TelemetryRecord)
    return result


def _distinct_count_telemetry() -> TelemetryRecord:
    """A hand-built ``TelemetryRecord`` (never via ``project`` — every count field is given a distinct value, which
    no currently-achievable real run can produce: today's runtime never dispatches a retry or a replan, D-170, so
    every real ``TelemetryRecord`` has ``retries_used == replans_used == 0`` and a field swap between them would be
    undetectable against a real fixture alone. This exists so a swapped-field mutation has something to be caught
    against for every count, not only the ones a real baseline happens to vary."""
    return TelemetryRecord(
        tenant_id=TenantId(UUID(int=1)), mission_id=MissionId(UUID(int=2)), execution_id=ExecutionId(UUID(int=3)),
        agent_calls_used=11, tool_calls_used=12, retries_used=13, replans_used=14, tokens_used=15,
        execution_time_used_ms=16, responses_missing_token_counts=17,
        mission_status=MissionStatus.COMPLETED, verified=True,
        succeeded_count=1, failed_count=0, no_result_count=0, verification_failed_count=0,
        verification_inconclusive_count=0, skipped_count=0, not_reached_count=0, awaiting_count=0,
        model_call_count=18, remote_task_count=19,
        event_count=1, first_occurred_at=T0, last_occurred_at=at(20), mission_wall_clock_ms=20_000,
    )


# --- field-for-field mapping ------------------------------------------------------------------------------------


def test_every_count_field_maps_to_its_own_distinct_destination():
    telemetry = _distinct_count_telemetry()
    experience = evaluate_experience(make_strategy(), make_task_genome(), telemetry, recorded_at=T0)

    assert experience.agent_calls_used == 11
    assert experience.tool_calls_used == 12
    assert experience.retries_used == 13
    assert experience.replans_used == 14
    assert experience.tokens_used == 15
    assert experience.execution_time_used_ms == 16
    assert experience.responses_missing_token_counts == 17
    assert experience.model_call_count == 18
    assert experience.mission_wall_clock_ms == 20_000


def test_every_identity_and_outcome_field_is_copied_from_telemetry_exactly():
    telemetry = _telemetry()
    strategy = make_strategy()
    genome = make_task_genome()

    experience = evaluate_experience(strategy, genome, telemetry, recorded_at=T0)

    assert (experience.tenant_id, experience.mission_id, experience.execution_id) == (
        telemetry.tenant_id, telemetry.mission_id, telemetry.execution_id,
    )
    assert (experience.plan_id, experience.plan_version) == (telemetry.plan_id, telemetry.plan_version)
    assert experience.mission_status == telemetry.mission_status
    assert experience.run_outcome == telemetry.run_outcome
    assert experience.verified == telemetry.verified
    assert experience.failure_cause == telemetry.failure_cause
    assert experience.plan_rejected_at == telemetry.plan_rejected_at
    assert experience.execution_time_used_ms == telemetry.execution_time_used_ms
    assert experience.mission_wall_clock_ms == telemetry.mission_wall_clock_ms
    assert experience.model_call_count == telemetry.model_call_count
    assert experience.tokens_used == telemetry.tokens_used
    assert experience.responses_missing_token_counts == telemetry.responses_missing_token_counts
    assert experience.agent_calls_used == telemetry.agent_calls_used
    assert experience.tool_calls_used == telemetry.tool_calls_used
    assert experience.retries_used == telemetry.retries_used
    assert experience.replans_used == telemetry.replans_used


def test_strategy_identity_and_shape_are_extracted_from_the_strategy_not_the_telemetry():
    telemetry = _telemetry()  # carries no strategy_id at all (V0.9 Step 4, deliberate)
    strategy = make_strategy(
        stages=(
            StrategyStage(capabilities=(CapabilityId("research"), CapabilityId("cost"))),
            StrategyStage(capabilities=(CapabilityId("security"),)),
        ),
        verification=VerificationPosture.FINAL,
    )
    genome = make_task_genome()

    experience = evaluate_experience(strategy, genome, telemetry, recorded_at=T0)

    assert experience.strategy_id == strategy.strategy_id
    assert experience.strategy_stage_shapes == (
        (CapabilityId("research"), CapabilityId("cost")),
        (CapabilityId("security"),),
    )
    assert experience.strategy_verification is VerificationPosture.FINAL


def test_task_characteristics_are_extracted_from_the_task_genome():
    telemetry = _telemetry()
    strategy = make_strategy()
    genome = make_task_genome(
        required_capabilities=(CapabilityId("cost"), CapabilityId("security")),
        risk_level=RiskLevel.HIGH,
        autonomy_level=AutonomyLevel.REVERSIBLE,
    )

    experience = evaluate_experience(strategy, genome, telemetry, recorded_at=T0)

    assert experience.task_required_capabilities == (CapabilityId("cost"), CapabilityId("security"))
    assert experience.task_risk_level is RiskLevel.HIGH
    assert experience.task_autonomy_level is AutonomyLevel.REVERSIBLE


def test_recorded_at_is_exactly_what_the_caller_supplied_never_derived():
    telemetry = _telemetry()
    strategy = make_strategy()
    genome = make_task_genome()
    stamp = T0 + timedelta(days=400)  # far from T0 and from "now" — proves nothing internal generates a time

    experience = evaluate_experience(strategy, genome, telemetry, recorded_at=stamp)

    assert experience.recorded_at == stamp


# --- immutability / strictness, matching every other EidosModel in this project -----------------------------------


def test_execution_experience_is_frozen():
    experience = evaluate_experience(make_strategy(), make_task_genome(), _telemetry(), recorded_at=T0)
    with pytest.raises(ValidationError):
        experience.verified = False  # type: ignore[misc]


def test_execution_experience_rejects_an_unknown_field():
    fields = evaluate_experience(make_strategy(), make_task_genome(), _telemetry(), recorded_at=T0).model_dump()
    fields["quality_score"] = 0.9  # exactly the forbidden concept this type must never carry
    with pytest.raises(ValidationError):
        ExecutionExperience(**fields)


def test_execution_experience_round_trips_through_strict_json():
    experience = evaluate_experience(make_strategy(), make_task_genome(), _telemetry(), recorded_at=T0)
    assert ExecutionExperience.model_validate_json(experience.model_dump_json()) == experience


# --- purity: the same inputs always produce the same, byte-identical output ----------------------------------------


def test_evaluate_experience_is_a_pure_function_of_its_arguments():
    strategy, genome, telemetry = make_strategy(), make_task_genome(), _telemetry()
    first = evaluate_experience(strategy, genome, telemetry, recorded_at=T0)
    second = evaluate_experience(strategy, genome, telemetry, recorded_at=T0)
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
