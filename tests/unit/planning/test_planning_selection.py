"""``select_strategy``, ``SelectionResult``, ``SelectionOutcome`` (decisions.md D-186 to D-189; V0.8 Step 2).

``DeterministicSelector``'s own choice logic is tested standalone in ``test_planning_selector.py``; these tests
are about the orchestration boundary itself: the zero/one-candidate edge cases, the membership-validation
enforcement point, and the ``SelectionResult`` contract. A tiny hand-written test ``Selector`` exercises the
boundary in each direction — never a fake model, since no model is involved at this step.
"""

import pytest
from pydantic import ValidationError

from eidos.contracts import StrategyId
from eidos.planning import (
    DeterministicSelector,
    SelectedCandidate,
    SelectionOutcome,
    SelectionResult,
    SelectorFailure,
    SelectorFailureKind,
    select_strategy,
)

from eidos_planning_factories import genome_with, make_strategy_id, strategy_with_stages

GENOME = genome_with("research", "cost", "security")
DETERMINISTIC = DeterministicSelector()


class _NamesFirstCandidate:
    """A trivial fake Selector: always names the first candidate it is given."""

    def select(self, candidates, task_genome):
        return SelectedCandidate(strategy_id=candidates[0].strategy_id)


class _NamesUnknownCandidate:
    """A fake Selector that hallucinates an id outside the candidate set."""

    def select(self, candidates, task_genome):
        return SelectedCandidate(strategy_id=StrategyId(make_strategy_id(999_999)))


class _AlwaysFails:
    """A fake Selector that always fails, with a fixed kind/message."""

    def __init__(self, kind=SelectorFailureKind.UNAVAILABLE, message="the selector is unavailable"):
        self._kind, self._message = kind, message

    def select(self, candidates, task_genome):
        return SelectorFailure(kind=self._kind, message=self._message)


class _RecordingSelector:
    """Records whether it was ever called — used to prove the 0/1-candidate short-circuit never calls it."""

    def __init__(self):
        self.called = False

    def select(self, candidates, task_genome):
        self.called = True
        return SelectedCandidate(strategy_id=candidates[0].strategy_id)


# --- 1. zero candidates --------------------------------------------------------------------------------------------


def test_zero_candidates_yields_no_feasible_candidates():
    result = select_strategy(DETERMINISTIC, (), GENOME)
    assert result.outcome is SelectionOutcome.NO_FEASIBLE_CANDIDATES
    assert result.selected is None
    assert result.reason


def test_zero_candidates_never_calls_the_selector():
    recorder = _RecordingSelector()
    select_strategy(recorder, (), GENOME)
    assert recorder.called is False


# --- 2. one candidate: selected directly, selector not called ------------------------------------------------------


def test_one_candidate_is_selected_directly():
    only = strategy_with_stages(1, ("research",))
    result = select_strategy(DETERMINISTIC, (only,), GENOME)
    assert result.outcome is SelectionOutcome.SELECTED
    assert result.selected is only  # the exact object, not a reconstructed copy


def test_one_candidate_never_calls_the_selector():
    only = strategy_with_stages(1, ("research",))
    recorder = _RecordingSelector()
    select_strategy(recorder, (only,), GENOME)
    assert recorder.called is False


# --- 3. multiple candidates invokes the selector --------------------------------------------------------------------


def test_multiple_candidates_invokes_the_selector():
    candidates = (strategy_with_stages(1, ("research",)), strategy_with_stages(2, ("cost",)))
    recorder = _RecordingSelector()
    select_strategy(recorder, candidates, GENOME)
    assert recorder.called is True


# --- 4/6. valid id returns the exact candidate object ------------------------------------------------------------------


def test_a_valid_id_returns_the_exact_candidate_object():
    first = strategy_with_stages(1, ("research",))
    second = strategy_with_stages(2, ("cost",))
    result = select_strategy(_NamesFirstCandidate(), (first, second), GENOME)
    assert result.outcome is SelectionOutcome.SELECTED
    assert result.selected is first  # identity, not merely equality


def test_the_deterministic_selector_end_to_end_through_the_boundary():
    cheap = strategy_with_stages(1, ("research",))
    expensive = strategy_with_stages(2, ("research",), ("cost",), ("security",))
    result = select_strategy(DETERMINISTIC, (expensive, cheap), GENOME)
    assert result.outcome is SelectionOutcome.SELECTED
    assert result.selected is cheap


# --- 5. invalid id returns INVALID_CANDIDATE_RETURNED, never substitutes ------------------------------------------------


def test_an_invalid_id_is_refused_not_substituted():
    candidates = (strategy_with_stages(1, ("research",)), strategy_with_stages(2, ("cost",)))
    result = select_strategy(_NamesUnknownCandidate(), candidates, GENOME)
    assert result.outcome is SelectionOutcome.INVALID_CANDIDATE_RETURNED
    assert result.selected is None
    assert "not in the candidate set" in result.reason


def test_an_invalid_id_never_falls_back_to_any_real_candidate():
    a = strategy_with_stages(1, ("research",))
    b = strategy_with_stages(2, ("cost",))
    result = select_strategy(_NamesUnknownCandidate(), (a, b), GENOME)
    assert result.selected is not a and result.selected is not b


# --- SelectorFailure -> SELECTOR_FAILED; message preserved; no retry, no fallback ------------------------------------------


def test_a_selector_failure_yields_selector_failed_with_the_message_preserved():
    candidates = (strategy_with_stages(1, ("research",)), strategy_with_stages(2, ("cost",)))
    result = select_strategy(_AlwaysFails(message="the model timed out"), candidates, GENOME)
    assert result.outcome is SelectionOutcome.SELECTOR_FAILED
    assert result.selected is None
    assert result.reason == "the model timed out"


def test_a_selector_failure_does_not_retry():
    class CountingFailer:
        def __init__(self):
            self.calls = 0

        def select(self, candidates, task_genome):
            self.calls += 1
            return SelectorFailure(kind=SelectorFailureKind.TIMEOUT, message="x")

    failer = CountingFailer()
    candidates = (strategy_with_stages(1, ("research",)), strategy_with_stages(2, ("cost",)))
    select_strategy(failer, candidates, GENOME)
    assert failer.calls == 1


def test_a_selector_failure_never_falls_back_to_a_deterministic_choice():
    candidates = (strategy_with_stages(1, ("research",)), strategy_with_stages(2, ("cost",)))
    result = select_strategy(_AlwaysFails(), candidates, GENOME)
    assert result.selected is None  # never silently resolved via DeterministicSelector or any other fallback


# --- duplicate StrategyIds in the candidate tuple: deterministic, not rejected, not a new architecture rule -----------


def test_duplicate_strategy_ids_in_the_candidate_set_resolve_to_the_first_match_deterministically():
    # Nothing in the approved Strategy/candidate-generation contracts enforces global uniqueness of strategy_id
    # across a tuple (D-178 onward never states this as an invariant); Python's own next()-over-a-tuple already
    # resolves this deterministically (first occurrence in iteration order), so no new rejection rule is invented
    # here — this test pins that existing, sufficient behavior rather than silently assuming it.
    duplicate_id = make_strategy_id(1)
    first = strategy_with_stages(1, ("research",))
    second = strategy_with_stages(1, ("cost",))  # same id, different content
    assert first.strategy_id == second.strategy_id == duplicate_id

    class NamesTheDuplicateId:
        def select(self, candidates, task_genome):
            return SelectedCandidate(strategy_id=duplicate_id)

    result = select_strategy(NamesTheDuplicateId(), (first, second), GENOME)
    assert result.outcome is SelectionOutcome.SELECTED
    assert result.selected is first  # the first occurrence in the tuple, deterministically


def test_duplicate_strategy_ids_are_deterministic_regardless_of_which_is_first():
    duplicate_id = make_strategy_id(1)
    first = strategy_with_stages(1, ("research",))
    second = strategy_with_stages(1, ("cost",))

    class NamesTheDuplicateId:
        def select(self, candidates, task_genome):
            return SelectedCandidate(strategy_id=duplicate_id)

    reordered = select_strategy(NamesTheDuplicateId(), (second, first), GENOME)
    assert reordered.selected is second  # still "first in the tuple as given", now second's turn to be first


# --- does not mutate the supplied candidates tuple ------------------------------------------------------------------


def test_select_strategy_does_not_mutate_candidates():
    candidates = (strategy_with_stages(1, ("research",)), strategy_with_stages(2, ("cost",)))
    before = candidates
    select_strategy(DETERMINISTIC, candidates, GENOME)
    assert candidates == before


# --- SelectionResult / SelectionOutcome contract ----------------------------------------------------------------------


def test_selection_outcome_has_exactly_the_approved_four_members():
    assert {member.value for member in SelectionOutcome} == {
        "selected", "no_feasible_candidates", "selector_failed", "invalid_candidate_returned",
    }


def test_selection_result_selected_requires_a_strategy():
    with pytest.raises(ValidationError):
        SelectionResult(outcome=SelectionOutcome.SELECTED)


def test_selection_result_selected_must_not_carry_a_reason():
    strategy = strategy_with_stages(1, ("research",))
    with pytest.raises(ValidationError):
        SelectionResult(outcome=SelectionOutcome.SELECTED, selected=strategy, reason="why not")


def test_selection_result_non_selected_outcome_requires_a_reason():
    with pytest.raises(ValidationError):
        SelectionResult(outcome=SelectionOutcome.NO_FEASIBLE_CANDIDATES)


def test_selection_result_non_selected_outcome_must_not_carry_a_strategy():
    strategy = strategy_with_stages(1, ("research",))
    with pytest.raises(ValidationError):
        SelectionResult(outcome=SelectionOutcome.NO_FEASIBLE_CANDIDATES, selected=strategy, reason="x")


def test_selection_result_is_immutable():
    strategy = strategy_with_stages(1, ("research",))
    result = SelectionResult(outcome=SelectionOutcome.SELECTED, selected=strategy)
    with pytest.raises(ValidationError):
        result.outcome = SelectionOutcome.SELECTOR_FAILED


def test_selection_result_rejects_extra_fields():
    with pytest.raises(ValidationError):
        SelectionResult(outcome=SelectionOutcome.NO_FEASIBLE_CANDIDATES, reason="x", rank=1)


def test_selection_result_carries_no_selection_id_field():
    # D-189: SelectionResult is a typed value only — no identity of its own.
    assert "selection_id" not in SelectionResult.model_fields


def test_selection_result_round_trips_through_json():
    strategy = strategy_with_stages(1, ("research",))
    result = SelectionResult(outcome=SelectionOutcome.SELECTED, selected=strategy)
    restored = SelectionResult.model_validate_json(result.model_dump_json())
    assert restored == result


# --- no ranking/scoring vocabulary anywhere --------------------------------------------------------------------------


def test_selection_result_never_names_a_best_preferred_or_winner():
    assert "best" not in SelectionResult.model_fields
    assert "preferred" not in SelectionResult.model_fields
    assert "winner" not in SelectionResult.model_fields
    assert "score" not in SelectionResult.model_fields
    assert "rank" not in SelectionResult.model_fields
