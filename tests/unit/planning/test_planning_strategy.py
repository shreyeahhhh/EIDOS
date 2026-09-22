"""``Strategy``, ``StrategyStage``, ``VerificationPosture`` (decisions.md D-178, D-179, D-182; V0.7 Step 2).

Contract-only tests: construction, immutability, the forbidden-concepts boundary (D-179), and deterministic
equality/serialization, mirroring ``tests/unit/contracts/test_plan.py``'s own conventions for a sibling type.
No ``CandidateGenerator``, feasibility filtering, or Strategy-to-Plan expansion exists yet to test.
"""

import json
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from eidos.contracts import CapabilityId, DEFAULT_TENANT_ID, MissionId, StrategyId, TenantId
from eidos.planning import Strategy, StrategyStage, VerificationPosture

from eidos_planning_factories import MISSION, TENANT, make_strategy, make_strategy_id, make_strategy_stage

# --- StrategyStage ----------------------------------------------------------------------------------------------


def test_stage_valid_construction():
    stage = make_strategy_stage("research")
    assert stage.capabilities == (CapabilityId("research"),)


def test_stage_may_hold_more_than_one_capability_in_parallel():
    stage = StrategyStage(capabilities=(CapabilityId("research"), CapabilityId("security")))
    assert len(stage.capabilities) == 2


def test_stage_allows_a_repeated_capability():
    # Two parallel calls to the same capability is a legitimate shape (module docstring); StrategyStage
    # is a multiset, unlike AgentDescriptor.capabilities (D-134), which is a set.
    stage = StrategyStage(capabilities=(CapabilityId("research"), CapabilityId("research")))
    assert stage.capabilities == (CapabilityId("research"), CapabilityId("research"))


def test_an_empty_stage_is_rejected():
    with pytest.raises(ValidationError):
        StrategyStage(capabilities=())


def test_stage_is_immutable():
    stage = make_strategy_stage("research")
    with pytest.raises(ValidationError):
        stage.capabilities = (CapabilityId("cost"),)


def test_stage_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        StrategyStage(capabilities=(CapabilityId("research"),), agent_id=str(uuid4()))


def test_capability_typing_is_not_coerced_from_an_arbitrary_object():
    # EidosModel is strict (CLAUDE.md §8): a CapabilityId is a str-backed NewType, but the field
    # still refuses a non-string value rather than silently stringifying it.
    with pytest.raises(ValidationError):
        StrategyStage(capabilities=(123,))


# --- VerificationPosture ------------------------------------------------------------------------------------------


def test_verification_posture_has_exactly_two_members():
    # D-179 item 2: narrow by design — only one deterministic Verifier exists (D-133).
    assert {member.value for member in VerificationPosture} == {"none", "final"}


def test_verification_posture_round_trips_by_value():
    assert VerificationPosture("final") is VerificationPosture.FINAL
    assert VerificationPosture("none") is VerificationPosture.NONE


def test_verification_rejects_an_unenumerated_value():
    with pytest.raises(ValidationError):
        make_strategy(verification="partial")


# --- Strategy: construction and required/optional fields ---------------------------------------------------------


def test_valid_construction_with_only_required_fields():
    strategy = Strategy(
        mission_id=MISSION,
        strategy_id=make_strategy_id(),
        stages=(make_strategy_stage("research"),),
        verification=VerificationPosture.FINAL,
        rationale="a reason",
    )
    assert strategy.tenant_id == DEFAULT_TENANT_ID


def test_tenant_id_defaults_when_omitted():
    strategy = Strategy(
        mission_id=MISSION,
        strategy_id=make_strategy_id(),
        stages=(),
        verification=VerificationPosture.NONE,
        rationale="a reason",
    )
    assert strategy.tenant_id == DEFAULT_TENANT_ID


def test_mission_id_is_required():
    with pytest.raises(ValidationError):
        Strategy(
            tenant_id=TENANT,
            strategy_id=make_strategy_id(),
            stages=(),
            verification=VerificationPosture.NONE,
            rationale="a reason",
        )


def test_strategy_id_is_required():
    with pytest.raises(ValidationError):
        Strategy(
            mission_id=MISSION,
            stages=(),
            verification=VerificationPosture.NONE,
            rationale="a reason",
        )


def test_stages_field_is_required():
    with pytest.raises(ValidationError):
        Strategy(
            mission_id=MISSION,
            strategy_id=make_strategy_id(),
            verification=VerificationPosture.NONE,
            rationale="a reason",
        )


def test_verification_field_is_required():
    with pytest.raises(ValidationError):
        Strategy(
            mission_id=MISSION,
            strategy_id=make_strategy_id(),
            stages=(),
            rationale="a reason",
        )


def test_rationale_field_is_required():
    with pytest.raises(ValidationError):
        Strategy(
            mission_id=MISSION,
            strategy_id=make_strategy_id(),
            stages=(),
            verification=VerificationPosture.NONE,
        )


def test_stages_may_be_empty():
    # Mirrors D-106's "empty plans pass": a mission with nothing to allocate has a legitimate empty shape.
    strategy = make_strategy(stages=())
    assert strategy.stages == ()


def test_stages_may_hold_several_levels_in_sequence():
    strategy = make_strategy(stages=(make_strategy_stage("research"), make_strategy_stage("cost", "security")))
    assert len(strategy.stages) == 2
    assert strategy.stages[1].capabilities == (CapabilityId("cost"), CapabilityId("security"))


def test_rationale_must_be_non_empty():
    with pytest.raises(ValidationError):
        make_strategy(rationale="")


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        make_strategy(unexpected_field=123)


# --- immutability -------------------------------------------------------------------------------------------------


def test_strategy_is_immutable():
    strategy = make_strategy()
    with pytest.raises(ValidationError):
        strategy.rationale = "changed"


def test_strategy_stages_tuple_cannot_be_reassigned():
    strategy = make_strategy()
    with pytest.raises(ValidationError):
        strategy.stages = ()


# --- StrategyId typing ---------------------------------------------------------------------------------------------


def test_strategy_id_is_a_plain_uuid_backed_value():
    strategy_id = make_strategy_id(1)
    assert isinstance(strategy_id, UUID)
    strategy = make_strategy(strategy_id=strategy_id)
    assert strategy.strategy_id == strategy_id


def test_two_strategies_from_the_same_generation_round_have_distinct_ids():
    first = make_strategy(strategy_id=make_strategy_id(1))
    second = make_strategy(strategy_id=make_strategy_id(2))
    assert first.strategy_id != second.strategy_id


# --- forbidden strategy concepts (D-179): rejected or simply absent, wherever practical ----------------------------


def test_strategy_has_no_step_id_field():
    assert "step_id" not in Strategy.model_fields
    with pytest.raises(ValidationError):
        make_strategy(step_id="gather")


def test_strategy_has_no_dependency_edge_field():
    assert "depends_on" not in Strategy.model_fields
    with pytest.raises(ValidationError):
        make_strategy(depends_on=())


def test_strategy_has_no_agent_id_field():
    assert "agent_id" not in Strategy.model_fields
    with pytest.raises(ValidationError):
        make_strategy(agent_id=str(uuid4()))


def test_strategy_has_no_model_or_vendor_field():
    assert "model" not in Strategy.model_fields
    with pytest.raises(ValidationError):
        make_strategy(model="qwen3:4b")


def test_strategy_has_no_tool_field():
    assert "tool" not in Strategy.model_fields
    assert "tools" not in Strategy.model_fields
    with pytest.raises(ValidationError):
        make_strategy(tools=("search_documents",))


def test_strategy_has_no_retry_or_replan_field():
    assert "max_retries" not in Strategy.model_fields
    assert "max_replans" not in Strategy.model_fields
    assert "retry_policy" not in Strategy.model_fields
    with pytest.raises(ValidationError):
        make_strategy(max_retries=3)


def test_strategy_stage_carries_no_step_id_or_dependency_edge():
    assert "step_id" not in StrategyStage.model_fields
    assert "depends_on" not in StrategyStage.model_fields


def test_strategy_field_set_is_exactly_the_approved_dimensions():
    # D-179: topology (stages), verification, capability allocation, plus identity. Nothing else.
    assert set(Strategy.model_fields) == {
        "tenant_id", "mission_id", "strategy_id", "stages", "verification", "rationale",
    }


# --- deterministic equality / serialization, consistent with existing EIDOS models ---------------------------------


def test_two_strategies_built_from_the_same_fields_are_equal():
    strategy_id = make_strategy_id(7)
    a = make_strategy(strategy_id=strategy_id)
    b = make_strategy(strategy_id=strategy_id)
    assert a == b


def test_a_strategy_with_a_different_field_is_not_equal():
    a = make_strategy()
    b = make_strategy(rationale="a different reason")
    assert a != b


def test_strategy_is_hashable_like_other_frozen_eidos_models():
    strategy = make_strategy()
    {strategy}  # a frozen, hashable model can be put in a set without raising


def test_strategy_round_trips_through_json():
    strategy = make_strategy(stages=(make_strategy_stage("research"), make_strategy_stage("cost", "security")))
    restored = Strategy.model_validate_json(strategy.model_dump_json())
    assert restored == strategy


def test_strategy_json_uses_plain_capability_strings():
    strategy = make_strategy(stages=(make_strategy_stage("research"),))
    dumped = json.loads(strategy.model_dump_json())
    assert dumped["stages"][0]["capabilities"] == ["research"]
    assert dumped["verification"] == "final"


def test_strategy_json_round_trip_rejects_an_extra_field_like_plan_does():
    # Mirrors test_plan.py's own "not recoverable with a bogus field" check.
    dumped = json.loads(make_strategy().model_dump_json())
    dumped["bogus"] = 1
    with pytest.raises(ValidationError):
        Strategy.model_validate_json(json.dumps(dumped))
