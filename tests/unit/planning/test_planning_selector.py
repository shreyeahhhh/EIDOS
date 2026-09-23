"""``Selector``, ``structural_cost``, ``DeterministicSelector`` (decisions.md D-186 to D-189; V0.8 Step 2).

Orchestration (``select_strategy``) is tested separately in ``test_planning_selection.py``; these tests are about
the core selection mechanism alone: the reference implementation, and the contract types every ``Selector``
(deterministic or, later, model-assisted) must produce.
"""

import inspect

import pytest
from pydantic import ValidationError

from eidos.contracts import CapabilityId, StrategyId
from eidos.planning import (
    DeterministicSelector,
    SelectedCandidate,
    Selector,
    SelectorFailure,
    SelectorFailureKind,
    VerificationPosture,
    structural_cost,
)

from eidos_planning_factories import genome_with, make_strategy, make_strategy_id, make_strategy_stage, strategy_with_stages

GENOME = genome_with("research", "cost", "security", "architecture")
SELECTOR = DeterministicSelector()


# --- Selector protocol shape -----------------------------------------------------------------------------------


def test_selector_is_a_runtime_checkable_shaped_protocol():
    # DeterministicSelector satisfies Selector structurally: one method, select(candidates, task_genome).
    assert hasattr(Selector, "select")
    signature = inspect.signature(DeterministicSelector.select)
    assert list(signature.parameters) == ["self", "candidates", "task_genome"]


def test_deterministic_selector_implements_select():
    strategy = strategy_with_stages(1, ("research",))
    choice = SELECTOR.select((strategy,), GENOME)
    assert isinstance(choice, SelectedCandidate)


# --- SelectedCandidate ------------------------------------------------------------------------------------------


def test_selected_candidate_valid_construction():
    candidate = SelectedCandidate(strategy_id=make_strategy_id(1))
    assert candidate.strategy_id == make_strategy_id(1)


def test_selected_candidate_is_immutable():
    candidate = SelectedCandidate(strategy_id=make_strategy_id(1))
    with pytest.raises(ValidationError):
        candidate.strategy_id = make_strategy_id(2)


def test_selected_candidate_rejects_extra_fields():
    with pytest.raises(ValidationError):
        SelectedCandidate(strategy_id=make_strategy_id(1), rank=1)


def test_selected_candidate_requires_strategy_id():
    with pytest.raises(ValidationError):
        SelectedCandidate()


# --- SelectorFailureKind / SelectorFailure ------------------------------------------------------------------------


def test_selector_failure_kind_has_exactly_the_approved_three_members():
    assert {member.value for member in SelectorFailureKind} == {"unavailable", "timeout", "malformed_choice"}


def test_selector_failure_kind_is_a_narrower_vocabulary_than_model_failure_kind():
    # eidos.planning cannot import eidos.agents (a core-layer guard), so this is necessarily a separate
    # enum, not a reuse — and deliberately narrower (no EMPTY_RESPONSE analogue).
    assert len(SelectorFailureKind) == 3


def test_selector_failure_valid_construction():
    failure = SelectorFailure(kind=SelectorFailureKind.TIMEOUT, message="no answer within the deadline")
    assert failure.kind is SelectorFailureKind.TIMEOUT
    assert failure.message


def test_selector_failure_requires_a_message():
    with pytest.raises(ValidationError):
        SelectorFailure(kind=SelectorFailureKind.TIMEOUT, message="")


def test_selector_failure_rejects_an_unenumerated_kind():
    with pytest.raises(ValidationError):
        SelectorFailure(kind="network_error", message="x")


def test_selector_failure_is_immutable():
    failure = SelectorFailure(kind=SelectorFailureKind.UNAVAILABLE, message="down")
    with pytest.raises(ValidationError):
        failure.message = "changed"


def test_selector_failure_rejects_extra_fields():
    with pytest.raises(ValidationError):
        SelectorFailure(kind=SelectorFailureKind.UNAVAILABLE, message="down", retry_after=5)


# --- structural_cost: no scalar score, a tuple only -----------------------------------------------------------------


def test_structural_cost_of_an_empty_strategy_is_zero_zero():
    strategy = make_strategy(strategy_id=make_strategy_id(1), stages=(), verification=VerificationPosture.NONE)
    assert structural_cost(strategy) == (0, 0)


def test_structural_cost_of_one_stage_one_capability():
    strategy = strategy_with_stages(1, ("research",))
    assert structural_cost(strategy) == (1, 1)


def test_structural_cost_of_multiple_stages():
    strategy = strategy_with_stages(1, ("research",), ("cost",), ("security",))
    assert structural_cost(strategy) == (3, 3)


def test_structural_cost_counts_multiple_capability_occurrences_within_a_stage():
    strategy = strategy_with_stages(1, ("research", "cost", "security"))
    assert structural_cost(strategy) == (3, 1)


def test_structural_cost_orders_occurrences_before_stage_count():
    # The tuple's own field order is what makes "fewer occurrences beats more stages" true via plain
    # lexicographic tuple comparison — pinned directly, not just observed through the selector.
    assert (2, 1) < (2, 2)  # fewer stages wins a tie on occurrences
    assert (1, 5) < (2, 1)  # fewer occurrences always outranks stage count, however large
    parallel = structural_cost(strategy_with_stages(1, ("research", "cost")))
    linear = structural_cost(strategy_with_stages(2, ("research",), ("cost",)))
    assert parallel < linear


def test_structural_cost_returns_a_plain_tuple_never_a_single_number():
    cost = structural_cost(strategy_with_stages(1, ("research",)))
    assert isinstance(cost, tuple) and len(cost) == 2
    assert not isinstance(cost, (int, float))


# --- DeterministicSelector ---------------------------------------------------------------------------------------


def test_chooses_the_minimum_structural_cost_candidate():
    cheap = strategy_with_stages(1, ("research",))
    expensive = strategy_with_stages(2, ("research",), ("cost",), ("security",))
    choice = SELECTOR.select((expensive, cheap), GENOME)
    assert choice.strategy_id == cheap.strategy_id


def test_fewer_capability_occurrences_beats_more_stages():
    many_stages_fewer_caps = strategy_with_stages(1, ("research",))  # cost (1, 1)
    one_stage_more_caps = strategy_with_stages(2, ("research", "cost", "security"))  # cost (3, 1)
    choice = SELECTOR.select((one_stage_more_caps, many_stages_fewer_caps), GENOME)
    assert choice.strategy_id == many_stages_fewer_caps.strategy_id


def test_fewer_stages_breaks_an_equal_capability_count_tie():
    parallel = strategy_with_stages(1, ("research", "cost"))       # (2, 1)
    linear = strategy_with_stages(2, ("research",), ("cost",))      # (2, 2)
    choice = SELECTOR.select((linear, parallel), GENOME)
    assert choice.strategy_id == parallel.strategy_id


def test_an_exact_structural_tie_preserves_generation_order():
    first = strategy_with_stages(10, ("research",))
    second = strategy_with_stages(20, ("cost",))
    assert structural_cost(first) == structural_cost(second)

    forward = SELECTOR.select((first, second), GENOME)
    assert forward.strategy_id == first.strategy_id

    reversed_order = SELECTOR.select((second, first), GENOME)
    assert reversed_order.strategy_id == second.strategy_id  # order, not value, decided it


def test_deterministic_across_repeated_calls():
    strategies = (
        strategy_with_stages(1, ("research",), ("cost",)),
        strategy_with_stages(2, ("research", "cost")),
        strategy_with_stages(3, ("research",)),
    )
    first = SELECTOR.select(strategies, GENOME)
    second = SELECTOR.select(strategies, GENOME)
    assert first == second


def test_a_fresh_selector_instance_is_equally_deterministic():
    strategies = (strategy_with_stages(1, ("research",)), strategy_with_stages(2, ("research", "cost")))
    assert DeterministicSelector().select(strategies, GENOME) == DeterministicSelector().select(strategies, GENOME)


def test_does_not_mutate_the_candidates_tuple_or_its_contents():
    strategies = (strategy_with_stages(1, ("research",)), strategy_with_stages(2, ("research", "cost")))
    before = strategies
    SELECTOR.select(strategies, GENOME)
    assert strategies == before
    assert strategies[0].stages == (make_strategy_stage("research"),)  # untouched
