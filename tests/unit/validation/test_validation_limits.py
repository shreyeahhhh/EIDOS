"""SystemLimits and LimitName (decisions.md D-009, D-042, D-078, D-103, D-104)."""

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticUndefined

from eidos.contracts import ReliabilityContract
from eidos.validation.limits import (
    MISSION_BUDGETS,
    SHAPE_LIMITS,
    LimitName,
    SystemLimits,
)

from eidos_validation_factories import FIXTURE_LIMIT_VALUES, make_system_limits

ALL_FIELDS = sorted(FIXTURE_LIMIT_VALUES)


# --- D-103: no built-in numeric defaults ----------------------------------


def test_system_limits_cannot_be_constructed_without_arguments():
    with pytest.raises(ValidationError) as exc_info:
        SystemLimits()
    assert {e["type"] for e in exc_info.value.errors()} == {"missing"}
    assert len(exc_info.value.errors()) == len(ALL_FIELDS)


def test_every_field_is_required_and_has_no_default():
    for name, field in SystemLimits.model_fields.items():
        assert field.is_required(), f"{name} has a default; D-103 forbids any"
        assert field.default is PydanticUndefined


@pytest.mark.parametrize("omitted", ALL_FIELDS)
def test_omitting_any_single_field_is_rejected(omitted):
    fields = {k: v for k, v in FIXTURE_LIMIT_VALUES.items() if k != omitted}
    with pytest.raises(ValidationError) as exc_info:
        SystemLimits(**fields)
    (error,) = exc_info.value.errors()
    assert error["type"] == "missing"
    assert error["loc"] == (omitted,)


def test_fixture_values_are_not_the_handoff_illustrative_numbers():
    # D-103 point 5: the handoff's example numbers are not shipped as defaults,
    # and the labelled fixtures do not quietly reintroduce them.
    assert 600_000 not in FIXTURE_LIMIT_VALUES.values()
    assert 10_000 not in FIXTURE_LIMIT_VALUES.values()


# --- contract discipline --------------------------------------------------


def test_valid_construction_round_trips_every_value():
    limits = make_system_limits()
    for name, value in FIXTURE_LIMIT_VALUES.items():
        assert getattr(limits, name) == value


def test_zero_is_a_legal_limit_and_is_not_treated_as_unset():
    limits = make_system_limits(max_nodes=0, max_tokens=0)
    assert limits.max_nodes == 0
    assert limits.max_tokens == 0


@pytest.mark.parametrize("field", ALL_FIELDS)
def test_negative_values_are_rejected(field):
    with pytest.raises(ValidationError):
        make_system_limits(**{field: -1})


@pytest.mark.parametrize("bad", ["5", 5.0, 5.5, True, None])
def test_non_integer_values_are_rejected_strictly(bad):
    with pytest.raises(ValidationError):
        make_system_limits(max_nodes=bad)


def test_limits_are_immutable():
    limits = make_system_limits()
    with pytest.raises(ValidationError):
        limits.max_nodes = 1


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        make_system_limits(max_widgets=3)


# --- LimitName and its groupings ------------------------------------------


def test_limit_names_are_exactly_the_system_limits_fields():
    # Drift guard: a new field on SystemLimits without a LimitName (or vice
    # versa) would let a limit escape reporting.
    assert {n.value for n in LimitName} == set(SystemLimits.model_fields)


def test_shape_limits_and_budgets_partition_the_limit_names():
    assert set(SHAPE_LIMITS) | set(MISSION_BUDGETS) == set(LimitName)
    assert set(SHAPE_LIMITS) & set(MISSION_BUDGETS) == set()
    assert len(SHAPE_LIMITS) == 3
    assert len(MISSION_BUDGETS) == 6


def test_mission_budgets_are_exactly_the_reliability_contract_budget_fields():
    contract_budgets = {
        name
        for name in ReliabilityContract.model_fields
        if name.startswith("max_") and name != "max_risk_level"
    }
    assert {b.value for b in MISSION_BUDGETS} == contract_budgets


def test_shape_limits_are_not_reliability_contract_fields():
    # D-009: shape limits are system-only.
    for name in SHAPE_LIMITS:
        assert name.value not in ReliabilityContract.model_fields


def test_budget_and_limit_orders_are_fixed():
    # Violation order in reports derives from these tuples.
    assert [n.value for n in MISSION_BUDGETS] == [
        "max_retries",
        "max_replans",
        "max_agent_calls",
        "max_tool_calls",
        "max_execution_time",
        "max_tokens",
    ]
    assert [n.value for n in SHAPE_LIMITS] == [
        "max_nodes",
        "max_depth",
        "max_parallel_branches",
    ]


@pytest.mark.parametrize("name", list(LimitName))
def test_ceiling_returns_the_named_field(name):
    assert make_system_limits().ceiling(name) == FIXTURE_LIMIT_VALUES[name.value]
