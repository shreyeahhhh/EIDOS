"""``task_relevance``/``relevant_experience``/``experience_for`` (decisions.md D-198; V1.0 Step 2).

``_experience(**overrides)`` is a minimal-valid-object factory in the same spirit as ``eidos_factories.py``'s own
``make_reliability_contract``/``make_task_genome`` — every test starts from a known-good ``ExecutionExperience``
and overrides only the field(s) under test.
"""

from uuid import UUID

from eidos.contracts import AutonomyLevel, CapabilityId, ExecutionId, MissionId, MissionStatus, RiskLevel, StrategyId, TenantId
from eidos.memory import ExecutionExperience, TaskRelevance, experience_for, relevant_experience, task_relevance
from eidos.planning import StrategyStage, VerificationPosture

from eidos_factories import make_task_genome
from eidos_planning_factories import make_strategy
from eidos_state_factories import T0

_TENANT, _MISSION = TenantId(UUID(int=1)), MissionId(UUID(int=2))


def _experience(**overrides) -> ExecutionExperience:
    fields = dict(
        tenant_id=_TENANT, mission_id=_MISSION, execution_id=ExecutionId(UUID(int=3)),
        strategy_id=StrategyId(UUID(int=4)), recorded_at=T0,
        strategy_stage_shapes=((CapabilityId("research"),),), strategy_verification=VerificationPosture.FINAL,
        task_required_capabilities=(CapabilityId("research"),), task_risk_level=RiskLevel.MEDIUM,
        task_autonomy_level=AutonomyLevel.SAFE_READ_ONLY,
        mission_status=MissionStatus.COMPLETED, verified=True,
        execution_time_used_ms=0, mission_wall_clock_ms=0, model_call_count=0, tokens_used=0,
        responses_missing_token_counts=0, agent_calls_used=0, tool_calls_used=0, retries_used=0, replans_used=0,
    )
    fields.update(overrides)
    return ExecutionExperience(**fields)


# --- task_relevance ------------------------------------------------------------------------------------------


def test_exact_same_task_shape_is_same():
    experience = _experience(
        task_required_capabilities=(CapabilityId("research"), CapabilityId("cost")),
        task_risk_level=RiskLevel.HIGH, task_autonomy_level=AutonomyLevel.REVERSIBLE,
    )
    genome = make_task_genome(
        required_capabilities=(CapabilityId("research"), CapabilityId("cost")),
        risk_level=RiskLevel.HIGH, autonomy_level=AutonomyLevel.REVERSIBLE,
    )
    assert task_relevance(experience, genome) is TaskRelevance.SAME


def test_capability_overlap_with_matching_risk_and_autonomy_is_similar():
    experience = _experience(
        task_required_capabilities=(CapabilityId("research"), CapabilityId("cost")),
        task_risk_level=RiskLevel.MEDIUM, task_autonomy_level=AutonomyLevel.SAFE_READ_ONLY,
    )
    genome = make_task_genome(
        required_capabilities=(CapabilityId("cost"), CapabilityId("security")),  # overlaps on "cost" only
        risk_level=RiskLevel.MEDIUM, autonomy_level=AutonomyLevel.SAFE_READ_ONLY,
    )
    assert task_relevance(experience, genome) is TaskRelevance.SIMILAR


def test_no_capability_overlap_is_irrelevant():
    experience = _experience(task_required_capabilities=(CapabilityId("research"),))
    genome = make_task_genome(
        required_capabilities=(CapabilityId("cost"),),
        risk_level=RiskLevel.MEDIUM, autonomy_level=AutonomyLevel.SAFE_READ_ONLY,
    )
    assert task_relevance(experience, genome) is TaskRelevance.IRRELEVANT


def test_risk_mismatch_is_irrelevant_even_with_identical_capabilities():
    experience = _experience(task_required_capabilities=(CapabilityId("research"),), task_risk_level=RiskLevel.LOW)
    genome = make_task_genome(
        required_capabilities=(CapabilityId("research"),),
        risk_level=RiskLevel.HIGH, autonomy_level=AutonomyLevel.SAFE_READ_ONLY,
    )
    assert task_relevance(experience, genome) is TaskRelevance.IRRELEVANT


def test_autonomy_mismatch_is_irrelevant_even_with_identical_capabilities():
    experience = _experience(
        task_required_capabilities=(CapabilityId("research"),), task_autonomy_level=AutonomyLevel.RECOMMEND_ONLY,
    )
    genome = make_task_genome(
        required_capabilities=(CapabilityId("research"),),
        risk_level=RiskLevel.MEDIUM, autonomy_level=AutonomyLevel.HUMAN_APPROVAL_REQUIRED,
    )
    assert task_relevance(experience, genome) is TaskRelevance.IRRELEVANT


def test_duplicate_capabilities_are_handled_structurally_as_sets():
    # Neither side's duplicates change the comparison: {research, cost} == {research, cost} regardless of how
    # many times either tuple repeats a capability.
    experience = _experience(
        task_required_capabilities=(CapabilityId("research"), CapabilityId("research"), CapabilityId("cost")),
    )
    genome = make_task_genome(
        required_capabilities=(CapabilityId("cost"), CapabilityId("research")),
        risk_level=RiskLevel.MEDIUM, autonomy_level=AutonomyLevel.SAFE_READ_ONLY,
    )
    assert task_relevance(experience, genome) is TaskRelevance.SAME


# --- relevant_experience --------------------------------------------------------------------------------------


def test_relevant_experience_excludes_irrelevant_history():
    genome = make_task_genome(
        required_capabilities=(CapabilityId("research"),), risk_level=RiskLevel.MEDIUM,
        autonomy_level=AutonomyLevel.SAFE_READ_ONLY,
    )
    same = _experience(task_required_capabilities=(CapabilityId("research"),))
    irrelevant_by_capability = _experience(task_required_capabilities=(CapabilityId("security"),))
    irrelevant_by_risk = _experience(task_required_capabilities=(CapabilityId("research"),), task_risk_level=RiskLevel.HIGH)

    result = relevant_experience((), genome, (same, irrelevant_by_capability, irrelevant_by_risk))

    assert result == (same,)


def test_relevant_experience_preserves_insertion_order():
    genome = make_task_genome(
        required_capabilities=(CapabilityId("research"), CapabilityId("cost")), risk_level=RiskLevel.MEDIUM,
        autonomy_level=AutonomyLevel.SAFE_READ_ONLY,
    )
    similar = _experience(task_required_capabilities=(CapabilityId("cost"),), recorded_at=T0)
    same_first = _experience(task_required_capabilities=(CapabilityId("research"), CapabilityId("cost")), recorded_at=T0)
    same_second = _experience(task_required_capabilities=(CapabilityId("cost"), CapabilityId("research")), recorded_at=T0)
    history = (similar, same_first, same_second)

    assert relevant_experience((), genome, history) == history  # every one is relevant here; order must match exactly


def test_relevant_experience_on_empty_history_is_empty():
    genome = make_task_genome(required_capabilities=(CapabilityId("research"),))
    assert relevant_experience((), genome, ()) == ()


def test_relevant_experience_is_pure_and_never_mutates_its_inputs():
    genome = make_task_genome(
        required_capabilities=(CapabilityId("research"),), risk_level=RiskLevel.MEDIUM,
        autonomy_level=AutonomyLevel.SAFE_READ_ONLY,
    )
    history = (_experience(), _experience(task_required_capabilities=(CapabilityId("security"),)))
    first = relevant_experience((), genome, history)
    second = relevant_experience((), genome, history)
    assert first == second
    assert history == (history[0], history[1])  # unchanged


# --- experience_for --------------------------------------------------------------------------------------------


def test_experience_for_matches_identical_strategy_shape():
    candidate = make_strategy(
        stages=(StrategyStage(capabilities=(CapabilityId("research"), CapabilityId("cost"))),),
        verification=VerificationPosture.FINAL,
    )
    matching = _experience(
        strategy_stage_shapes=((CapabilityId("research"), CapabilityId("cost")),),
        strategy_verification=VerificationPosture.FINAL,
    )
    assert experience_for(candidate, (matching,)) == (matching,)


def test_experience_for_excludes_a_different_strategy_shape():
    candidate = make_strategy(
        stages=(StrategyStage(capabilities=(CapabilityId("research"),)),), verification=VerificationPosture.FINAL,
    )
    different_stage_count = _experience(
        strategy_stage_shapes=((CapabilityId("research"),), (CapabilityId("cost"),)),
        strategy_verification=VerificationPosture.FINAL,
    )
    different_capability = _experience(
        strategy_stage_shapes=((CapabilityId("cost"),),), strategy_verification=VerificationPosture.FINAL,
    )
    different_order = _experience(
        strategy_stage_shapes=((CapabilityId("cost"), CapabilityId("research")),),  # a different candidate's own shape
        strategy_verification=VerificationPosture.FINAL,
    )
    assert experience_for(candidate, (different_stage_count, different_capability, different_order)) == ()


def test_experience_for_excludes_a_verification_posture_mismatch():
    candidate = make_strategy(
        stages=(StrategyStage(capabilities=(CapabilityId("research"),)),), verification=VerificationPosture.FINAL,
    )
    same_shape_different_verification = _experience(
        strategy_stage_shapes=((CapabilityId("research"),),), strategy_verification=VerificationPosture.NONE,
    )
    assert experience_for(candidate, (same_shape_different_verification,)) == ()


def test_experience_for_ignores_strategy_id_entirely():
    # A fresh StrategyId every generation round (D-182) must never affect matching — only shape/verification do.
    candidate = make_strategy(
        strategy_id=StrategyId(UUID(int=900_001)),
        stages=(StrategyStage(capabilities=(CapabilityId("research"),)),), verification=VerificationPosture.FINAL,
    )
    recorded_under_a_different_id = _experience(
        strategy_id=StrategyId(UUID(int=555_555)),
        strategy_stage_shapes=((CapabilityId("research"),),), strategy_verification=VerificationPosture.FINAL,
    )
    assert experience_for(candidate, (recorded_under_a_different_id,)) == (recorded_under_a_different_id,)
    assert candidate.strategy_id == StrategyId(UUID(int=900_001))  # candidate identity is untouched


def test_experience_for_on_empty_history_is_empty():
    candidate = make_strategy()
    assert experience_for(candidate, ()) == ()


def test_experience_for_partitions_correctly_across_multiple_candidates():
    linear = make_strategy(
        strategy_id=StrategyId(UUID(int=1)),
        stages=(StrategyStage(capabilities=(CapabilityId("research"),)), StrategyStage(capabilities=(CapabilityId("cost"),))),
        verification=VerificationPosture.FINAL,
    )
    parallel = make_strategy(
        strategy_id=StrategyId(UUID(int=2)),
        stages=(StrategyStage(capabilities=(CapabilityId("research"), CapabilityId("cost"))),),
        verification=VerificationPosture.FINAL,
    )
    for_linear = _experience(
        strategy_stage_shapes=((CapabilityId("research"),), (CapabilityId("cost"),)), strategy_verification=VerificationPosture.FINAL,
    )
    for_parallel = _experience(
        strategy_stage_shapes=((CapabilityId("research"), CapabilityId("cost")),), strategy_verification=VerificationPosture.FINAL,
    )
    history = (for_linear, for_parallel)

    assert experience_for(linear, history) == (for_linear,)
    assert experience_for(parallel, history) == (for_parallel,)


def test_experience_for_is_pure_and_never_mutates_its_inputs():
    candidate = make_strategy(stages=(StrategyStage(capabilities=(CapabilityId("research"),)),), verification=VerificationPosture.FINAL)
    history = (_experience(strategy_stage_shapes=((CapabilityId("research"),),), strategy_verification=VerificationPosture.FINAL),)
    first = experience_for(candidate, history)
    second = experience_for(candidate, history)
    assert first == second
    assert history == (history[0],)  # unchanged
