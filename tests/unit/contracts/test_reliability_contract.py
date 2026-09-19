"""ReliabilityContract (decisions.md D-016, D-042, D-056, D-065, D-073, D-078, D-089)."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from eidos.contracts import ReliabilityContractId, RiskLevel

from eidos_factories import make_reliability_contract


def test_valid_construction_with_only_required_fields():
    contract = make_reliability_contract()
    assert contract.max_retries is None
    assert contract.max_replans is None
    assert contract.max_agent_calls is None
    assert contract.max_tool_calls is None
    assert contract.max_execution_time is None
    assert contract.max_tokens is None


def test_valid_construction_with_all_budgets_present():
    contract = make_reliability_contract(
        max_retries=2,
        max_replans=2,
        max_agent_calls=32,
        max_tool_calls=64,
        max_execution_time=600_000,
        max_tokens=10_000,
    )
    assert contract.max_execution_time == 600_000


def test_tenant_id_defaults_when_omitted():
    from eidos.contracts import DEFAULT_TENANT_ID, ReliabilityContract

    built = ReliabilityContract(
        contract_id=ReliabilityContractId(uuid4()),
        min_quality=0.9,
        max_risk_level=RiskLevel.MEDIUM,
        min_independent_evidence=3,
    )
    assert built.tenant_id == DEFAULT_TENANT_ID


@pytest.mark.parametrize("bad_value", [-0.01, 1.01, -1.0, 2.0])
def test_min_quality_outside_0_to_1_is_rejected(bad_value):
    with pytest.raises(ValidationError):
        make_reliability_contract(min_quality=bad_value)


@pytest.mark.parametrize("boundary_value", [0.0, 1.0])
def test_min_quality_boundary_values_are_accepted(boundary_value):
    contract = make_reliability_contract(min_quality=boundary_value)
    assert contract.min_quality == boundary_value


def test_min_independent_evidence_negative_is_rejected():
    with pytest.raises(ValidationError):
        make_reliability_contract(min_independent_evidence=-1)


def test_min_independent_evidence_zero_is_accepted():
    contract = make_reliability_contract(min_independent_evidence=0)
    assert contract.min_independent_evidence == 0


@pytest.mark.parametrize(
    "field",
    ["max_retries", "max_replans", "max_agent_calls", "max_tool_calls", "max_execution_time", "max_tokens"],
)
def test_each_optional_budget_field_rejects_negative(field):
    with pytest.raises(ValidationError):
        make_reliability_contract(**{field: -1})


@pytest.mark.parametrize(
    "field",
    ["max_retries", "max_replans", "max_agent_calls", "max_tool_calls", "max_execution_time", "max_tokens"],
)
def test_each_optional_budget_field_accepts_zero(field):
    contract = make_reliability_contract(**{field: 0})
    assert getattr(contract, field) == 0


def test_missing_min_quality_is_rejected():
    with pytest.raises(ValidationError):
        make_reliability_contract(min_quality=None)


def test_missing_max_risk_level_is_rejected():
    with pytest.raises(ValidationError):
        make_reliability_contract(max_risk_level=None)


def test_max_risk_level_rejects_raw_string_under_strict_mode():
    # decisions.md A6: strict validation, not silent coercion — "medium"
    # (a plain str) must not be silently accepted where a RiskLevel member
    # is required.
    with pytest.raises(ValidationError):
        make_reliability_contract(max_risk_level="medium")


def test_approval_clause_is_not_a_field():
    # decisions.md D-069: the high-risk-approval clause is not part of this
    # contract's surface at all.
    with pytest.raises(ValidationError):
        make_reliability_contract(high_risk_actions="require_human_approval")


def test_model_is_immutable():
    contract = make_reliability_contract()
    with pytest.raises(ValidationError):
        contract.min_quality = 0.5


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        make_reliability_contract(unexpected_field=123)
