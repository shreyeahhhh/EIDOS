"""``check_feasibility`` — the deterministic feasibility gate, standalone (decisions.md D-178 to D-182; V0.7 Step 4).

Pipeline integration (how ``generate_candidate_strategies`` uses this) is tested in ``test_planning_pipeline.py``;
these tests are about ``check_feasibility`` itself, called directly against hand-built ``Strategy`` instances.
"""

import pytest
from pydantic import ValidationError

from eidos.contracts import CapabilityId
from eidos.planning import (
    FeasibilityCheck,
    FeasibilityReport,
    FeasibilityViolation,
    FeasibilityViolationCode,
    Strategy,
    VerificationPosture,
    check_feasibility,
)
from eidos.validation.limits import LimitName

from eidos_planning_factories import GENEROUS_CONTRACT, GENEROUS_LIMITS, genome_with, make_strategy, make_strategy_stage

CHECK = check_feasibility


def strategy_with(*stage_capabilities: tuple, verification=VerificationPosture.FINAL) -> Strategy:
    stages = tuple(make_strategy_stage(*caps) for caps in stage_capabilities)
    return make_strategy(stages=stages, verification=verification, rationale="test")


def genome_requiring(*capabilities: str):
    return genome_with(*capabilities)


# --- 1. valid strategy -> feasible -----------------------------------------------------------------------------------


def test_a_valid_strategy_within_every_limit_is_feasible():
    strategy = strategy_with(("research",), ("cost",))
    report = CHECK(strategy, genome_requiring("research", "cost"), GENEROUS_CONTRACT, GENEROUS_LIMITS)
    assert report.feasible
    assert report.violations == ()


# --- 2. unknown capability -> rejected -------------------------------------------------------------------------------


def test_a_capability_outside_required_capabilities_is_rejected():
    strategy = strategy_with(("research",), ("cost",))
    report = CHECK(strategy, genome_requiring("research"), GENEROUS_CONTRACT, GENEROUS_LIMITS)
    assert not report.feasible
    violation = report.violations[0]
    assert violation.code is FeasibilityViolationCode.CAPABILITY_NOT_AVAILABLE
    assert violation.check is FeasibilityCheck.CAPABILITY
    assert violation.capability == CapabilityId("cost")
    assert violation.stage_index == 1


def test_every_occurrence_of_an_unavailable_capability_is_reported_not_deduplicated():
    strategy = strategy_with(("cost",), ("cost",))
    report = CHECK(strategy, genome_requiring("research"), GENEROUS_CONTRACT, GENEROUS_LIMITS)
    codes = [v.code for v in report.violations]
    assert codes == [FeasibilityViolationCode.CAPABILITY_NOT_AVAILABLE, FeasibilityViolationCode.CAPABILITY_NOT_AVAILABLE]
    assert [v.stage_index for v in report.violations] == [0, 1]


# --- 9. required capabilities not all being present -> still allowed -------------------------------------------------


def test_a_strategy_using_only_some_of_the_required_capabilities_is_still_feasible():
    # The converse is not required (D-179's own asymmetry, matching check_capabilities for Plan).
    strategy = strategy_with(("research",))
    report = CHECK(strategy, genome_requiring("research", "cost", "security"), GENEROUS_CONTRACT, GENEROUS_LIMITS)
    assert report.feasible


# --- 3. max_depth exceeded --------------------------------------------------------------------------------------------


def test_more_stages_than_max_depth_is_rejected():
    limits = GENEROUS_LIMITS.model_copy(update={"max_depth": 1})
    strategy = strategy_with(("research",), ("cost",))
    report = CHECK(strategy, genome_requiring("research", "cost"), GENEROUS_CONTRACT, limits)
    assert not report.feasible
    violation = next(v for v in report.violations if v.code is FeasibilityViolationCode.MAX_DEPTH_EXCEEDED)
    assert violation.check is FeasibilityCheck.COMPLEXITY
    assert violation.limit_name is LimitName.MAX_DEPTH
    assert violation.limit_value == 1
    assert violation.observed_value == 2


def test_exactly_max_depth_stages_is_feasible():
    limits = GENEROUS_LIMITS.model_copy(update={"max_depth": 2})
    strategy = strategy_with(("research",), ("cost",))
    report = CHECK(strategy, genome_requiring("research", "cost"), GENEROUS_CONTRACT, limits)
    assert report.feasible


# --- 4. max_parallel_branches exceeded ----------------------------------------------------------------------------------


def test_a_wider_stage_than_max_parallel_branches_is_rejected():
    limits = GENEROUS_LIMITS.model_copy(update={"max_parallel_branches": 2})
    strategy = strategy_with(("research", "cost", "security"))
    report = CHECK(strategy, genome_requiring("research", "cost", "security"), GENEROUS_CONTRACT, limits)
    assert not report.feasible
    violation = next(v for v in report.violations if v.code is FeasibilityViolationCode.MAX_PARALLEL_BRANCHES_EXCEEDED)
    assert violation.limit_value == 2
    assert violation.observed_value == 3


def test_the_widest_stage_is_the_one_measured_not_the_average():
    limits = GENEROUS_LIMITS.model_copy(update={"max_parallel_branches": 2})
    strategy = strategy_with(("research",), ("cost", "security"))  # widest stage is 2, not 1.5
    report = CHECK(strategy, genome_requiring("research", "cost", "security"), GENEROUS_CONTRACT, limits)
    assert report.feasible


# --- 5. max_nodes exceeded ------------------------------------------------------------------------------------------------


def test_more_total_capability_occurrences_than_max_nodes_is_rejected():
    limits = GENEROUS_LIMITS.model_copy(update={"max_nodes": 2})
    strategy = strategy_with(("research",), ("cost",), ("security",))
    report = CHECK(strategy, genome_requiring("research", "cost", "security"), GENEROUS_CONTRACT, limits)
    assert not report.feasible
    violation = next(v for v in report.violations if v.code is FeasibilityViolationCode.MAX_NODES_EXCEEDED)
    assert violation.limit_value == 2
    assert violation.observed_value == 3


def test_max_nodes_counts_capability_occurrences_not_stage_count():
    # 2 stages, 3 total capability occurrences (one stage holds 2 in parallel) — must be measured by
    # occurrences, not by how many stages there are, which would coincidentally be smaller here.
    limits = GENEROUS_LIMITS.model_copy(update={"max_nodes": 2})
    strategy = strategy_with(("research",), ("cost", "security"))
    report = CHECK(strategy, genome_requiring("research", "cost", "security"), GENEROUS_CONTRACT, limits)
    assert not report.feasible
    violation = next(v for v in report.violations if v.code is FeasibilityViolationCode.MAX_NODES_EXCEEDED)
    assert violation.observed_value == 3


def test_verification_is_not_counted_toward_max_nodes():
    # A strategy-level estimate only; the real compiled VERIFY node is counted for real, later, by the
    # unmodified V0.2/V0.3 pipeline once a selected strategy expands into a concrete Plan.
    limits = GENEROUS_LIMITS.model_copy(update={"max_nodes": 1})
    strategy = strategy_with(("research",), verification=VerificationPosture.FINAL)
    report = CHECK(strategy, genome_requiring("research"), GENEROUS_CONTRACT, limits)
    assert report.feasible


# --- 6. effective max_agent_calls exceeded ----------------------------------------------------------------------------


def test_more_capability_occurrences_than_the_contracts_own_max_agent_calls_is_rejected():
    contract = GENEROUS_CONTRACT.model_copy(update={"max_agent_calls": 2})
    strategy = strategy_with(("research",), ("cost",), ("security",))
    report = CHECK(strategy, genome_requiring("research", "cost", "security"), contract, GENEROUS_LIMITS)
    assert not report.feasible
    violation = next(v for v in report.violations if v.code is FeasibilityViolationCode.AGENT_CALLS_EXCEEDED)
    assert violation.check is FeasibilityCheck.RESOURCE
    assert violation.limit_value == 2  # the contract's own tighter value, not the system ceiling
    assert violation.observed_value == 3


def test_the_effective_limit_is_the_tighter_of_system_ceiling_and_contract_value():
    # min(system ceiling, contract value) — the identical formula check_resources already uses for Plan.
    tight_system = GENEROUS_LIMITS.model_copy(update={"max_agent_calls": 2})
    loose_contract = GENEROUS_CONTRACT.model_copy(update={"max_agent_calls": 100})
    strategy = strategy_with(("research",), ("cost",), ("security",))
    report = CHECK(strategy, genome_requiring("research", "cost", "security"), loose_contract, tight_system)
    assert not report.feasible
    violation = next(v for v in report.violations if v.code is FeasibilityViolationCode.AGENT_CALLS_EXCEEDED)
    assert violation.limit_value == 2  # the system ceiling won, not the looser contract value


def test_exactly_the_effective_max_agent_calls_is_feasible():
    contract = GENEROUS_CONTRACT.model_copy(update={"max_agent_calls": 3})
    strategy = strategy_with(("research",), ("cost",), ("security",))
    report = CHECK(strategy, genome_requiring("research", "cost", "security"), contract, GENEROUS_LIMITS)
    assert report.feasible


def test_an_unset_contract_max_agent_calls_falls_back_to_the_system_ceiling_alone():
    contract = GENEROUS_CONTRACT.model_copy(update={"max_agent_calls": None})
    limits = GENEROUS_LIMITS.model_copy(update={"max_agent_calls": 2})
    strategy = strategy_with(("research",), ("cost",), ("security",))
    report = CHECK(strategy, genome_requiring("research", "cost", "security"), contract, limits)
    violation = next(v for v in report.violations if v.code is FeasibilityViolationCode.AGENT_CALLS_EXCEEDED)
    assert violation.limit_value == 2


# --- 7. multiple simultaneous violations ------------------------------------------------------------------------------


def test_multiple_simultaneous_violations_are_all_reported_not_only_the_first():
    limits = GENEROUS_LIMITS.model_copy(update={"max_depth": 1, "max_parallel_branches": 1, "max_nodes": 1})
    strategy = strategy_with(("research",), ("cost", "architecture"))  # unavailable: architecture
    report = CHECK(strategy, genome_requiring("research", "cost"), GENEROUS_CONTRACT, limits)
    codes = {v.code for v in report.violations}
    assert FeasibilityViolationCode.CAPABILITY_NOT_AVAILABLE in codes
    assert FeasibilityViolationCode.MAX_DEPTH_EXCEEDED in codes
    assert FeasibilityViolationCode.MAX_PARALLEL_BRANCHES_EXCEEDED in codes
    assert FeasibilityViolationCode.MAX_NODES_EXCEEDED in codes


# --- 8. zero/empty strategy behavior --------------------------------------------------------------------------------


def test_an_empty_strategy_with_no_stages_is_feasible():
    strategy = make_strategy(stages=(), verification=VerificationPosture.NONE)
    report = CHECK(strategy, genome_requiring(), GENEROUS_CONTRACT, GENEROUS_LIMITS)
    assert report.feasible


def test_an_empty_strategy_is_feasible_even_against_a_zero_max_nodes_ceiling():
    limits = GENEROUS_LIMITS.model_copy(update={"max_nodes": 0, "max_depth": 0, "max_parallel_branches": 0})
    strategy = make_strategy(stages=(), verification=VerificationPosture.NONE)
    report = CHECK(strategy, genome_requiring(), GENEROUS_CONTRACT, limits)
    assert report.feasible


# --- 10. deterministic report ordering ----------------------------------------------------------------------------------


def test_violations_are_reported_in_a_fixed_deterministic_order():
    limits = GENEROUS_LIMITS.model_copy(update={"max_depth": 1, "max_parallel_branches": 1, "max_nodes": 1})
    strategy = strategy_with(("research",), ("cost", "architecture"))
    first = CHECK(strategy, genome_requiring("research", "cost"), GENEROUS_CONTRACT, limits)
    second = CHECK(strategy, genome_requiring("research", "cost"), GENEROUS_CONTRACT, limits)
    assert first == second
    assert [v.code for v in first.violations] == [v.code for v in second.violations]


# --- 11. no exception for ordinary infeasibility ------------------------------------------------------------------------


def test_ordinary_infeasibility_never_raises():
    limits = GENEROUS_LIMITS.model_copy(update={"max_nodes": 0})
    strategy = strategy_with(("research",))
    report = CHECK(strategy, genome_requiring("research"), GENEROUS_CONTRACT, limits)  # must not raise
    assert not report.feasible


# --- 12. malformed strategy input follows existing contract behavior -----------------------------------------------------


def test_a_non_strategy_input_fails_the_same_way_an_existing_v02_stage_function_would():
    # check_feasibility trusts its argument is an already-validated Strategy, matching check_capabilities(plan, ...)'s
    # own convention: neither re-validates the type of what it is handed.
    with pytest.raises(AttributeError):
        CHECK(None, genome_requiring("research"), GENEROUS_CONTRACT, GENEROUS_LIMITS)


# --- typed violations, never a bare bool -----------------------------------------------------------------------------------


def test_report_is_not_a_bare_bool():
    strategy = strategy_with(("research",))
    report = CHECK(strategy, genome_requiring("research"), GENEROUS_CONTRACT, GENEROUS_LIMITS)
    assert isinstance(report, FeasibilityReport)
    assert not isinstance(report, bool)


def test_a_violation_with_a_mismatched_check_and_code_is_unconstructible():
    with pytest.raises(ValidationError):
        FeasibilityViolation(
            check=FeasibilityCheck.RESOURCE, code=FeasibilityViolationCode.CAPABILITY_NOT_AVAILABLE,
            message="x", stage_index=0, capability=CapabilityId("research"),
        )


def test_a_limit_violation_without_its_limit_fields_is_unconstructible():
    with pytest.raises(ValidationError):
        FeasibilityViolation(check=FeasibilityCheck.COMPLEXITY, code=FeasibilityViolationCode.MAX_DEPTH_EXCEEDED, message="x")


def test_a_capability_violation_carrying_limit_fields_is_unconstructible():
    with pytest.raises(ValidationError):
        FeasibilityViolation(
            check=FeasibilityCheck.CAPABILITY, code=FeasibilityViolationCode.CAPABILITY_NOT_AVAILABLE,
            message="x", stage_index=0, capability=CapabilityId("research"),
            limit_name=LimitName.MAX_NODES, limit_value=1, observed_value=2,
        )
