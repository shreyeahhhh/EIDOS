"""ExecutionContext (decisions.md D-113, D-123, D-139): a frozen, minimal snapshot — never MissionState.

D-139 added the frozen ReliabilityContract, so the field-set pins below changed *because the approved
specification changed*; every other assertion keeps its meaning."""

import json
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from eidos.contracts import (
    ExecutionId,
    MissionId,
    MissionState,
    PlanId,
    ReliabilityContract,
    TaskGenome,
    TenantId,
)
from eidos.runtime import ExecutionContext, context_from_state

from eidos_factories import make_mission_state, make_reliability_contract, make_task_genome
from eidos_runtime_factories import compiled_of, context_for

FIELDS = ["tenant_id", "mission_id", "execution_id", "plan_id", "plan_version", "task_genome", "reliability_contract"]
MISSION_STATE_ONLY_FIELDS = [
    "status", "status_reason", "plans", "active_plan_id", "agent_tasks",
    "retries_used", "replans_used", "agent_calls_used", "tool_calls_used",
    "execution_time_used_ms", "tokens_used", "state_version", "created_at", "updated_at",
]


def make_context(**overrides) -> ExecutionContext:
    tenant = TenantId(UUID(int=1))
    contract = make_reliability_contract(tenant_id=tenant)
    fields = dict(
        tenant_id=tenant,
        mission_id=MissionId(UUID(int=2)),
        execution_id=ExecutionId(UUID(int=3)),
        plan_id=PlanId(UUID(int=4)),
        plan_version=2,
        task_genome=make_task_genome(contract=contract),
        reliability_contract=contract,
    )
    fields.update(overrides)
    return ExecutionContext(**fields)


def state_for(compiled) -> MissionState:
    contract = make_reliability_contract(tenant_id=compiled.tenant_id)
    genome = make_task_genome(contract=contract)
    return make_mission_state(
        tenant_id=compiled.tenant_id,
        mission_id=compiled.mission_id,
        reliability_contract=contract,
        task_genome=genome,
    )


# --- construction and shape ------------------------------------------------------------------


def test_a_context_is_built_from_its_seven_fields():
    context = make_context()
    assert context.plan_version == 2
    assert isinstance(context.task_genome, TaskGenome)
    assert isinstance(context.reliability_contract, ReliabilityContract)


def test_the_context_carries_exactly_the_narrow_snapshot_fields():
    assert list(ExecutionContext.model_fields) == FIELDS


def test_the_context_has_no_mission_state_field_and_none_of_its_fields():
    for name, field in ExecutionContext.model_fields.items():
        assert field.annotation is not MissionState, name
    # The contract is the one state-owned value the context holds, and it holds it frozen (D-139).
    assert ExecutionContext.model_fields["reliability_contract"].annotation is ReliabilityContract
    for name in MISSION_STATE_ONLY_FIELDS + ["mission_state", "state"]:
        assert name not in ExecutionContext.model_fields


def test_the_serialized_context_has_none_of_the_state_only_keys():
    keys = set(json.loads(make_context().model_dump_json()))
    assert keys == set(FIELDS)
    assert not keys & set(MISSION_STATE_ONLY_FIELDS)
    # D-139 / D-041: no universal output or answer field.
    assert not keys & {"answer", "output", "result", "final_result", "outputs"}


@pytest.mark.parametrize("smuggled", ["mission_state", "state", "retries_used", "plans", "status", "answer"])
def test_state_cannot_be_smuggled_into_the_context(smuggled):
    with pytest.raises(ValidationError):
        make_context(**{smuggled: None})


def test_a_whole_mission_state_is_not_accepted_as_the_genome():
    compiled = compiled_of({"a": ""})
    with pytest.raises(ValidationError):
        make_context(task_genome=state_for(compiled))


@pytest.mark.parametrize("field", FIELDS)
def test_every_field_is_required(field):
    contract = make_reliability_contract(tenant_id=TenantId(UUID(int=1)))
    fields = dict(
        tenant_id=TenantId(UUID(int=1)), mission_id=MissionId(UUID(int=2)), execution_id=ExecutionId(UUID(int=3)),
        plan_id=PlanId(UUID(int=4)), plan_version=1, task_genome=make_task_genome(contract=contract),
        reliability_contract=contract,
    )
    del fields[field]
    with pytest.raises(ValidationError):
        ExecutionContext(**fields)


@pytest.mark.parametrize("bad", [0, -1, "1", 1.0, True, None])
def test_plan_version_is_a_strict_positive_integer(bad):
    with pytest.raises(ValidationError):
        make_context(plan_version=bad)


def test_identifiers_are_strictly_typed():
    with pytest.raises(ValidationError):
        make_context(tenant_id="not-a-uuid")
    with pytest.raises(ValidationError):
        make_context(execution_id=str(uuid4()))


def test_the_genome_must_belong_to_the_contexts_tenant():
    with pytest.raises(ValidationError, match="task_genome.tenant_id must match"):
        make_context(task_genome=make_task_genome(tenant_id=TenantId(UUID(int=99))))


def test_the_contract_must_belong_to_the_contexts_tenant():
    foreign = make_reliability_contract(tenant_id=TenantId(UUID(int=99)))
    with pytest.raises(ValidationError, match="reliability_contract.tenant_id must match"):
        make_context(reliability_contract=foreign)


def test_the_contract_must_be_the_one_the_genome_refers_to():
    tenant = TenantId(UUID(int=1))
    other = make_reliability_contract(tenant_id=tenant)  # same tenant, a different contract id
    with pytest.raises(ValidationError, match="reliability_contract_id must equal"):
        make_context(reliability_contract=other)


def test_a_missing_or_wrongly_typed_contract_is_rejected():
    for bad in (None, "contract", {"min_quality": 0.9}, 0.9):
        with pytest.raises(ValidationError):
            make_context(reliability_contract=bad)


# --- immutability -----------------------------------------------------------------------------


def test_the_context_is_frozen():
    context = make_context()
    with pytest.raises(ValidationError):
        context.plan_version = 3
    with pytest.raises(ValidationError):
        context.task_genome = make_task_genome(tenant_id=context.tenant_id)
    with pytest.raises(ValidationError):
        context.task_genome.goal = "something else"  # the nested contract is frozen too
    with pytest.raises(ValidationError):
        context.reliability_contract = make_reliability_contract(tenant_id=context.tenant_id)
    with pytest.raises(ValidationError):
        context.reliability_contract.min_quality = 0.1  # and so is the reliability contract


def test_model_copy_makes_a_new_context_and_leaves_the_original_untouched():
    context = make_context()
    before = context.model_dump_json()
    other = context.model_copy(update={"plan_version": 9})
    assert other.plan_version == 9 and context.plan_version == 2
    assert context.model_dump_json() == before


def test_equal_contexts_are_equal_hash_equally_and_serialize_identically():
    contract = make_reliability_contract(tenant_id=TenantId(UUID(int=1)))
    genome = make_task_genome(contract=contract)
    a = make_context(task_genome=genome, reliability_contract=contract)
    b = make_context(task_genome=genome, reliability_contract=contract)
    assert a == b and a is not b and hash(a) == hash(b)
    assert a.model_dump_json() == b.model_dump_json()
    assert ExecutionContext.model_validate_json(a.model_dump_json()) == a


# --- context_from_state -------------------------------------------------------------------------


def test_context_from_state_copies_identity_and_genome_and_takes_the_plan_from_the_compiled_plan():
    compiled = compiled_of({"a": ""}, version=3)
    state = state_for(compiled)
    context = context_from_state(state, compiled)
    assert context.tenant_id == state.tenant_id
    assert context.mission_id == state.mission_id
    assert context.execution_id == state.execution_id
    assert context.task_genome == state.task_genome
    assert context.reliability_contract == state.reliability_contract  # D-139
    assert context.plan_id == compiled.plan_id and context.plan_version == 3


def test_context_from_state_only_reads_the_state():
    compiled = compiled_of({"a": ""})
    state = state_for(compiled)
    before = state.model_dump_json()
    context_from_state(state, compiled)
    assert state.model_dump_json() == before


def test_the_context_built_from_state_holds_the_states_contract_but_not_the_state():
    compiled = compiled_of({"a": ""})
    state = state_for(compiled)
    context = context_from_state(state, compiled)
    assert not any(isinstance(getattr(context, name), MissionState) for name in FIELDS)
    assert context.reliability_contract == state.reliability_contract
    text = context.model_dump_json()
    assert not set(json.loads(text)) & set(MISSION_STATE_ONLY_FIELDS)
    # ...and the contract it holds is the frozen contract itself, not a MissionState field set.
    assert set(json.loads(text)["reliability_contract"]) <= set(ReliabilityContract.model_fields)


def test_context_from_state_does_not_check_the_plan_against_the_states_plans():
    # Whether the context and the compiled plan agree is the executor's precondition check,
    # not a lookup in state.plans (the runtime does not read the plan collection).
    compiled = compiled_of({"a": ""})
    state = state_for(compiled)
    assert compiled.plan_id not in {p.plan_id for p in state.plans}
    assert context_from_state(state, compiled).plan_id == compiled.plan_id


def test_a_state_of_another_mission_gives_a_context_that_disagrees_with_the_compiled_plan():
    compiled = compiled_of({"a": ""})
    foreign = make_mission_state()  # its own tenant and mission
    context = context_from_state(foreign, compiled)
    assert context.mission_id != compiled.mission_id  # the executor will reject this


def test_context_for_helper_builds_a_matching_context():
    compiled = compiled_of({"a": ""})
    context = context_for(compiled)
    assert (context.tenant_id, context.mission_id, context.plan_id, context.plan_version) == (
        compiled.tenant_id, compiled.mission_id, compiled.plan_id, compiled.plan_version,
    )
