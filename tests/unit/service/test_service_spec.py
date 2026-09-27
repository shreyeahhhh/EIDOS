"""The mission specification and its mapping onto the existing contracts (decisions.md D-232; invariant 3; V1.4-B).

A ``MissionSpec`` is explicit and structured; nothing derives a genome or a contract from anything. The mapping is one to one because the field names are the contracts' own, and the tests keep it
that way. Ceilings reject and never clamp.
"""

from uuid import UUID

import pytest
from pydantic import ValidationError

from eidos.contracts import AutonomyLevel, ReliabilityContract, RiskLevel, TaskGenome, TenantId
from eidos.service import ApiCeilings, InvalidSpec, MissionSpec, ReliabilitySpec, SuppliedDocument, provisional_system_limits
from eidos.service.spec import (
    RESERVED_REF_PREFIXES,
    contract_and_genome,
    documents_of,
    initial_state,
    spec_digest,
    validate_spec,
    without_documents,
)

from eidos_service_fixture import make_spec

TENANT = TenantId(UUID(int=0xA0A0))
CAPABILITIES = ("architecture", "cost", "research", "security")
LIMITS = provisional_system_limits()


def check(spec, **overrides):
    kwargs = dict(ceilings=ApiCeilings(), allowed_actions=frozenset({"read_documents"}), capabilities=CAPABILITIES, limits=LIMITS)
    kwargs.update(overrides)
    return validate_spec(spec, **kwargs)


def problems(spec, **overrides) -> dict[str, str]:
    with pytest.raises(InvalidSpec) as raised:
        check(spec, **overrides)
    return {item["field"]: item["message"] for item in raised.value.details}


# --- the mapping is one to one, because the names are the contracts' own ---------------------------------------------------------------


def test_a_spec_is_a_task_genome_and_a_reliability_contract_without_the_identifiers_the_server_assigns():
    assert set(MissionSpec.model_fields) - {"reliability", "supplied_documents"} == set(TaskGenome.model_fields) - {"tenant_id", "reliability_contract_id"}
    assert set(ReliabilitySpec.model_fields) == set(ReliabilityContract.model_fields) - {"tenant_id", "contract_id"}


def test_the_mapping_carries_every_field_across_unchanged_and_the_server_supplies_the_tenant_and_the_contract_id():
    spec = make_spec(
        information_dependencies=("a", "b"), allowed_actions=("read_documents",),
        reliability=ReliabilitySpec(min_quality=0.5, max_risk_level=RiskLevel.HIGH, min_independent_evidence=3, max_retries=1, max_replans=2, max_execution_time=1000),
    )
    contract_id = UUID(int=9)
    contract, genome = contract_and_genome(spec, tenant_id=TENANT, contract_id=contract_id)
    assert (genome.tenant_id, contract.tenant_id, genome.reliability_contract_id, contract.contract_id) == (TENANT, TENANT, contract_id, contract_id)
    assert (genome.goal, genome.required_capabilities, genome.information_dependencies, genome.risk_level, genome.autonomy_level, genome.allowed_actions) == (
        spec.goal, spec.required_capabilities, ("a", "b"), spec.risk_level, spec.autonomy_level, ("read_documents",))
    assert (contract.min_quality, contract.max_risk_level, contract.min_independent_evidence, contract.max_retries, contract.max_replans, contract.max_execution_time) == (0.5, "high", 3, 1, 2, 1000)
    assert (contract.max_agent_calls, contract.max_tool_calls, contract.max_tokens) == (None, None, None)  # an absent budget stays absent (D-065)


def test_a_client_cannot_supply_a_tenant_or_any_field_the_contracts_do_not_have():
    body = make_spec().model_dump_json()[:-1] + ', "tenant_id": "00000000-0000-0000-0000-0000000000a0"}'
    with pytest.raises(ValidationError):
        MissionSpec.model_validate_json(body)
    with pytest.raises(ValidationError):
        MissionSpec.model_validate_json(make_spec().model_dump_json()[:-1] + ', "confidence": 0.9}')


def test_the_reducer_builds_the_carrier_state_through_a_throwaway_log_and_a_mission_that_is_created_and_has_no_plan():
    spec = make_spec()
    contract, genome = contract_and_genome(spec, tenant_id=TENANT, contract_id=UUID(int=9))
    from datetime import datetime, timezone
    from eidos.contracts import EventId, ExecutionId, MissionId

    state = initial_state(genome, contract, tenant_id=TENANT, mission_id=MissionId(UUID(int=1)), execution_id=ExecutionId(UUID(int=2)),
                          at=datetime(2026, 1, 1, tzinfo=timezone.utc), event_id=EventId(UUID(int=3)))
    assert (state.status.value, state.plans, state.state_version, state.tenant_id) == ("created", (), 1, TENANT)
    assert state.task_genome == genome and state.reliability_contract == contract


def test_the_digest_covers_the_whole_request_and_is_the_same_for_the_same_request():
    assert spec_digest(make_spec()) == spec_digest(make_spec())
    assert spec_digest(make_spec()) != spec_digest(make_spec(goal="another goal"))
    assert spec_digest(make_spec()) != spec_digest(make_spec(supplied_documents=()))  # the documents are part of what was asked


def test_the_stored_spec_drops_the_documents_which_are_kept_as_supplied_artifacts():
    spec = make_spec()
    stored = without_documents(spec)
    assert stored.supplied_documents == () and stored.goal == spec.goal
    assert [str(a.ref) for a in documents_of(spec)] == ["doc:1", "doc:2", "doc:3"] and all(a.content_type == "text/plain" for a in documents_of(spec))


# --- ceilings reject; nothing is clamped -------------------------------------------------------------------------------------------------


def test_a_valid_spec_passes():
    check(make_spec())


def test_an_over_long_goal_is_rejected_and_the_goal_is_not_shortened():
    ceilings = ApiCeilings(max_goal_chars=10)
    found = problems(make_spec(goal="x" * 11), ceilings=ceilings)
    assert "goal" in found and "10" in found["goal"]


def test_a_blank_goal_is_rejected():
    assert "goal" in problems(make_spec(goal="   "))


@pytest.mark.parametrize("capabilities, fragment", [((), "at least one"), (("research", "research"), "more than once"), (("research", "verification"), "not served here: verification")])
def test_required_capabilities_must_be_present_distinct_and_served(capabilities, fragment):
    assert fragment in problems(make_spec(required_capabilities=capabilities))["required_capabilities"]


def test_allowed_actions_must_be_in_the_servers_allowlist_and_distinct():
    assert "not permitted" in problems(make_spec(allowed_actions=("write_files",)))["allowed_actions"]
    assert "more than once" in problems(make_spec(allowed_actions=("read_documents", "read_documents")))["allowed_actions"]
    assert "not permitted" in problems(make_spec(allowed_actions=("read_documents",)), allowed_actions=frozenset())["allowed_actions"]


def test_autonomy_above_the_ceiling_is_rejected():
    assert "autonomy_level" in problems(make_spec(autonomy_level=AutonomyLevel.REVERSIBLE))
    check(make_spec(autonomy_level=AutonomyLevel.REVERSIBLE), ceilings=ApiCeilings(max_autonomy_level=2))


@pytest.mark.parametrize("name", ["max_retries", "max_replans", "max_agent_calls", "max_tool_calls", "max_execution_time", "max_tokens"])
def test_a_budget_above_the_system_ceiling_is_rejected_never_clamped(name):
    over = getattr(LIMITS, name) + 1
    spec = make_spec(reliability=ReliabilitySpec(min_quality=0.0, max_risk_level=RiskLevel.LOW, min_independent_evidence=0, **{name: over}))
    assert f"reliability.{name}" in problems(spec)
    at_ceiling = make_spec(reliability=ReliabilitySpec(min_quality=0.0, max_risk_level=RiskLevel.LOW, min_independent_evidence=0, **{name: getattr(LIMITS, name)}))
    check(at_ceiling)  # exactly at the ceiling is fine


def test_documents_are_bounded_in_count_size_and_total():
    docs = lambda n, size: tuple(SuppliedDocument(ref=f"d{i}", content_type="text/plain", content="x" * size) for i in range(n))  # noqa: E731
    assert "supplied_documents" in problems(make_spec(supplied_documents=docs(3, 5)), ceilings=ApiCeilings(max_supplied_documents=2))
    assert "supplied_documents[0].content" in problems(make_spec(supplied_documents=docs(1, 11)), ceilings=ApiCeilings(max_document_bytes=10))
    assert "supplied_documents" in problems(make_spec(supplied_documents=docs(3, 6)), ceilings=ApiCeilings(max_total_document_bytes=17))
    check(make_spec(supplied_documents=docs(2, 6)), ceilings=ApiCeilings(max_total_document_bytes=12))


def test_the_size_of_a_document_is_its_utf8_bytes_not_its_characters():
    accents = SuppliedDocument(ref="d", content_type="text/plain", content="e" + chr(0x301) * 5)  # 6 characters, 11 bytes
    assert "supplied_documents[0].content" in problems(make_spec(supplied_documents=(accents,)), ceilings=ApiCeilings(max_document_bytes=10))


@pytest.mark.parametrize("ref", ["", " x", "a b", "a[b", "a]b", "x" * 129, "-lead", "line\nbreak"])
def test_a_document_reference_must_be_one_a_model_can_cite(ref):
    doc = SuppliedDocument(ref=ref, content_type="text/plain", content="text") if ref else None
    if doc is None:
        with pytest.raises(ValidationError):
            SuppliedDocument(ref=ref, content_type="text/plain", content="text")
        return
    assert "supplied_documents[0].ref" in problems(make_spec(supplied_documents=(doc,)))


@pytest.mark.parametrize("prefix", RESERVED_REF_PREFIXES)
def test_the_namespaces_the_runtime_writes_are_reserved(prefix):
    doc = SuppliedDocument(ref=prefix + "x", content_type="text/plain", content="text")
    assert "reserved" in problems(make_spec(supplied_documents=(doc,)))["supplied_documents[0].ref"]


def test_a_document_needs_a_supported_type_content_and_a_unique_reference():
    bad_type = SuppliedDocument(ref="a", content_type="application/pdf", content="text")
    blank = SuppliedDocument(ref="b", content_type="text/plain", content="  ")
    assert "supplied_documents[0].content_type" in problems(make_spec(supplied_documents=(bad_type,)))
    assert "supplied_documents[0].content" in problems(make_spec(supplied_documents=(blank,)))
    twice = (SuppliedDocument(ref="a", content_type="text/plain", content="one"), SuppliedDocument(ref="a", content_type="text/plain", content="two"))
    assert "supplied_documents[1].ref" in problems(make_spec(supplied_documents=twice))


def test_every_problem_is_reported_together_so_a_caller_fixes_them_in_one_pass():
    found = problems(make_spec(goal=" ", required_capabilities=(), autonomy_level=AutonomyLevel.AUTHORIZED_AUTONOMOUS))
    assert {"goal", "required_capabilities", "autonomy_level"} <= set(found)


def test_the_strict_contracts_refuse_a_wrong_type_in_the_json_and_accept_json_numbers():
    body = make_spec().model_dump_json()
    with pytest.raises(ValidationError):
        MissionSpec.model_validate_json(body.replace('"min_quality":0.0', '"min_quality":"0.5"'))
    assert MissionSpec.model_validate_json(body.replace('"min_quality":0.0', '"min_quality":1')).reliability.min_quality == 1.0  # a JSON integer is a valid float
