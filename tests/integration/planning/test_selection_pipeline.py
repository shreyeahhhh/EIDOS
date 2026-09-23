"""Integration: ``TaskGenome`` -> ``RuleBasedCandidateGenerator`` -> feasibility -> ``DeterministicSelector``
(decisions.md D-178 to D-189; V0.8 Step 6).

**The gap this closes.** Nothing before this step exercised ``generate_candidate_strategies`` and
``select_strategy`` together — each has its own unit suite (``tests/unit/planning/``), but always against
hand-built candidate tuples. Inspecting the contracts first: ``CandidateGenerationResult.candidates`` is already
exactly the ``tuple[Strategy, ...]`` ``select_strategy`` takes as its own second parameter — no adapter, wiring
function or new abstraction was needed to connect them; the "gap" was a missing test, not a missing component.
``generate_feasible`` (``eidos_planning_factories.py``) is a thin, test-only composition of the two already-public
functions, proving that directly.

No ``Plan`` is built or executed anywhere in this file (checked structurally by
``test_selection_integration_boundaries.py``, not merely asserted here): Strategy-to-Plan expansion does not
exist yet (D-183's own ordering decision), so this suite stops exactly at ``SelectionResult``.
"""

from eidos.planning import (
    DeterministicSelector,
    SelectionOutcome,
    select_strategy,
    structural_cost,
)

from eidos_planning_factories import GENEROUS_LIMITS, generate_feasible, genome_with


class CountingSelector:
    """Wraps a real ``Selector`` and counts how many times it was actually invoked — proves
    ``select_strategy``'s own zero/one-candidate short-circuit really means the wrapped selector is never called,
    not merely that its result looks as if it wasn't."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = 0

    def select(self, candidates, task_genome):
        self.calls += 1
        return self._inner.select(candidates, task_genome)


def run(genome, *, limits=GENEROUS_LIMITS, max_candidates=3):
    selector = CountingSelector(DeterministicSelector())
    generation = generate_feasible(genome, limits=limits, max_candidates=max_candidates)
    result = select_strategy(selector, generation.candidates, genome)
    return generation, result, selector


# --- zero / one capability: bounded candidate sets, the selector is bypassed --------------------------------------


def test_zero_capabilities_yields_one_feasible_candidate_and_bypasses_the_selector():
    generation, result, selector = run(genome_with())
    assert len(generation.candidates) == 1
    assert generation.candidates[0].stages == ()
    assert result.outcome is SelectionOutcome.SELECTED
    assert result.selected is generation.candidates[0]
    assert selector.calls == 0


def test_one_capability_yields_one_feasible_candidate_and_bypasses_the_selector():
    generation, result, selector = run(genome_with("research"))
    assert len(generation.candidates) == 1
    assert result.outcome is SelectionOutcome.SELECTED
    assert result.selected is generation.candidates[0]
    assert selector.calls == 0


# --- two independent capabilities: linear + parallel, the selector actually runs ----------------------------------


def test_two_capabilities_yield_two_feasible_candidates_and_the_selector_is_invoked():
    generation, result, selector = run(genome_with("research", "cost"))
    assert len(generation.candidates) == 2
    assert selector.calls == 1
    assert result.outcome is SelectionOutcome.SELECTED
    assert result.selected in generation.candidates


def test_two_capabilities_deterministic_selector_prefers_fewer_stages_on_an_occurrence_tie():
    generation, result, _ = run(genome_with("research", "cost"))
    # Both candidates allocate 2 occurrences total (linear: 2 stages, parallel: 1 stage) — D-188's tie-break
    # picks the 1-stage (parallel) shape, the cheaper structural_cost.
    costs = {candidate.strategy_id: structural_cost(candidate) for candidate in generation.candidates}
    assert result.selected.strategy_id == min(costs, key=costs.get)
    assert len(result.selected.stages) == 1
    assert set(result.selected.stages[0].capabilities) == {"research", "cost"}


# --- three capabilities: linear / parallel / staged all differ -----------------------------------------------------


def test_three_capabilities_yield_three_structurally_distinct_feasible_candidates():
    generation, result, selector = run(genome_with("research", "cost", "security"))
    shapes = {candidate.stages for candidate in generation.candidates}
    assert len(generation.candidates) == 3
    assert len(shapes) == 3  # linear, parallel and staged are all structurally distinct
    assert selector.calls == 1
    assert result.outcome is SelectionOutcome.SELECTED


def test_deterministic_selector_chooses_the_structurally_cheapest_of_three():
    generation, result, _ = run(genome_with("research", "cost", "security"))
    costs = {candidate.strategy_id: structural_cost(candidate) for candidate in generation.candidates}
    cheapest_id = min(costs, key=costs.get)
    assert result.selected.strategy_id == cheapest_id
    # D-188: the parallel shape (1 stage, 3 occurrences) is cheaper than staged (2 stages) or linear (3 stages).
    assert len(result.selected.stages) == 1
    assert set(result.selected.stages[0].capabilities) == {"research", "cost", "security"}


# --- constraints that reject at least one, but not every, candidate ------------------------------------------------


def test_a_tight_max_depth_rejects_the_linear_shape_but_the_selector_still_runs_over_the_rest():
    tight = GENEROUS_LIMITS.model_copy(update={"max_depth": 2})  # rules out the 3-stage linear shape only
    generation, result, selector = run(genome_with("research", "cost", "security"), limits=tight)
    assert len(generation.candidates) == 2  # parallel (1 stage) and staged (2 stages) both still fit
    assert len(generation.rejected) == 1
    rejected = generation.rejected[0]
    assert rejected.strategy.stages not in {c.stages for c in generation.candidates}
    assert not rejected.report.feasible
    assert selector.calls == 1
    assert result.outcome is SelectionOutcome.SELECTED
    assert result.selected.strategy_id in {c.strategy_id for c in generation.candidates}
    # The rejected candidate's own id never appears as a possible selection.
    assert result.selected.strategy_id != rejected.strategy.strategy_id


def test_rejected_candidates_never_reach_the_selector():
    tight = GENEROUS_LIMITS.model_copy(update={"max_depth": 2})
    generation, _, selector = run(genome_with("research", "cost", "security"), limits=tight)
    rejected_ids = {r.strategy.strategy_id for r in generation.rejected}
    feasible_ids = {c.strategy_id for c in generation.candidates}
    assert rejected_ids.isdisjoint(feasible_ids)
    assert selector.calls == 1  # only ever invoked with the already-feasible tuple


# --- constraints that reject every candidate: NO_FEASIBLE_CANDIDATES, selector never runs --------------------------


def test_max_nodes_zero_rejects_every_candidate_and_the_selector_is_never_called():
    impossible = GENEROUS_LIMITS.model_copy(update={"max_nodes": 0})
    generation, result, selector = run(genome_with("research", "cost", "security"), limits=impossible)
    assert generation.candidates == ()
    assert len(generation.rejected) == 3
    assert result.outcome is SelectionOutcome.NO_FEASIBLE_CANDIDATES
    assert result.selected is None
    assert selector.calls == 0


# --- identity and no forged reconstruction --------------------------------------------------------------------


def test_the_selected_strategy_is_the_exact_feasible_candidate_object_not_a_copy():
    generation, result, _ = run(genome_with("research", "cost"))
    assert any(result.selected is candidate for candidate in generation.candidates)


# --- Part 5: determinism / replay-safety for the deterministic path ------------------------------------------------


def test_identical_input_produces_identical_candidate_order_and_selection_across_repeated_runs():
    genome = genome_with("research", "cost", "security")
    first_generation, first_result, _ = run(genome)
    second_generation, second_result, _ = run(genome)
    assert [c.stages for c in first_generation.candidates] == [c.stages for c in second_generation.candidates]
    assert first_result.selected.stages == second_result.selected.stages
    assert first_result.selected.strategy_id == second_result.selected.strategy_id


def test_selection_result_round_trips_through_json():
    # model_validate_json, not model_validate(json.loads(...)) — strict mode (EidosModel) coerces str -> UUID/enum
    # only when validating directly from JSON text, mirroring eidos.state.records's own established round-trip.
    _, result, _ = run(genome_with("research", "cost"))
    restored = result.__class__.model_validate_json(result.model_dump_json())
    assert restored == result
