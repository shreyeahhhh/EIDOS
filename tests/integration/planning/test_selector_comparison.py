"""Integration: ``DeterministicSelector`` and ``ModelAssistedSelector`` compared over the identical feasible
candidate set (decisions.md D-186 to D-193; V0.8 Step 6, Part 4).

This is a factual comparison, never a ranking. ``SelectionComparison`` below is test-only reporting: it names
what each selector actually did (outcome, chosen id, whether that id is a member of the feasible set, the failure
kind if any, and the selected candidate's own ``structural_cost`` — a structural property of the ``Strategy``
itself, not a quality judgment of the choice). Nothing here declares one selector "better," computes a score, or
picks a winner; where the two selectors choose differently, that is recorded as a difference, not an error, since
no deterministic ground truth exists for "the right strategy" at this layer.
"""

from dataclasses import dataclass

from eidos.agents import ModelResponse
from eidos.planning import DeterministicSelector, SelectionOutcome, SelectionResult, select_strategy, structural_cost
from eidos.selectors import ModelAssistedSelector

from eidos_agents_factories import ScriptedModel, make_settings
from eidos_planning_factories import generate_feasible, genome_with


def respond(text: str):
    return lambda request: ModelResponse(text=text)


@dataclass(frozen=True, slots=True)
class SelectionComparison:
    """Factual properties of one selection round — no score, no rank, no "best" field (checked by
    ``test_selection_integration_boundaries.py``, not merely by convention here)."""

    selector_name: str
    outcome: SelectionOutcome
    selected_strategy_id: object | None
    selected_is_a_feasible_candidate: bool
    structural_cost: tuple[int, int] | None
    failure_reason: str | None


def describe(selector_name: str, result: SelectionResult, feasible_ids: set) -> SelectionComparison:
    return SelectionComparison(
        selector_name=selector_name,
        outcome=result.outcome,
        selected_strategy_id=result.selected.strategy_id if result.selected is not None else None,
        selected_is_a_feasible_candidate=(result.selected is not None and result.selected.strategy_id in feasible_ids),
        structural_cost=structural_cost(result.selected) if result.selected is not None else None,
        failure_reason=result.reason if result.outcome is not SelectionOutcome.SELECTED else None,
    )


def test_both_selectors_operate_over_the_identical_candidate_set():
    genome = genome_with("research", "cost", "security")
    generation = generate_feasible(genome)
    feasible_ids = {c.strategy_id for c in generation.candidates}

    deterministic_result = select_strategy(DeterministicSelector(), generation.candidates, genome)
    model = ScriptedModel(respond("[[CANDIDATE_2]]"))
    model_result = select_strategy(
        ModelAssistedSelector(model=model, settings=make_settings()), generation.candidates, genome
    )

    deterministic = describe("deterministic", deterministic_result, feasible_ids)
    model_assisted = describe("model_assisted", model_result, feasible_ids)

    for comparison in (deterministic, model_assisted):
        assert comparison.outcome is SelectionOutcome.SELECTED
        assert comparison.selected_is_a_feasible_candidate


def test_the_comparison_records_agreement_neutrally_when_both_choose_the_same_candidate():
    genome = genome_with("research", "cost", "security")
    generation = generate_feasible(genome)
    feasible_ids = {c.strategy_id for c in generation.candidates}
    cheapest_id = min(feasible_ids, key=lambda sid: structural_cost(next(c for c in generation.candidates if c.strategy_id == sid)))
    cheapest_label = f"CANDIDATE_{[c.strategy_id for c in generation.candidates].index(cheapest_id) + 1}"

    deterministic_result = select_strategy(DeterministicSelector(), generation.candidates, genome)
    model = ScriptedModel(respond(f"[[{cheapest_label}]]"))
    model_result = select_strategy(
        ModelAssistedSelector(model=model, settings=make_settings()), generation.candidates, genome
    )

    deterministic = describe("deterministic", deterministic_result, feasible_ids)
    model_assisted = describe("model_assisted", model_result, feasible_ids)

    assert deterministic.selected_strategy_id == model_assisted.selected_strategy_id
    assert deterministic.structural_cost == model_assisted.structural_cost


def test_the_comparison_records_a_difference_neutrally_when_the_selectors_choose_differently():
    genome = genome_with("research", "cost", "security")
    generation = generate_feasible(genome)
    feasible_ids = {c.strategy_id for c in generation.candidates}
    costs = {c.strategy_id: structural_cost(c) for c in generation.candidates}
    cheapest_id = min(costs, key=costs.get)
    # Script the model to name a real but deliberately different (not-cheapest) candidate.
    other_index = next(i for i, c in enumerate(generation.candidates) if c.strategy_id != cheapest_id)
    model = ScriptedModel(respond(f"[[CANDIDATE_{other_index + 1}]]"))

    deterministic_result = select_strategy(DeterministicSelector(), generation.candidates, genome)
    model_result = select_strategy(
        ModelAssistedSelector(model=model, settings=make_settings()), generation.candidates, genome
    )

    deterministic = describe("deterministic", deterministic_result, feasible_ids)
    model_assisted = describe("model_assisted", model_result, feasible_ids)

    # Both are still valid, feasible selections — a recorded difference, not a defect in either.
    assert deterministic.selected_is_a_feasible_candidate
    assert model_assisted.selected_is_a_feasible_candidate
    assert deterministic.selected_strategy_id != model_assisted.selected_strategy_id
    assert deterministic.outcome is SelectionOutcome.SELECTED
    assert model_assisted.outcome is SelectionOutcome.SELECTED


def test_the_comparison_reports_a_selector_failure_as_a_fact_not_a_missing_result():
    genome = genome_with("research", "cost")
    generation = generate_feasible(genome)
    feasible_ids = {c.strategy_id for c in generation.candidates}
    model = ScriptedModel(respond("no idea"))

    model_result = select_strategy(
        ModelAssistedSelector(model=model, settings=make_settings()), generation.candidates, genome
    )
    model_assisted = describe("model_assisted", model_result, feasible_ids)

    assert model_assisted.outcome is SelectionOutcome.SELECTOR_FAILED
    assert model_assisted.selected_strategy_id is None
    assert model_assisted.structural_cost is None
    assert model_assisted.failure_reason is not None


def test_structural_cost_is_never_presented_as_a_quality_field():
    # SelectionComparison itself carries only factual fields — pinned directly against the dataclass's own shape.
    field_names = {f for f in SelectionComparison.__dataclass_fields__}
    assert field_names & {"score", "quality", "rank", "best", "winner", "preferred"} == set()
    assert "structural_cost" in field_names  # present, but never renamed to imply a judgment
