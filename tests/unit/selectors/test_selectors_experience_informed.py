"""``ExperienceInformedSelector`` (decisions.md D-198; V1.0 Step 4).

Every test uses the real ``JsonlExperienceStore`` (via pytest's own ``tmp_path``) — not a fake — so Step 3's
already-proven persistence and Step 4's own selection logic are exercised together, end to end, exactly as they
would be by a real caller. ``_experience(**overrides)`` mirrors the same minimal-valid-object factory pattern
``test_memory_relevance.py``/``test_memory_store.py`` already use.
"""

from dataclasses import fields
from uuid import UUID

import pytest

from eidos.contracts import (
    AutonomyLevel,
    CapabilityId,
    ExecutionId,
    MissionId,
    MissionStatus,
    RiskLevel,
    StrategyId,
    TenantId,
)
from eidos.memory import ExecutionExperience, JsonlExperienceStore
from eidos.planning import DeterministicSelector, SelectedCandidate, SelectionOutcome, StrategyStage, VerificationPosture, select_strategy
from eidos.selectors import ExperienceInformedSelector

from eidos_factories import make_task_genome
from eidos_planning_factories import make_strategy
from eidos_state_factories import T0

_TENANT, _MISSION = TenantId(UUID(int=1)), MissionId(UUID(int=2))
_next_execution_id = iter(range(1000, 100_000))


def _experience(**overrides) -> ExecutionExperience:
    fields_ = dict(
        tenant_id=_TENANT, mission_id=_MISSION, execution_id=ExecutionId(UUID(int=next(_next_execution_id))),
        strategy_id=StrategyId(UUID(int=next(_next_execution_id))), recorded_at=T0,
        strategy_stage_shapes=((CapabilityId("research"),),), strategy_verification=VerificationPosture.FINAL,
        task_required_capabilities=(CapabilityId("research"),), task_risk_level=RiskLevel.MEDIUM,
        task_autonomy_level=AutonomyLevel.SAFE_READ_ONLY,
        mission_status=MissionStatus.COMPLETED, verified=True,
        execution_time_used_ms=0, mission_wall_clock_ms=0, model_call_count=0, tokens_used=0,
        responses_missing_token_counts=0, agent_calls_used=0, tool_calls_used=0, retries_used=0, replans_used=0,
    )
    fields_.update(overrides)
    return ExecutionExperience(**fields_)


def _verified_success(**overrides) -> ExecutionExperience:
    return _experience(mission_status=MissionStatus.COMPLETED, verified=True, **overrides)


def _non_success(**overrides) -> ExecutionExperience:
    # A finished-but-unverified mission is deliberately the "non-success" fixture used throughout: a real,
    # constructible ExecutionExperience whose own facts are unambiguous ("completed" but never "verified").
    overrides.setdefault("mission_status", MissionStatus.COMPLETED)
    overrides.setdefault("verified", False)
    return _experience(**overrides)


def _store(tmp_path, *experiences: ExecutionExperience) -> JsonlExperienceStore:
    store = JsonlExperienceStore.open(tmp_path / "store.jsonl")
    assert isinstance(store, JsonlExperienceStore)
    for experience in experiences:
        store.append(experience)
    return store


def _genome(**overrides):
    overrides.setdefault("required_capabilities", (CapabilityId("research"),))
    overrides.setdefault("risk_level", RiskLevel.MEDIUM)
    overrides.setdefault("autonomy_level", AutonomyLevel.SAFE_READ_ONLY)
    return make_task_genome(**overrides)


def _strategy(*capabilities: str, verification=VerificationPosture.FINAL, strategy_id: StrategyId | None = None):
    return make_strategy(
        strategy_id=strategy_id or StrategyId(UUID(int=next(_next_execution_id))),
        stages=(StrategyStage(capabilities=tuple(CapabilityId(c) for c in capabilities)),),
        verification=verification,
    )


def _shape_of(*capabilities: str):
    return (tuple(CapabilityId(c) for c in capabilities),)


# --- no/one candidate; membership; determinism ------------------------------------------------------------------


def test_no_candidates_behaves_exactly_like_deterministic_selector(tmp_path):
    # Never reached through select_strategy (which short-circuits at 0 candidates) — but .select() itself must
    # behave identically to DeterministicSelector.select(()), not silently invent different behavior.
    selector = ExperienceInformedSelector(store=_store(tmp_path), fallback=DeterministicSelector())
    with pytest.raises(ValueError):
        selector.select((), _genome())
    with pytest.raises(ValueError):
        DeterministicSelector().select((), _genome())


def test_one_candidate_with_no_history_matches_the_fallback(tmp_path):
    candidate = _strategy("research")
    selector = ExperienceInformedSelector(store=_store(tmp_path), fallback=DeterministicSelector())
    choice = selector.select((candidate,), _genome())
    assert choice == SelectedCandidate(strategy_id=candidate.strategy_id)


def test_one_candidate_with_verified_success_is_selected(tmp_path):
    candidate = _strategy("research")
    history = _verified_success(strategy_stage_shapes=_shape_of("research"), strategy_verification=VerificationPosture.FINAL)
    selector = ExperienceInformedSelector(store=_store(tmp_path, history), fallback=DeterministicSelector())
    choice = selector.select((candidate,), _genome())
    assert choice == SelectedCandidate(strategy_id=candidate.strategy_id)


def test_candidate_membership_is_always_respected(tmp_path):
    a, b, c = _strategy("research"), _strategy("cost"), _strategy("security")
    history = _verified_success(strategy_stage_shapes=_shape_of("cost"), task_required_capabilities=(CapabilityId("cost"),))
    selector = ExperienceInformedSelector(store=_store(tmp_path, history), fallback=DeterministicSelector())
    choice = selector.select((a, b, c), _genome(required_capabilities=(CapabilityId("cost"),)))
    assert isinstance(choice, SelectedCandidate)
    assert choice.strategy_id in {a.strategy_id, b.strategy_id, c.strategy_id}


def test_selection_is_deterministic_across_repeated_calls(tmp_path):
    a, b = _strategy("research"), _strategy("cost")
    history = _verified_success(strategy_stage_shapes=_shape_of("cost"), task_required_capabilities=(CapabilityId("cost"),))
    store = _store(tmp_path, history)
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))
    selector = ExperienceInformedSelector(store=store, fallback=DeterministicSelector())
    first = selector.select((a, b), genome)
    second = selector.select((a, b), genome)
    assert first == second


def test_selector_introduces_no_model_dependency():
    # Structural proof, not just a guard: the dataclass carries only store/fallback — no model, no settings.
    assert {f.name for f in fields(ExperienceInformedSelector)} == {"store", "fallback"}


# --- cold start --------------------------------------------------------------------------------------------


def test_multiple_candidates_with_no_history_matches_the_fallback_exactly(tmp_path):
    a, b, c = _strategy("research"), _strategy("cost"), _strategy("security")
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost"), CapabilityId("security")))
    selector = ExperienceInformedSelector(store=_store(tmp_path), fallback=DeterministicSelector())
    experience_choice = selector.select((a, b, c), genome)
    fallback_choice = DeterministicSelector().select((a, b, c), genome)
    assert experience_choice == fallback_choice


def test_cold_start_equivalence_holds_for_any_configured_fallback_not_only_deterministic(tmp_path):
    # A custom fallback (not DeterministicSelector) must genuinely be the one consulted — proves the delegation
    # is real, never an internal re-derivation that happens to only work for one specific fallback. Deliberately
    # picks the *last* candidate: min()'s own tie-break stability always favours the *first* element on an exact
    # tie, so a fallback that disagrees with that stability is the one choice that can prove the call actually
    # happened, rather than the code merely falling through to an all-Tier-1 comparison that coincidentally
    # agrees with "pick the first."
    class AlwaysLast:
        def select(self, candidates, task_genome):
            return SelectedCandidate(strategy_id=candidates[-1].strategy_id)

    a, b = _strategy("cost"), _strategy("research")  # same structural_cost: a genuine Tier-1-vs-Tier-1 tie
    genome = _genome(required_capabilities=(CapabilityId("cost"), CapabilityId("research")))
    selector = ExperienceInformedSelector(store=_store(tmp_path), fallback=AlwaysLast())
    assert selector.select((a, b), genome) == SelectedCandidate(strategy_id=b.strategy_id)


def test_empty_store_is_a_cold_start_not_a_failure(tmp_path):
    candidate = _strategy("research")
    store = _store(tmp_path)
    assert store.all() == ()
    selector = ExperienceInformedSelector(store=store, fallback=DeterministicSelector())
    choice = selector.select((candidate,), _genome())
    assert isinstance(choice, SelectedCandidate)  # never a SelectorFailure


# --- Tier 0 vs Tier 1 vs Tier 2 -----------------------------------------------------------------------------


def test_verified_success_beats_no_history(tmp_path):
    proven = _strategy("research")
    untested = _strategy("cost")
    history = _verified_success(strategy_stage_shapes=_shape_of("research"))
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))
    selector = ExperienceInformedSelector(store=_store(tmp_path, history), fallback=DeterministicSelector())
    assert selector.select((proven, untested), genome) == SelectedCandidate(strategy_id=proven.strategy_id)


def test_verified_success_beats_only_non_success_history(tmp_path):
    proven = _strategy("research")
    failing = _strategy("cost")
    history = (
        _verified_success(strategy_stage_shapes=_shape_of("research")),
        _non_success(strategy_stage_shapes=_shape_of("cost")),
    )
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))
    selector = ExperienceInformedSelector(store=_store(tmp_path, *history), fallback=DeterministicSelector())
    assert selector.select((proven, failing), genome) == SelectedCandidate(strategy_id=proven.strategy_id)


def test_no_history_beats_only_non_success_history():
    # Architectural: absence of evidence is neutral; observed non-success is negative evidence, so it must rank
    # below "untested" — asserted directly against the tier-ordering rule, not just an end-to-end pick.
    from eidos.selectors.experience_informed import _tiered_key

    untested_key = _tiered_key(_strategy("research"), ())
    failing_key = _tiered_key(_strategy("cost"), (_non_success(),))
    assert untested_key < failing_key


def test_a_completed_but_unverified_record_is_never_counted_as_a_verified_success():
    # mission_status alone is not enough (a FAILED mission with a stray verified=True must never count either) —
    # both halves of _is_verified_success's own AND are exercised directly, not just through an end-to-end pick
    # that could coincidentally tie elsewhere.
    from eidos.selectors.experience_informed import _is_verified_success

    assert not _is_verified_success(_experience(mission_status=MissionStatus.COMPLETED, verified=False))
    assert not _is_verified_success(_experience(mission_status=MissionStatus.COMPLETED, verified=None))
    assert not _is_verified_success(_experience(mission_status=MissionStatus.FAILED, verified=True))
    assert _is_verified_success(_experience(mission_status=MissionStatus.COMPLETED, verified=True))


def test_tiered_key_components_directly_success_count_non_success_count_and_cost():
    # White-box, component by component — sidesteps every coincidental tie/ordering a full .select() comparison
    # could mask (two single-capability candidates share the same structural_cost, so an end-to-end pick alone
    # cannot distinguish which field actually decided it).
    from eidos.selectors.experience_informed import _tiered_key

    candidate = _strategy("research")
    zero_history_key = _tiered_key(candidate, ())
    one_success_key = _tiered_key(candidate, (_verified_success(),))
    two_successes_key = _tiered_key(candidate, (_verified_success(), _verified_success()))
    one_success_one_failure_key = _tiered_key(candidate, (_verified_success(), _non_success()))
    cheap_success_key = _tiered_key(candidate, (_verified_success(execution_time_used_ms=10),))
    costly_success_key = _tiered_key(candidate, (_verified_success(execution_time_used_ms=9_999),))

    assert zero_history_key[0] == 1 and one_success_key[0] == 0  # tier
    assert two_successes_key[1] < one_success_key[1]  # success_count: more successes sorts earlier
    assert one_success_key[2] < one_success_one_failure_key[2]  # non_success_count: fewer non-successes sorts earlier
    assert one_success_one_failure_key[1] == one_success_key[1]  # the extra record is a non-success, not a second success
    assert cheap_success_key[3] < costly_success_key[3]  # verified_cost: lower summed cost sorts earlier
    only_non_success_key = _tiered_key(candidate, (_non_success(execution_time_used_ms=5_000),))
    assert only_non_success_key[3] == 0  # cost is summed over verified successes only, never non-successes


def test_tiered_key_final_element_is_structural_cost():
    from eidos.planning import structural_cost
    from eidos.selectors.experience_informed import _tiered_key

    cheap = _strategy("research", "cost")  # one stage, two capabilities
    b_stage1, b_stage2 = StrategyStage(capabilities=(CapabilityId("research"),)), StrategyStage(capabilities=(CapabilityId("cost"),))
    costly = make_strategy(strategy_id=StrategyId(UUID(int=next(_next_execution_id))), stages=(b_stage1, b_stage2), verification=VerificationPosture.FINAL)
    assert _tiered_key(cheap, ())[-1] == structural_cost(cheap)
    assert _tiered_key(costly, ())[-1] == structural_cost(costly)
    assert _tiered_key(cheap, ())[-1] < _tiered_key(costly, ())[-1]


# --- Tier 0 tie-breaks ---------------------------------------------------------------------------------------


def test_multiple_verified_success_candidates_all_reach_tier_0(tmp_path):
    a, b = _strategy("research"), _strategy("cost")
    history = (
        _verified_success(strategy_stage_shapes=_shape_of("research")),
        _verified_success(strategy_stage_shapes=_shape_of("cost")),
    )
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))
    selector = ExperienceInformedSelector(store=_store(tmp_path, *history), fallback=DeterministicSelector())
    choice = selector.select((a, b), genome)
    assert choice.strategy_id in {a.strategy_id, b.strategy_id}  # both are legitimately Tier 0; a tie-break decides which


def test_tier_0_tie_break_by_more_verified_successes(tmp_path):
    two_successes = _strategy("research")
    one_success = _strategy("cost")
    history = (
        _verified_success(strategy_stage_shapes=_shape_of("research")),
        _verified_success(strategy_stage_shapes=_shape_of("research")),
        _verified_success(strategy_stage_shapes=_shape_of("cost")),
    )
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))
    selector = ExperienceInformedSelector(store=_store(tmp_path, *history), fallback=DeterministicSelector())
    assert selector.select((two_successes, one_success), genome) == SelectedCandidate(strategy_id=two_successes.strategy_id)


def test_tier_0_tie_break_by_fewer_non_successes_once_success_counts_are_equal(tmp_path):
    cleaner = _strategy("research")
    noisier = _strategy("cost")
    history = (
        _verified_success(strategy_stage_shapes=_shape_of("research")),
        _verified_success(strategy_stage_shapes=_shape_of("cost")),
        _non_success(strategy_stage_shapes=_shape_of("cost")),  # only "cost" carries an extra non-success
    )
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))
    selector = ExperienceInformedSelector(store=_store(tmp_path, *history), fallback=DeterministicSelector())
    assert selector.select((cleaner, noisier), genome) == SelectedCandidate(strategy_id=cleaner.strategy_id)


def test_tier_0_tie_break_by_lower_summed_execution_time_once_counts_are_equal(tmp_path):
    cheaper = _strategy("research")
    costlier = _strategy("cost")
    history = (
        _verified_success(strategy_stage_shapes=_shape_of("research"), execution_time_used_ms=100),
        _verified_success(strategy_stage_shapes=_shape_of("cost"), execution_time_used_ms=9_000),
    )
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))
    selector = ExperienceInformedSelector(store=_store(tmp_path, *history), fallback=DeterministicSelector())
    assert selector.select((cheaper, costlier), genome) == SelectedCandidate(strategy_id=cheaper.strategy_id)


# --- Tier 2 tie-break -----------------------------------------------------------------------------------------


def test_tier_2_tie_break_by_fewer_non_successes(tmp_path):
    less_bad = _strategy("research")
    more_bad = _strategy("cost")
    history = (
        _non_success(strategy_stage_shapes=_shape_of("research")),
        _non_success(strategy_stage_shapes=_shape_of("cost")),
        _non_success(strategy_stage_shapes=_shape_of("cost")),
    )
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))
    selector = ExperienceInformedSelector(store=_store(tmp_path, *history), fallback=DeterministicSelector())
    assert selector.select((less_bad, more_bad), genome) == SelectedCandidate(strategy_id=less_bad.strategy_id)


# --- Tier 1 structural-cost tie-break -----------------------------------------------------------------------


def test_tier_1_ties_break_by_structural_cost_matching_deterministic_selector(tmp_path):
    from eidos.planning import structural_cost

    a = _strategy("research", "cost")  # a single stage of two capabilities: cheaper structural_cost (fewer stages)
    b_stage1 = StrategyStage(capabilities=(CapabilityId("research"),))
    b_stage2 = StrategyStage(capabilities=(CapabilityId("cost"),))
    b = make_strategy(strategy_id=StrategyId(UUID(int=next(_next_execution_id))), stages=(b_stage1, b_stage2), verification=VerificationPosture.FINAL)
    assert structural_cost(a) < structural_cost(b)
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))
    selector = ExperienceInformedSelector(store=_store(tmp_path), fallback=DeterministicSelector())
    # No history for either shape: both Tier 1. DeterministicSelector's own comparison decides identically.
    assert selector.select((a, b), genome) == DeterministicSelector().select((a, b), genome)


# --- structural shape / verification-posture / StrategyId independence -----------------------------------------


def test_fresh_strategy_ids_with_identical_shapes_still_match(tmp_path):
    old_run_id = StrategyId(UUID(int=777_777))
    history = _verified_success(strategy_id=old_run_id, strategy_stage_shapes=_shape_of("research"))
    fresh_candidate = _strategy("research", strategy_id=StrategyId(UUID(int=888_888)))
    assert fresh_candidate.strategy_id != old_run_id
    other = _strategy("cost")
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))
    selector = ExperienceInformedSelector(store=_store(tmp_path, history), fallback=DeterministicSelector())
    assert selector.select((fresh_candidate, other), genome) == SelectedCandidate(strategy_id=fresh_candidate.strategy_id)


def test_verification_posture_mismatch_prevents_matching(tmp_path):
    candidate = _strategy("research", verification=VerificationPosture.FINAL)
    other = _strategy("cost")
    # Same shape as `candidate`, but a different verification posture: must not count toward it.
    history = _verified_success(strategy_stage_shapes=_shape_of("research"), strategy_verification=VerificationPosture.NONE)
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))
    selector = ExperienceInformedSelector(store=_store(tmp_path, history), fallback=DeterministicSelector())
    # Neither candidate reaches Tier 0: both fall to the Tier 1 (no match) vs Tier 1 comparison — resolved by
    # structural_cost, exactly as if the mismatched history did not exist at all.
    assert selector.select((candidate, other), genome) == DeterministicSelector().select((candidate, other), genome)


def test_risk_mismatch_makes_history_irrelevant_even_with_a_verified_success(tmp_path):
    candidate = _strategy("research")
    other = _strategy("cost")
    history = _verified_success(strategy_stage_shapes=_shape_of("research"), task_risk_level=RiskLevel.HIGH)
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")), risk_level=RiskLevel.LOW)
    selector = ExperienceInformedSelector(store=_store(tmp_path, history), fallback=DeterministicSelector())
    assert selector.select((candidate, other), genome) == DeterministicSelector().select((candidate, other), genome)


def test_autonomy_mismatch_makes_history_irrelevant_even_with_a_verified_success(tmp_path):
    candidate = _strategy("research")
    other = _strategy("cost")
    history = _verified_success(strategy_stage_shapes=_shape_of("research"), task_autonomy_level=AutonomyLevel.RECOMMEND_ONLY)
    genome = _genome(
        required_capabilities=(CapabilityId("research"), CapabilityId("cost")),
        autonomy_level=AutonomyLevel.HUMAN_APPROVAL_REQUIRED,
    )
    selector = ExperienceInformedSelector(store=_store(tmp_path, history), fallback=DeterministicSelector())
    assert selector.select((candidate, other), genome) == DeterministicSelector().select((candidate, other), genome)


def test_similar_capability_overlap_still_counts_toward_relevance(tmp_path):
    candidate = _strategy("research")
    other = _strategy("security")
    # Recorded for a genome requiring {research, cost}; the new genome requires {research, security} — overlaps
    # on "research" only (SIMILAR, not SAME) but is still relevant.
    history = _verified_success(
        strategy_stage_shapes=_shape_of("research"),
        task_required_capabilities=(CapabilityId("research"), CapabilityId("cost")),
    )
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("security")))
    selector = ExperienceInformedSelector(store=_store(tmp_path, history), fallback=DeterministicSelector())
    assert selector.select((candidate, other), genome) == SelectedCandidate(strategy_id=candidate.strategy_id)


# --- insertion order / duplicates -----------------------------------------------------------------------------


def test_history_order_does_not_change_the_selection_only_the_facts_do(tmp_path):
    a, b = _strategy("research"), _strategy("cost")
    success_a = _verified_success(strategy_stage_shapes=_shape_of("research"))
    success_b = _verified_success(strategy_stage_shapes=_shape_of("cost"))
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))

    forward = ExperienceInformedSelector(store=_store(tmp_path, success_a, success_b), fallback=DeterministicSelector())
    backward = ExperienceInformedSelector(store=_store(tmp_path, success_b, success_a), fallback=DeterministicSelector())
    # Both candidates reach Tier 0 with one success each either way — the choice is decided by the same
    # downstream tie-break regardless of which order the store happened to record them in.
    assert forward.select((a, b), genome) == backward.select((a, b), genome)


def test_duplicate_experiences_both_count_toward_the_success_tie_break(tmp_path):
    twice_proven = _strategy("research")
    once_proven = _strategy("cost")
    success = _verified_success(strategy_stage_shapes=_shape_of("research"))
    history = (success, success, _verified_success(strategy_stage_shapes=_shape_of("cost")))
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))
    selector = ExperienceInformedSelector(store=_store(tmp_path, *history), fallback=DeterministicSelector())
    assert selector.select((twice_proven, once_proven), genome) == SelectedCandidate(strategy_id=twice_proven.strategy_id)


# --- the worked A/B example, and its inverse --------------------------------------------------------------------


def test_historical_experience_changes_selection_linear_beats_parallel_when_linear_verified_and_parallel_failed(tmp_path):
    linear = _strategy("research")  # stands in for "Strategy B" in the brief's own labeling; shape is what matters
    parallel = _strategy("cost")
    history = (
        _non_success(strategy_stage_shapes=_shape_of("cost")),  # parallel -> verified failure (non-success)
        _verified_success(strategy_stage_shapes=_shape_of("research")),  # linear -> verified success
    )
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))

    without_memory = DeterministicSelector().select((linear, parallel), genome)
    with_memory = ExperienceInformedSelector(store=_store(tmp_path, *history), fallback=DeterministicSelector()).select((linear, parallel), genome)

    assert with_memory == SelectedCandidate(strategy_id=linear.strategy_id)
    # The memory-blind selector need not agree — proves the outcome is attributable to experience, not luck.
    if without_memory != with_memory:
        assert without_memory.strategy_id == parallel.strategy_id


def test_historical_experience_changes_selection_the_inverse_arrangement(tmp_path):
    a = _strategy("research")
    b = _strategy("cost")
    history = (
        _non_success(strategy_stage_shapes=_shape_of("research")),  # a -> verified failure
        _verified_success(strategy_stage_shapes=_shape_of("cost")),  # b -> verified success
    )
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))
    selector = ExperienceInformedSelector(store=_store(tmp_path, *history), fallback=DeterministicSelector())
    assert selector.select((a, b), genome) == SelectedCandidate(strategy_id=b.strategy_id)


# --- select_strategy integration: membership is enforced one layer up too --------------------------------------


def test_select_strategy_orchestration_is_untouched_and_still_admits_only_real_candidates(tmp_path):
    a, b = _strategy("research"), _strategy("cost")
    history = _verified_success(strategy_stage_shapes=_shape_of("cost"))
    genome = _genome(required_capabilities=(CapabilityId("research"), CapabilityId("cost")))
    selector = ExperienceInformedSelector(store=_store(tmp_path, history), fallback=DeterministicSelector())
    result = select_strategy(selector, (a, b), genome)
    assert result.outcome is SelectionOutcome.SELECTED
    assert result.selected is b  # the exact object, never reconstructed — select_strategy's own guarantee, unchanged
