"""Benchmark 4: the semantic retriever on the frozen retrieval fixture (decisions.md D-208, D-213, D-226; V1.3 Step 5).

The real pinned model, behind the process boundary, is run over the SAME frozen fixture as the lexical baseline: same corpus, gold labels, query text, groups, strata, digest, metrics and runner. This
scenario pins what was measured, so that a later change to the retriever, the model configuration, the boundary or the fixture cannot alter the measurement without a test failing and a new measurement
being recorded. **It judges nothing.** No retriever is called better, best, sufficient or rejected here or anywhere in this milestone, and no threshold or margin exists (D-226 ruling 1): the numbers are
the semantic measurement, put in the same form as the lexical baseline so that the owner can compare them (Step 6). The cost and environment measurements are one machine's, on one day, and are recorded
by the harness, never asserted; what is asserted for them is only that they are measured and well formed.

It is an explicit opt-in (``-m real_model``): it starts the real worker, so it needs the isolated Python 3.13 interpreter and the cached, pinned model, and fails loudly, never skips, without them. The
pinned values are the ones recorded on 2026-09-26 from the first run, in the environment of the recorded libraries (the ranking, not the scores, is what they pin, and it was identical across repeated
runs, across two worker processes and, on this machine, across the thread counts and batch sizes tried; nothing is claimed for another machine, and a different environment is to be re-measured and
re-recorded, never edited to pass). No parameter was tuned.
"""

import json

import pytest

from eidos.knowledge import PINNED_MODEL, RetrievalResult, SemanticKnowledgePort, semantic_scheme_id
from eidos_retrieval_benchmark import rank_query, report_digest
from eidos_retrieval_fixture import KB_ID, QUERIES, build_fixture_snapshot, fixture_digest
from eidos_semantic_benchmark import (
    FROZEN_DIGEST,
    HEADLINE,
    cache_file_count,
    collect_vectors,
    compare_vectors,
    measure_cost,
    measure_window_probe,
    rankings_of,
    run_semantic_benchmark,
    score_gaps,
    side_by_side,
    start_real_embedder,
    vector_facts,
)
from eidos_retrieval_benchmark import run_lexical_benchmark

pytestmark = pytest.mark.real_model

MEASURED_REPORT_DIGEST = "7dbab19fddd7f8a2c93751f5150214bf8d6cc9275e96ec33b68979a5996f2bf0"
MEASURED_TEST = {
    "queries": 30,
    "recall@1": "149/225",
    "recall@3": "713/900",
    "recall@5": "749/900",
    "mrr": "69/80",
    "source_coverage@1": "109/180",
    "source_coverage@3": "143/180",
    "source_coverage@5": "151/180",
    "queries_with_no_gold_group_retrieved": 0,
}
MEASURED_DEV = {
    "queries": 6,
    "recall@1": "7/10",
    "recall@3": "7/10",
    "recall@5": "11/15",
    "mrr": "61/72",
    "source_coverage@1": "5/8",
    "source_coverage@3": "17/24",
    "source_coverage@5": "17/24",
    "queries_with_no_gold_group_retrieved": 0,
}
# The lexical baseline the semantic measurement is set beside (recorded at Step 4; see test_retrieval_benchmark_lexical.py). Referenced here only to build the side-by-side table.
LEXICAL_REPORT_DIGEST = "f10840ecaf7642f1ffbb098e031ae165a2ae017f913577495766965214a822ff"


@pytest.fixture(scope="module")
def embedder():
    cache_before = cache_file_count()
    with start_real_embedder() as started:
        yield started
    assert cache_file_count() == cache_before


@pytest.fixture(scope="module")
def report(embedder):
    return run_semantic_benchmark(embedder)


def exact(summary: dict) -> dict:
    return {k: (v["exact"] if isinstance(v, dict) else v) for k, v in summary.items()}


# --- what was measured, pinned ------------------------------------------------------------------------------------------------------------------


def test_the_run_was_made_on_the_fixture_that_was_frozen_before_any_result_was_observed(report):
    assert report["fixture_digest"] == FROZEN_DIGEST == fixture_digest()
    assert report["scheme_id"] == semantic_scheme_id(PINNED_MODEL) and report["chunks"] == 53


def test_the_test_and_development_measurements_are_the_values_recorded_from_the_first_run(report):
    assert exact(report["overall"]["test"]) == MEASURED_TEST
    assert exact(report["overall"]["dev"]) == MEASURED_DEV


def test_the_whole_report_is_the_one_recorded_and_a_change_of_any_rank_would_fail_here(report):
    assert report_digest(report) == MEASURED_REPORT_DIGEST


def test_the_report_has_exactly_the_form_of_the_lexical_report_so_the_two_can_be_read_together(report):
    lexical = run_lexical_benchmark()
    assert report_digest(lexical) == LEXICAL_REPORT_DIGEST
    assert set(report) == set(lexical) == {"fixture_digest", "scheme_id", "snapshot_id", "chunks", "overall", "per_stratum", "per_query"}
    assert report["snapshot_id"] == lexical["snapshot_id"] and report["fixture_digest"] == lexical["fixture_digest"]
    assert [entry["query_id"] for entry in report["per_query"]] == [entry["query_id"] for entry in lexical["per_query"]]
    assert {key for entry in report["per_query"] for key in entry} == {key for entry in lexical["per_query"] for key in entry}
    assert report["per_stratum"].keys() == lexical["per_stratum"].keys()


def test_every_chunk_is_a_candidate_so_every_query_is_ranked_over_the_whole_corpus_and_every_gold_group_gets_a_rank(report):
    assert {entry["retrieved"] for entry in report["per_query"]} == {53}
    assert all(None not in entry["gold_group_ranks"] for entry in report["per_query"])


def test_the_report_makes_no_judgement_it_holds_measurements_only(report):
    text = json.dumps(report).lower()
    for word in ("better", "best", "worse", "sufficient", "insufficient", "wins", "passes", "fails", "threshold", "verdict", "rejected", "baseline"):
        assert word not in text, word


def test_the_side_by_side_puts_the_two_measurements_in_one_table_and_states_no_difference_or_verdict(report):
    table = side_by_side(run_lexical_benchmark(), report)
    assert set(table) == {"test", "dev", "per_stratum"}
    assert list(table["test"]) == list(HEADLINE)
    for row in table["test"].values():
        assert set(row) == {"lexical", "semantic"}
    text = json.dumps(table).lower()
    for word in ("better", "best", "worse", "wins", "verdict", "difference", "delta", "improve", "sufficient", "rejected"):
        assert word not in text, word
    assert table["test"]["recall@1"]["semantic"] == {"exact": "149/225", "decimal": "0.6622"}
    assert table["test"]["recall@1"]["lexical"] == {"exact": "1579/3600", "decimal": "0.4386"}


# --- the ranking the semantic retriever answers ---------------------------------------------------------------------------------------------------


def test_a_top_k_of_five_returns_exactly_the_first_five_of_the_full_ranking_for_every_query(embedder):
    snapshot = build_fixture_snapshot()
    port = SemanticKnowledgePort.open(snapshot, kb_id=KB_ID, embedder=embedder)
    scheme = semantic_scheme_id(PINNED_MODEL)
    for query in QUERIES:
        full = rank_query(port, snapshot, query, scheme)
        five = rank_query(port, snapshot, query, scheme, top_k=5)
        assert isinstance(five, RetrievalResult) and five.hits == full.hits[:5], query.query_id
        assert [hit.rank for hit in five.hits] == [1, 2, 3, 4, 5]


def test_every_ranking_is_ordered_by_score_descending_and_then_chunk_id_ascending_and_ranked_from_one(embedder):
    snapshot = build_fixture_snapshot()
    port = SemanticKnowledgePort.open(snapshot, kb_id=KB_ID, embedder=embedder)
    for query in QUERIES:
        result = rank_query(port, snapshot, query, semantic_scheme_id(PINNED_MODEL))
        keys = [(-hit.score, hit.chunk.chunk_id) for hit in result.hits]
        assert keys == sorted(keys) and len(set(keys)) == len(keys) and result.score_kind == "semantic-cosine-v1"
        assert [hit.rank for hit in result.hits] == list(range(1, 54))


def test_a_mirror_pair_is_a_real_tie_because_the_same_text_has_the_same_vector_and_is_ordered_by_chunk_id(embedder):
    snapshot = build_fixture_snapshot()
    port = SemanticKnowledgePort.open(snapshot, kb_id=KB_ID, embedder=embedder)
    ties = 0
    for query in QUERIES:
        by_text = {}
        for hit in rank_query(port, snapshot, query, semantic_scheme_id(PINNED_MODEL)).hits:
            by_text.setdefault(hit.chunk.text, []).append(hit)
        for copies in by_text.values():
            if len(copies) == 2:
                ties += 1
                assert copies[0].score == copies[1].score and copies[0].chunk.chunk_id < copies[1].chunk.chunk_id
    assert ties == 5 * len(QUERIES)


# --- reproducibility: measured, and no more claimed than was measured ------------------------------------------------------------------------------


def test_running_the_benchmark_again_in_the_same_worker_gives_a_byte_identical_report(embedder, report):
    assert report_digest(run_semantic_benchmark(embedder)) == report_digest(report)


def test_two_separate_worker_processes_give_the_same_vectors_bit_for_bit_the_same_scores_and_the_same_report_on_this_machine(embedder, report):
    snapshot = build_fixture_snapshot()
    first_vectors, first_rankings = collect_vectors(embedder, snapshot), rankings_of(embedder, snapshot)
    with start_real_embedder() as other:
        assert other.pid != embedder.pid
        second_vectors, second_rankings = collect_vectors(other, snapshot), rankings_of(other, snapshot)
        second_report = run_semantic_benchmark(other)
    comparison = compare_vectors(first_vectors, second_vectors)
    assert comparison["different_components"] == 0 and comparison["identical_texts"] == comparison["texts"] == 89 and comparison["largest_absolute_difference"] == 0.0
    assert first_rankings == second_rankings  # the chunk order and every score
    assert report_digest(second_report) == report_digest(report)


def test_the_gaps_between_adjacent_scores_are_measured_and_the_only_exact_ties_are_the_mirrored_chunks(embedder):
    gaps = score_gaps(rankings_of(embedder, build_fixture_snapshot()))
    assert gaps["adjacent_pairs"] == 36 * 52 and gaps["exact_ties"] == 5 * 36
    assert gaps["smallest_nonzero_gap"] > 0.0 and gaps["pairs_closer_than_1e-6"] <= gaps["pairs_closer_than_1e-4"] <= gaps["adjacent_pairs"]


# --- what only a semantic run has ---------------------------------------------------------------------------------------------------------------


def test_the_fixture_fits_the_window_so_no_text_is_refused_and_the_window_is_enforced_on_the_real_tokenizer(embedder):
    facts = vector_facts(collect_vectors(embedder, build_fixture_snapshot()))
    assert facts["token_piece_rejections"] == 0 and facts["dimension"] == [384]
    assert facts["chunk_pieces"] == {"min": 53, "max": 82, "count": 53} and facts["query_pieces"] == {"min": 11, "max": 36, "count": 36}
    probe = measure_window_probe()
    assert probe["text_of_400_words"]["refused"] and probe["text_of_400_words"]["pieces"] == 402
    assert probe["text_at_the_window"] == {"words": 126, "pieces": 128, "embedded": True}
    assert probe["text_one_piece_over"] == {"pieces": 129, "refused": True}


def test_the_cost_measurements_are_taken_from_a_real_run_and_are_well_formed_and_nothing_is_downloaded():
    cost = measure_cost(repeats=1)
    worker = cost["worker"]
    assert worker["environment"]["python_version"] == "3.13.1" and worker["environment"]["threads"] == 1
    assert worker["start_seconds_wall"] > worker["import_seconds"] > 0 and worker["model_load_seconds"] > 0 and worker["digest_verification_seconds"] > 0
    assert cost["index"]["chunks"] == 53 and cost["index"]["open_seconds_wall"] > 0
    warm = cost["warm_query"]
    assert warm["retrieval_ms"]["samples"] == 36 and warm["retrieval_ms"]["max"] >= warm["retrieval_ms"]["p95"] >= warm["retrieval_ms"]["median"] > 0
    assert cost["first_query"]["retrieval_ms"] > 0
    assert cost["footprint"]["model_directory_files"] == 10 and cost["footprint"]["model_directory_bytes"] > 400_000_000 and cost["footprint"]["index_on_disk_bytes"] == 0
    assert cost["memory"]["this_process_python_allocations"]["peak_bytes"] > 0
    assert cost["hugging_face_cache_files"]["before"] == cost["hugging_face_cache_files"]["after"]
