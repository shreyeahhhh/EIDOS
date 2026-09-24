"""Benchmark 2: a controlled evaluation of experience-informed strategy selection (decisions.md D-198 ruling 11;
V1.0 Step 7 — the final V1.0 step).

**Research question**: can measured execution experience from previous missions change future strategy selection
under controlled conditions? This is a controlled engineering/reproducibility evaluation, exactly like Benchmark 1
(`tests/scenarios/test_benchmark_execution_control.py`) one layer up — not a statistically significant study.
Nothing here produces or asserts a "best strategy" claim, a quality score, a combined benchmark score, a
statistical-significance claim, a general-superiority claim, or ranking/election language. Every assertion below
checks one narrow, already-recorded fact (which shape a real selector picked, whether historical experience was
available, whether an execution actually halted or verified) against a small, deterministic, three-pair,
five-mission-per-condition design.

**Design** (see `eidos_benchmark2_harness`'s own module docstring for the full architecture): three fixed
capability pairs (research+cost, research+security, cost+security), three conditions (D1 `DeterministicSelector`,
D2 `ModelAssistedSelector` scripted to the same parallel choice, E1 the real `ExperienceInformedSelector` over a
real JSONL `ExperienceStore`), five missions per condition per pair — 45 mission executions in total. A
deterministic, topology-driven `AdmissionGuard` halts the parallel shape and never the linear one; every mission
scripts uniformly sufficient citations so citation quality is never the confound.

Every case prints its own facts before asserting; `pytest -s -v` on this file is the benchmark's own report.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from eidos.contracts import PlanStepKind
from eidos.memory import JsonlExperienceStore
from eidos.planning import DeterministicSelector, SelectionOutcome, select_strategy
from eidos.selectors import ExperienceInformedSelector, ModelAssistedSelector

from eidos_agents_factories import make_settings
from eidos_benchmark2_harness import (
    CAPABILITY_PAIRS,
    N_MISSIONS,
    Capture,
    ScriptedPort,
    _run_one_mission,
    _seed,
    _selector_picks_parallel,
    _shape_of,
    generate_pair_candidates,
    report_table,
    run_d1_sequence,
    run_d2_sequence,
    run_e1_sequence,
    run_full_benchmark,
)

_PARALLEL_SHAPE = lambda pair: (tuple(pair),)  # noqa: E731 - a two-capability parallel shape is one stage, both capabilities
_LINEAR_SHAPE = lambda pair: tuple((capability,) for capability in pair)  # noqa: E731


# =================================================================================================================
# 1 — Candidate equivalence: every condition sees the identical feasible candidate set for the same task pair
# =================================================================================================================


def test_candidate_equivalence_across_repeated_generation_and_across_pairs():
    for pair in CAPABILITY_PAIRS:
        shape_sets = []
        for draw in range(3):  # three independent draws, standing in for D1/D2/E1's own independent generation calls
            _state, generation = generate_pair_candidates(pair, seed=500 + draw)
            shape_sets.append({_shape_of(candidate) for candidate in generation.candidates})
        assert shape_sets[0] == shape_sets[1] == shape_sets[2], f"{pair}: candidate shapes differ across draws"
        assert shape_sets[0] == {_LINEAR_SHAPE(pair), _PARALLEL_SHAPE(pair)}


# =================================================================================================================
# 2 — D1 behavior: verify its actual deterministic selection (never hardcoded, always derived)
# =================================================================================================================


def test_d1_selects_exactly_what_deterministic_selector_itself_computes():
    for pair_index, pair in enumerate(CAPABILITY_PAIRS):
        seed = _seed(pair_index, 1, 1)
        _state, generation = generate_pair_candidates(pair, seed)
        genome = _state.task_genome
        expected = select_strategy(DeterministicSelector(), generation.candidates, genome)
        assert expected.outcome is SelectionOutcome.SELECTED
        expected_shape = _shape_of(expected.selected)

        result, *_ = _run_one_mission(
            condition="D1", capability_pair=pair, mission_index=1, seed=seed, selector=DeterministicSelector(),
        )
        assert result.selected_strategy_shape == expected_shape == _PARALLEL_SHAPE(pair)


def test_d1_is_stable_across_all_five_missions_of_every_pair():
    for pair_index, pair in enumerate(CAPABILITY_PAIRS):
        results = run_d1_sequence(pair, pair_index=pair_index)
        assert len(results) == N_MISSIONS
        for result in results:
            print(result)
            assert result.selected_strategy_shape == _PARALLEL_SHAPE(pair)
            assert result.mission_status == "paused"
            assert result.history_available is False and result.relevant_history_count == 0


# =================================================================================================================
# 3 — D2 behavior: the scripted model response produces the intended deterministic choice
# =================================================================================================================


def test_d2_scripted_response_resolves_to_the_same_choice_deterministic_selector_makes():
    for pair_index, pair in enumerate(CAPABILITY_PAIRS):
        seed = _seed(pair_index, 2, 1)
        _state, generation = generate_pair_candidates(pair, seed)
        genome = _state.task_genome
        deterministic_choice = select_strategy(DeterministicSelector(), generation.candidates, genome)
        assert deterministic_choice.outcome is SelectionOutcome.SELECTED

        capture = Capture()
        model_assisted = ModelAssistedSelector(model=ScriptedPort(capture.wrap(_selector_picks_parallel)), settings=make_settings())
        scripted_choice = select_strategy(model_assisted, generation.candidates, genome)
        assert scripted_choice.outcome is SelectionOutcome.SELECTED
        assert _shape_of(scripted_choice.selected) == _shape_of(deterministic_choice.selected) == _PARALLEL_SHAPE(pair)


def test_d2_is_stable_across_all_five_missions_of_every_pair():
    for pair_index, pair in enumerate(CAPABILITY_PAIRS):
        results = run_d2_sequence(pair, pair_index=pair_index)
        assert len(results) == N_MISSIONS
        for result in results:
            print(result)
            assert result.selected_strategy_shape == _PARALLEL_SHAPE(pair)
            assert result.selector_model_calls == 1
            assert result.history_available is False and result.relevant_history_count == 0


# =================================================================================================================
# 4 — E1 adaptation: mission 1 is genuinely cold; missions 2-5 have and use accumulated history
# =================================================================================================================


def test_e1_mission_1_is_a_genuine_cold_start_matching_d1_d2(tmp_path):
    for pair_index, pair in enumerate(CAPABILITY_PAIRS):
        store_path = tmp_path / f"cold_{pair_index}.jsonl"
        results = run_e1_sequence(pair, pair_index=pair_index, store_path=store_path)
        first = results[0]
        assert first.history_available is False
        assert first.relevant_history_count == 0
        assert first.selected_strategy_shape == _PARALLEL_SHAPE(pair)  # matches the fallback's own bias exactly
        assert first.mission_status == "paused"  # the guard halts it: real, recorded non-success


def test_e1_missions_2_to_5_have_and_use_accumulated_history(tmp_path):
    for pair_index, pair in enumerate(CAPABILITY_PAIRS):
        store_path = tmp_path / f"adapt_{pair_index}.jsonl"
        results = run_e1_sequence(pair, pair_index=pair_index, store_path=store_path)
        for result in results[1:]:
            print(result)
            assert result.history_available is True
            assert result.relevant_history_count >= 1
            # requirement: the real selector diverges from what DeterministicSelector's own bias alone would pick
            _state, generation = generate_pair_candidates(pair, seed=_seed(pair_index, 3, result.mission_index))
            fallback_choice = select_strategy(DeterministicSelector(), generation.candidates, _state.task_genome)
            assert _shape_of(fallback_choice.selected) == _PARALLEL_SHAPE(pair)  # the bias alone still says parallel
            assert result.selected_strategy_shape == _LINEAR_SHAPE(pair)  # experience overrides it
            assert result.mission_status == "completed" and result.verified is True


def test_each_e1_mission_is_a_genuinely_separate_mission(tmp_path):
    # Calls the real run_e1_sequence (not a hand-rolled reimplementation of its loop) so a bug that made the
    # sequence replay one fixed mission identity instead of advancing through five distinct ones would actually
    # be exercised here (D-198/Step 6's own "fresh mission identity per mission" discipline).
    pair, pair_index = CAPABILITY_PAIRS[0], 0
    results = run_e1_sequence(pair, pair_index=pair_index, store_path=tmp_path / "distinct_missions.jsonl")
    assert len({r.mission_id for r in results}) == len({r.execution_id for r in results}) == N_MISSIONS


def test_e1_selection_is_performed_by_the_real_experience_informed_selector(tmp_path):
    # A structural proof, not a name check: an ExperienceInformedSelector constructed exactly like run_e1_sequence's
    # own, over the identical on-disk history, must agree with what the harness itself recorded.
    pair, pair_index = CAPABILITY_PAIRS[0], 0
    store_path = tmp_path / "direct.jsonl"
    results = run_e1_sequence(pair, pair_index=pair_index, store_path=store_path)

    seed = _seed(pair_index, 3, 3)  # mission 3: history from missions 1-2 already on disk
    _state, generation = generate_pair_candidates(pair, seed)
    reopened = JsonlExperienceStore.open(store_path)
    assert isinstance(reopened, JsonlExperienceStore)
    selector = ExperienceInformedSelector(store=reopened, fallback=DeterministicSelector())
    choice = select_strategy(selector, generation.candidates, _state.task_genome)
    assert choice.outcome is SelectionOutcome.SELECTED
    assert _shape_of(choice.selected) == results[2].selected_strategy_shape == _LINEAR_SHAPE(pair)


# =================================================================================================================
# 5 — Structural matching: fresh StrategyIds every mission, never reused, never the reason selection changes
# =================================================================================================================


def test_fresh_strategy_ids_every_mission_never_reused_within_a_sequence(tmp_path):
    for pair_index, pair in enumerate(CAPABILITY_PAIRS):
        store_path = tmp_path / f"ids_{pair_index}.jsonl"
        results = run_e1_sequence(pair, pair_index=pair_index, store_path=store_path)
        ids = [result.selected_strategy_id for result in results]
        assert len(set(ids)) == len(ids) == N_MISSIONS, f"{pair}: a selected_strategy_id was reused across missions"
        # despite every id being fresh, the SAME structural shape recurs identically for missions 2-5 (matched by
        # shape, D-182) — the direct proof that structural matching, not id reuse, drives the observed adaptation
        assert len({result.selected_strategy_shape for result in results[1:]}) == 1


# =================================================================================================================
# 6 — Outcome linkage: the selected topology is exactly what was expanded and executed
# =================================================================================================================


def test_selected_topology_matches_the_plan_actually_executed():
    pair, pair_index = CAPABILITY_PAIRS[0], 0
    seed = _seed(pair_index, 3, 1)

    result, selected, _telemetry, _state, plan = _run_one_mission(
        condition="E1", capability_pair=pair, mission_index=1, seed=seed, selector=DeterministicSelector(),
    )
    expected_capabilities = sorted(cap for stage in selected.stages for cap in stage.capabilities)
    agent_steps = [s for s in plan.steps if s.kind is PlanStepKind.AGENT]
    assert sorted(s.capability for s in agent_steps) == expected_capabilities
    assert result.selected_strategy_shape == _shape_of(selected)


# =================================================================================================================
# 7 — Persistence: the store contains the sequence of experiences in order, surviving a fresh reopen
# =================================================================================================================


def test_e1_store_persists_the_full_sequence_in_order(tmp_path):
    pair, pair_index = CAPABILITY_PAIRS[0], 0
    store_path = tmp_path / "persist.jsonl"
    results = run_e1_sequence(pair, pair_index=pair_index, store_path=store_path)

    final = JsonlExperienceStore.open(store_path)
    assert isinstance(final, JsonlExperienceStore)
    history = final.all()
    assert len(history) == N_MISSIONS
    # in order: mission 1's own halted, non-verified record first; every later record verified-success
    assert history[0].run_outcome.value == results[0].run_outcome == "halted"
    assert history[0].verified is not True
    for record, result in zip(history[1:], results[1:]):
        assert record.run_outcome.value == result.run_outcome == "finished"
        assert record.verified is True


# =================================================================================================================
# 8 — Reproducibility: two independent processes, two different PYTHONHASHSEED values, identical digest vectors
# =================================================================================================================

_REPRODUCIBILITY_SCRIPT = """
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, "src")
sys.path.insert(0, "tests/support")
from eidos_benchmark2_harness import run_full_benchmark, digest_of
with tempfile.TemporaryDirectory() as tmp:
    results = run_full_benchmark(Path(tmp))
print(json.dumps([r.digest for r in results]))
"""


def test_full_benchmark_reproduces_identically_under_two_different_hash_seeds():
    digests = []
    for seed in ("0", "112233"):
        completed = subprocess.run(
            [sys.executable, "-c", _REPRODUCIBILITY_SCRIPT],
            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2],
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        assert completed.returncode == 0, completed.stderr
        digests.append(json.loads(completed.stdout))
    assert len(digests[0]) == len(digests[1]) == 45
    assert digests[0] == digests[1], "digest vectors diverged across PYTHONHASHSEED values"
    assert all(d != "" for d in digests[0])


# =================================================================================================================
# Full 45-mission run and report — primary observations, never a combined score
# =================================================================================================================


def test_full_benchmark_runs_and_reports(tmp_path):
    results = run_full_benchmark(tmp_path)
    assert len(results) == 3 * 3 * N_MISSIONS
    print()
    print(report_table(results))

    by_condition_pair = {}
    for result in results:
        by_condition_pair.setdefault((result.condition, result.capability_pair), []).append(result)
    assert len(by_condition_pair) == 9
    for missions in by_condition_pair.values():
        assert len(missions) == N_MISSIONS

    for pair in CAPABILITY_PAIRS:
        # Observation 1/2: D1 and D2 select parallel across every one of their five missions.
        for condition in ("D1", "D2"):
            missions = by_condition_pair[(condition, pair)]
            assert all(m.selected_strategy_shape == _PARALLEL_SHAPE(pair) for m in missions)
            assert all(m.history_available is False for m in missions)

        e1_missions = by_condition_pair[("E1", pair)]
        # Observation 3: E1's own mission 1 matches D1/D2's own first-mission choice exactly (the cold-start equivalence).
        assert e1_missions[0].selected_strategy_shape == _PARALLEL_SHAPE(pair)
        assert e1_missions[0].mission_status == "paused"
        # Observation 4: E1's selection changed for every mission after the first, once history existed.
        for mission in e1_missions[1:]:
            assert mission.selected_strategy_shape == _LINEAR_SHAPE(pair)
            assert mission.history_available is True
        # Observation 5: fresh StrategyIds had no bearing on structural matching (every id distinct, shape stable).
        assert len({m.selected_strategy_id for m in e1_missions}) == N_MISSIONS
        # Observation 6: recorded execution outcomes correspond exactly to the selected topology.
        for mission in e1_missions:
            if mission.selected_strategy_shape == _PARALLEL_SHAPE(pair):
                assert mission.run_outcome == "halted" and mission.verified is not True
            else:
                assert mission.run_outcome == "finished" and mission.verified is True
    # Observation 7 (reproducibility) is checked separately, by subprocess, under two PYTHONHASHSEED values —
    # see test_full_benchmark_reproduces_identically_under_two_different_hash_seeds above.
