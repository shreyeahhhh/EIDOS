"""``generate_candidate_strategies`` — dedup, identity injection, feasibility filtering and capping (decisions.md
D-178 to D-182; V0.7 Steps 3 and 4). The reference generator's own raw shapes are tested in
``test_planning_generator.py``; ``check_feasibility`` itself is tested standalone in
``test_planning_feasibility.py``; these tests are about the orchestration boundary around any
``CandidateGenerator``, including a deliberately broken fake one (item 14 of the Step 3 instructions, reused here
for the feasibility gate).
"""

from uuid import UUID

import pytest
from pydantic import ValidationError

from eidos.contracts import CapabilityId
from eidos.planning import (
    CandidateGenerationResult,
    RejectedCandidate,
    RuleBasedCandidateGenerator,
    Strategy,
    StrategyShape,
    StrategyStage,
    VerificationPosture,
    generate_candidate_strategies,
)

from eidos_planning_factories import (
    GENEROUS_CONTRACT,
    GENEROUS_LIMITS,
    MISSION,
    FixedStrategyIdSource,
    genome_with,
    make_strategy_id,
)

GENERATOR = RuleBasedCandidateGenerator()


def run(genome, *, max_candidates: int, ids=None, generator=GENERATOR, contract=GENEROUS_CONTRACT, limits=GENEROUS_LIMITS):
    return generate_candidate_strategies(
        generator, genome, mission_id=MISSION, reliability_contract=contract, limits=limits,
        max_candidates=max_candidates, ids=ids or FixedStrategyIdSource(),
    )


# --- explicit max_candidates / fewer available than max_candidates -------------------------------------------------


def test_max_candidates_caps_the_result():
    result = run(genome_with("research", "cost", "security"), max_candidates=2)
    assert len(result.candidates) == 2


def test_fewer_available_shapes_than_max_candidates_returns_all_of_them_untruncated():
    result = run(genome_with("research"), max_candidates=3)
    assert len(result.candidates) == 1
    assert result.truncated == 0


def test_max_candidates_zero_returns_no_candidates():
    result = run(genome_with("research", "cost", "security"), max_candidates=0)
    assert result.candidates == ()
    assert result.truncated == 3


def test_max_candidates_is_required_with_no_default():
    import inspect

    signature = inspect.signature(generate_candidate_strategies)
    assert signature.parameters["max_candidates"].default is inspect.Parameter.empty


def test_a_negative_max_candidates_is_rejected_not_silently_misinterpreted():
    with pytest.raises(ValueError):
        run(genome_with("research", "cost"), max_candidates=-1)


# --- truncation behavior is deterministic and observable, only over the FEASIBLE pool -------------------------------


def test_truncated_count_is_exactly_what_the_cap_removed():
    result = run(genome_with("research", "cost", "security"), max_candidates=1)
    assert len(result.candidates) == 1
    assert result.truncated == 2  # 3 feasible shapes, 1 kept


def test_truncation_is_deterministic_across_repeated_calls():
    first = run(genome_with("research", "cost", "security"), max_candidates=2)
    second = run(genome_with("research", "cost", "security"), max_candidates=2)
    assert first.truncated == second.truncated
    assert len(first.candidates) == len(second.candidates)


def test_the_generator_never_pads_to_reach_max_candidates():
    result = run(genome_with("research"), max_candidates=3)
    assert len(result.candidates) == 1


def test_truncated_is_computed_from_the_feasible_pool_not_from_every_stamped_candidate():
    # 3 stamped, 1 rejected as infeasible, 2 feasible, capped at 1: truncated must be 2 - 1 = 1, not 3 - 1 = 2.
    tight = GENEROUS_LIMITS.model_copy(update={"max_parallel_branches": 2})  # rules out the 3-wide parallel shape
    result = run(genome_with("research", "cost", "security"), max_candidates=1, limits=tight)
    assert len(result.candidates) == 1
    assert len(result.rejected) == 1
    assert result.truncated == 1


def test_max_candidates_behavior_stays_deterministic_after_feasibility_filtering():
    # An infeasible candidate never occupies a slot: with one of three shapes infeasible, max_candidates=2
    # is satisfied entirely from the remaining two feasible ones, deterministically.
    tight = GENEROUS_LIMITS.model_copy(update={"max_parallel_branches": 2})  # rules out the 3-wide parallel shape
    result = run(genome_with("research", "cost", "security"), max_candidates=2, limits=tight)
    assert len(result.candidates) == 2
    assert len(result.rejected) == 1
    assert result.rejected[0].report.violations[0].code.value == "max_parallel_branches_exceeded"


# --- deduplication (structural, deterministic) ----------------------------------------------------------------------


class _RepeatingGenerator:
    """A fake CandidateGenerator that deliberately emits the same shape twice, with different rationale text."""

    def generate(self, task_genome):
        stage = StrategyStage(capabilities=(CapabilityId("research"),))
        return (
            StrategyShape(stages=(stage,), verification=VerificationPosture.FINAL, rationale="first wording"),
            StrategyShape(stages=(stage,), verification=VerificationPosture.FINAL, rationale="second wording"),
        )


def test_structurally_identical_shapes_from_the_generator_are_deduplicated():
    result = run(genome_with("research"), max_candidates=5, generator=_RepeatingGenerator())
    assert len(result.candidates) == 1


def test_deduplication_keeps_the_first_occurrences_rationale():
    result = run(genome_with("research"), max_candidates=5, generator=_RepeatingGenerator())
    assert result.candidates[0].rationale == "first wording"


class _SameTopologyDifferentVerificationGenerator:
    """Same stages, different verification posture — D-179's own third dimension, so these are NOT duplicates."""

    def generate(self, task_genome):
        stage = StrategyStage(capabilities=(CapabilityId("research"),))
        return (
            StrategyShape(stages=(stage,), verification=VerificationPosture.FINAL, rationale="verified"),
            StrategyShape(stages=(stage,), verification=VerificationPosture.NONE, rationale="unverified"),
        )


def test_the_same_topology_with_a_different_verification_posture_is_not_deduplicated_away():
    result = run(genome_with("research"), max_candidates=5, generator=_SameTopologyDifferentVerificationGenerator())
    assert len(result.candidates) == 2
    assert {c.verification for c in result.candidates} == {VerificationPosture.FINAL, VerificationPosture.NONE}


# --- identity injection ---------------------------------------------------------------------------------------------


def test_each_candidate_gets_a_distinct_strategy_id_from_the_injected_source():
    result = run(genome_with("research", "cost", "security"), max_candidates=3)
    ids = [candidate.strategy_id for candidate in result.candidates]
    assert len(ids) == len(set(ids))


def test_strategy_ids_are_drawn_in_generation_order_from_the_injected_source():
    result = run(genome_with("research", "cost"), max_candidates=2, ids=FixedStrategyIdSource(start=1))
    assert [c.strategy_id for c in result.candidates] == [make_strategy_id(1), make_strategy_id(2)]


def test_a_different_id_source_produces_different_ids_for_the_same_shapes():
    a = run(genome_with("research"), max_candidates=1, ids=FixedStrategyIdSource(start=1))
    b = run(genome_with("research"), max_candidates=1, ids=FixedStrategyIdSource(start=50))
    assert a.candidates[0].strategy_id != b.candidates[0].strategy_id
    assert a.candidates[0].stages == b.candidates[0].stages  # identity differs; content does not


def test_mission_id_and_tenant_id_are_stamped_from_the_callers_own_context():
    genome = genome_with("research")
    result = run(genome, max_candidates=1)
    assert result.candidates[0].mission_id == MISSION
    assert result.candidates[0].tenant_id == genome.tenant_id


def test_rejected_candidates_are_also_identity_stamped():
    # Identity is stable whether or not a candidate turns out feasible (module docstring).
    tight = GENEROUS_LIMITS.model_copy(update={"max_nodes": 0})
    result = run(genome_with("research"), max_candidates=5, limits=tight)
    assert result.candidates == ()
    assert len(result.rejected) == 1
    assert isinstance(result.rejected[0].strategy.strategy_id, UUID)


def test_the_generator_itself_never_assigns_identity():
    shape = GENERATOR.generate(genome_with("research"))[0]
    assert "strategy_id" not in type(shape).model_fields
    assert "mission_id" not in type(shape).model_fields


# --- feasibility integration: a malformed/misbehaving generator cannot bypass the gate -------------------------------


class _MisbehavingGenerator:
    """A fake CandidateGenerator that names a capability the mission never required — never trusted blindly."""

    def generate(self, task_genome):
        return (
            StrategyShape(
                stages=(StrategyStage(capabilities=(CapabilityId("research"), CapabilityId("cost"))),),
                verification=VerificationPosture.FINAL,
                rationale="names a capability outside required_capabilities",
            ),
        )


def test_a_shape_naming_an_unavailable_capability_is_rejected_not_silently_included():
    result = run(genome_with("research"), max_candidates=5, generator=_MisbehavingGenerator())
    assert result.candidates == ()
    assert len(result.rejected) == 1
    assert result.rejected[0].report.violations[0].code.value == "capability_not_available"


def test_a_rejected_shape_is_reported_not_raised():
    # Governance never depends on the generator behaving; an untrusted generator's mistake is reported, not fatal.
    result = run(genome_with("research"), max_candidates=5, generator=_MisbehavingGenerator())
    assert result.rejected[0].strategy.stages[0].capabilities == (CapabilityId("research"), CapabilityId("cost"))


class _PartlyMisbehavingGenerator:
    """One valid shape, one invalid shape: only the invalid one is rejected."""

    def generate(self, task_genome):
        return (
            StrategyShape(
                stages=(StrategyStage(capabilities=(CapabilityId("research"),)),),
                verification=VerificationPosture.FINAL, rationale="valid",
            ),
            StrategyShape(
                stages=(StrategyStage(capabilities=(CapabilityId("architecture"),)),),
                verification=VerificationPosture.FINAL, rationale="invalid: architecture was never required",
            ),
        )


def test_a_valid_shape_is_kept_even_when_a_sibling_shape_from_the_same_generator_is_rejected():
    result = run(genome_with("research"), max_candidates=5, generator=_PartlyMisbehavingGenerator())
    assert len(result.candidates) == 1
    assert len(result.rejected) == 1
    assert result.candidates[0].stages[0].capabilities == (CapabilityId("research"),)


def test_the_reference_generators_own_shapes_are_never_changed_merely_to_pass_feasibility():
    # The generator proposes; the feasibility layer filters. Tightening limits must never silently reshape
    # what RuleBasedCandidateGenerator itself produces — it only changes which shapes survive the gate.
    loose_shapes = GENERATOR.generate(genome_with("research", "cost", "security"))
    tight = GENEROUS_LIMITS.model_copy(update={"max_nodes": 1})
    run(genome_with("research", "cost", "security"), max_candidates=5, limits=tight)
    still_loose_shapes = GENERATOR.generate(genome_with("research", "cost", "security"))
    assert loose_shapes == still_loose_shapes


# --- typed field constraints on the result models -------------------------------------------------------------------


def test_candidate_generation_result_rejects_a_negative_truncated_count():
    with pytest.raises(ValidationError):
        CandidateGenerationResult(candidates=(), truncated=-1)


def test_rejected_candidate_requires_a_feasibility_report():
    from eidos_planning_factories import make_strategy

    strategy = make_strategy()
    with pytest.raises(ValidationError):
        RejectedCandidate(strategy=strategy)


# --- integration with the existing Strategy contract ------------------------------------------------------------------


def test_every_candidate_is_a_fully_valid_strategy_instance():
    result = run(genome_with("research", "cost"), max_candidates=2)
    for candidate in result.candidates:
        assert isinstance(candidate, Strategy)
        assert isinstance(candidate.strategy_id, UUID)
        assert candidate.rationale


def test_candidates_round_trip_through_json_like_any_other_strategy():
    result = run(genome_with("research", "cost"), max_candidates=2)
    for candidate in result.candidates:
        assert Strategy.model_validate_json(candidate.model_dump_json()) == candidate


def test_no_candidate_is_ever_labelled_best_preferred_or_winner():
    result = run(genome_with("research", "cost", "security"), max_candidates=3)
    assert not hasattr(result, "best")
    assert not hasattr(result, "preferred")
    assert not hasattr(result, "winner")
    assert "rank" not in type(result).model_fields
    assert "score" not in type(result).model_fields
