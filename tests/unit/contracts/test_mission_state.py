"""MissionState (decisions.md D-010a, D-042, D-077, D-082, D-084, D-085, D-088, D-091, D-097, D-100).

MissionState composes every other V0.1 contract, so its tests are last.
Most tests here exercise the six cross-object consistency validators
approved as A7 (2026-09-18): contract-reference consistency, plan/mission_id
consistency, plan_id uniqueness, plan-lineage referential integrity,
active_plan_id referential integrity, and tenant consistency.
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from eidos.contracts import (
    DEFAULT_TENANT_ID,
    ExecutionId,
    MissionId,
    MissionState,
    MissionStatus,
    PlanId,
    TenantId,
)

from eidos_factories import (
    make_mission_state,
    make_plan,
    make_reliability_contract,
    make_task_genome,
    utc_now,
)


# --- Basic construction and field presence -------------------------------


def test_valid_construction():
    state = make_mission_state()
    assert state.status == MissionStatus.CREATED


def test_plans_and_agent_tasks_may_be_empty():
    # decisions.md D-091/D-087: empty collections are legal. A freshly
    # created mission may exist before any plan has been selected.
    tenant_id = TenantId(uuid4())
    contract = make_reliability_contract(tenant_id=tenant_id)
    genome = make_task_genome(contract=contract)
    now = utc_now()
    state = MissionState(
        tenant_id=tenant_id,
        mission_id=MissionId(uuid4()),
        execution_id=ExecutionId(uuid4()),
        created_at=now,
        updated_at=now,
        state_version=0,
        task_genome=genome,
        reliability_contract=contract,
        status=MissionStatus.CREATED,
        plans=(),
        agent_tasks=(),
        retries_used=0,
        replans_used=0,
        agent_calls_used=0,
        tool_calls_used=0,
        execution_time_used_ms=0,
        tokens_used=0,
    )
    assert state.plans == ()
    assert state.agent_tasks == ()
    assert state.active_plan_id is None


def test_tenant_id_defaults_when_omitted():
    # make_mission_state always supplies a tenant explicitly; here we build
    # directly to confirm the field itself defaults when omitted.
    contract = make_reliability_contract(tenant_id=DEFAULT_TENANT_ID)
    genome = make_task_genome(contract=contract)
    now = utc_now()
    built = MissionState(
        mission_id=MissionId(uuid4()),
        execution_id=ExecutionId(uuid4()),
        created_at=now,
        updated_at=now,
        state_version=0,
        task_genome=genome,
        reliability_contract=contract,
        status=MissionStatus.CREATED,
        plans=(),
        agent_tasks=(),
        retries_used=0,
        replans_used=0,
        agent_calls_used=0,
        tool_calls_used=0,
        execution_time_used_ms=0,
        tokens_used=0,
    )
    assert built.tenant_id == DEFAULT_TENANT_ID


def test_task_genome_is_required():
    # decisions.md D-084: a mission is created with its authoritative
    # TaskGenome. MissionStatus.CREATED does not imply the genome is absent.
    with pytest.raises(ValidationError):
        make_mission_state(task_genome=None)


def test_reliability_contract_is_required():
    # decisions.md D-100.
    with pytest.raises(ValidationError):
        make_mission_state(reliability_contract=None)


def test_execution_id_is_required():
    # decisions.md D-085.
    with pytest.raises(ValidationError):
        make_mission_state(execution_id=None)


@pytest.mark.parametrize("bad_version", [-1])
def test_state_version_negative_is_rejected(bad_version):
    with pytest.raises(ValidationError):
        make_mission_state(state_version=bad_version)


def test_state_version_zero_is_accepted():
    state = make_mission_state(state_version=0)
    assert state.state_version == 0


@pytest.mark.parametrize(
    "counter",
    [
        "retries_used",
        "replans_used",
        "agent_calls_used",
        "tool_calls_used",
        "execution_time_used_ms",
        "tokens_used",
    ],
)
def test_each_counter_rejects_negative(counter):
    with pytest.raises(ValidationError):
        make_mission_state(**{counter: -1})


@pytest.mark.parametrize(
    "counter",
    [
        "retries_used",
        "replans_used",
        "agent_calls_used",
        "tool_calls_used",
        "execution_time_used_ms",
        "tokens_used",
    ],
)
def test_each_counter_accepts_zero(counter):
    state = make_mission_state(**{counter: 0})
    assert getattr(state, counter) == 0


def test_status_reason_is_optional():
    state = make_mission_state(status=MissionStatus.PAUSED, status_reason="Maximum recovery budget exceeded")
    assert state.status_reason == "Maximum recovery budget exceeded"
    default_state = make_mission_state()
    assert default_state.status_reason is None


def test_model_is_immutable():
    state = make_mission_state()
    with pytest.raises(ValidationError):
        state.status = MissionStatus.FAILED


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        make_mission_state(unexpected_field=123)


# --- Cross-object consistency: contract reference (D-100) ----------------


def test_contract_reference_mismatch_is_rejected():
    tenant_id = TenantId(uuid4())
    contract_a = make_reliability_contract(tenant_id=tenant_id)
    contract_b = make_reliability_contract(tenant_id=tenant_id)
    genome = make_task_genome(contract=contract_a)
    with pytest.raises(ValidationError, match="D-100"):
        make_mission_state(task_genome=genome, reliability_contract=contract_b, plans=())


def test_contract_reference_match_is_accepted():
    tenant_id = TenantId(uuid4())
    contract = make_reliability_contract(tenant_id=tenant_id)
    genome = make_task_genome(contract=contract)
    state = make_mission_state(tenant_id=tenant_id, task_genome=genome, reliability_contract=contract, plans=())
    assert state.task_genome.reliability_contract_id == state.reliability_contract.contract_id


# --- Cross-object consistency: plan.mission_id (D-088) --------------------


def test_plan_with_mismatched_mission_id_is_rejected():
    tenant_id = TenantId(uuid4())
    mission_id = MissionId(uuid4())
    wrong_mission_plan = make_plan(tenant_id=tenant_id, mission_id=MissionId(uuid4()))
    contract = make_reliability_contract(tenant_id=tenant_id)
    genome = make_task_genome(contract=contract)
    with pytest.raises(ValidationError, match="D-088"):
        MissionState(
            tenant_id=tenant_id,
            mission_id=mission_id,
            execution_id=ExecutionId(uuid4()),
            created_at=utc_now(),
            updated_at=utc_now(),
            state_version=0,
            task_genome=genome,
            reliability_contract=contract,
            status=MissionStatus.CREATED,
            plans=(wrong_mission_plan,),
            agent_tasks=(),
            retries_used=0,
            replans_used=0,
            agent_calls_used=0,
            tool_calls_used=0,
            execution_time_used_ms=0,
            tokens_used=0,
        )


# --- Cross-object consistency: plan_id uniqueness --------------------------


def test_duplicate_plan_id_is_rejected():
    tenant_id = TenantId(uuid4())
    mission_id = MissionId(uuid4())
    plan_id = PlanId(uuid4())
    plan_a = make_plan(tenant_id=tenant_id, mission_id=mission_id, plan_id=plan_id, version=1)
    plan_b = make_plan(tenant_id=tenant_id, mission_id=mission_id, plan_id=plan_id, version=2)
    with pytest.raises(ValidationError, match="duplicate plan_id"):
        make_mission_state(tenant_id=tenant_id, mission_id=mission_id, plans=(plan_a, plan_b))


# --- Cross-object consistency: plan lineage (parent_plan_id resolves) -----


def test_parent_plan_id_referencing_missing_plan_is_rejected():
    tenant_id = TenantId(uuid4())
    mission_id = MissionId(uuid4())
    orphan = make_plan(
        tenant_id=tenant_id,
        mission_id=mission_id,
        version=2,
        parent_plan_id=PlanId(uuid4()),
    )
    with pytest.raises(ValidationError, match="parent_plan_id"):
        make_mission_state(tenant_id=tenant_id, mission_id=mission_id, plans=(orphan,))


def test_parent_plan_id_referencing_present_plan_is_accepted():
    tenant_id = TenantId(uuid4())
    mission_id = MissionId(uuid4())
    plan_v1 = make_plan(tenant_id=tenant_id, mission_id=mission_id, version=1)
    plan_v2 = make_plan(
        tenant_id=tenant_id,
        mission_id=mission_id,
        version=2,
        parent_plan_id=plan_v1.plan_id,
        replan_reason="insufficient evidence",
    )
    state = make_mission_state(tenant_id=tenant_id, mission_id=mission_id, plans=(plan_v1, plan_v2), active_plan_id=plan_v2.plan_id)
    assert state.plans[1].parent_plan_id == plan_v1.plan_id


# --- Cross-object consistency: active_plan_id resolves ---------------------


def test_active_plan_id_referencing_missing_plan_is_rejected():
    tenant_id = TenantId(uuid4())
    mission_id = MissionId(uuid4())
    plan = make_plan(tenant_id=tenant_id, mission_id=mission_id)
    with pytest.raises(ValidationError, match="active_plan_id"):
        make_mission_state(tenant_id=tenant_id, mission_id=mission_id, plans=(plan,), active_plan_id=PlanId(uuid4()))


def test_active_plan_id_none_is_accepted_even_with_plans_present():
    tenant_id = TenantId(uuid4())
    mission_id = MissionId(uuid4())
    plan = make_plan(tenant_id=tenant_id, mission_id=mission_id)
    state = make_mission_state(tenant_id=tenant_id, mission_id=mission_id, plans=(plan,), active_plan_id=None)
    assert state.active_plan_id is None


# --- Cross-object consistency: tenant consistency ---------------------------


def test_task_genome_tenant_mismatch_is_rejected():
    state_tenant = TenantId(uuid4())
    other_tenant = TenantId(uuid4())
    contract = make_reliability_contract(tenant_id=state_tenant)
    mismatched_genome = make_task_genome(contract=contract, tenant_id=other_tenant)
    with pytest.raises(ValidationError, match="task_genome.tenant_id"):
        make_mission_state(tenant_id=state_tenant, task_genome=mismatched_genome, reliability_contract=contract, plans=())


def test_reliability_contract_tenant_mismatch_is_rejected():
    state_tenant = TenantId(uuid4())
    other_tenant = TenantId(uuid4())
    contract = make_reliability_contract(tenant_id=other_tenant)
    genome = make_task_genome(contract=contract, tenant_id=state_tenant)
    with pytest.raises(ValidationError, match="reliability_contract.tenant_id"):
        make_mission_state(tenant_id=state_tenant, task_genome=genome, reliability_contract=contract, plans=())


def test_plan_tenant_mismatch_is_rejected():
    state_tenant = TenantId(uuid4())
    other_tenant = TenantId(uuid4())
    mission_id = MissionId(uuid4())
    mismatched_plan = make_plan(tenant_id=other_tenant, mission_id=mission_id)
    with pytest.raises(ValidationError, match="plan .*tenant_id"):
        make_mission_state(tenant_id=state_tenant, mission_id=mission_id, plans=(mismatched_plan,))
