"""Benchmark 3: the lexical retriever on the frozen retrieval fixture (decisions.md D-208, D-213, D-225; V1.3 Step 4, phase C).

This scenario runs the deterministic lexical retriever over the frozen fixture and pins what was measured, so that a later change to the retriever, the chunker or the fixture cannot alter
the baseline without a test failing and a new measurement being recorded. **It judges nothing.** No retriever is called better, best or sufficient here or anywhere in this milestone: the
numbers are a measured baseline for the semantic retriever's own run (Step 5), and the comparison and the decision are the owner's (Step 6). The cost measurements (latency, memory) are
environment-specific and are recorded by the harness, never asserted; what is asserted for them is only that they are measured and well formed.

The measured values below were recorded on 2026-09-25 from the first run of the retriever on the fixture, which was frozen (digest ``93db0b1f...``) before that run and has not been touched since.
"""

import json
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from eidos.knowledge import LEXICAL_SCHEME_ID, LexicalKnowledgePort, RetrievalResult, build_snapshot
from eidos_retrieval_benchmark import (
    corpus_footprint,
    measure_cold,
    measure_memory,
    measure_warm,
    rank_query,
    report_digest,
    run_lexical_benchmark,
)
from eidos_retrieval_fixture import CHUNKING, KB_ID, QUERIES, build_fixture_snapshot, fixture_digest, knowledge_documents

ROOT = Path(__file__).resolve().parents[2]
FROZEN_DIGEST = "93db0b1f14c7c444073f86c763e891f1ccab92e5259f62351305b374db57df6b"
MEASURED_REPORT_DIGEST = "f10840ecaf7642f1ffbb098e031ae165a2ae017f913577495766965214a822ff"

# The measured baseline (test queries, macro-averaged, exact), recorded from the first run.
MEASURED_TEST = {
    "queries": 30,
    "recall@1": "1579/3600",
    "recall@3": "47/100",
    "recall@5": "1867/3600",
    "mrr": "7675247003/12098497950",
    "source_coverage@1": "73/180",
    "source_coverage@3": "1/2",
    "source_coverage@5": "11/20",
    "queries_with_no_gold_group_retrieved": 0,
}
MEASURED_DEV = {
    "queries": 6,
    "recall@1": "8/15",
    "recall@3": "17/30",
    "recall@5": "3/5",
    "mrr": "25/36",
    "source_coverage@1": "13/24",
    "source_coverage@3": "7/12",
    "source_coverage@5": "5/8",
    "queries_with_no_gold_group_retrieved": 0,
}

REPORT = run_lexical_benchmark()


def exact(summary: dict) -> dict:
    return {k: (v["exact"] if isinstance(v, dict) else v) for k, v in summary.items()}


# --- what was measured, pinned ------------------------------------------------------------------------------------------------------------------


def test_the_run_was_made_on_the_fixture_that_was_frozen_before_any_result_was_observed():
    assert REPORT["fixture_digest"] == FROZEN_DIGEST == fixture_digest()
    assert REPORT["scheme_id"] == LEXICAL_SCHEME_ID and REPORT["chunks"] == 53


def test_the_test_and_development_baselines_are_the_values_recorded_from_the_first_run():
    assert exact(REPORT["overall"]["test"]) == MEASURED_TEST
    assert exact(REPORT["overall"]["dev"]) == MEASURED_DEV


def test_the_whole_report_is_the_one_recorded_and_a_change_of_any_rank_would_fail_here():
    assert report_digest(REPORT) == MEASURED_REPORT_DIGEST


def test_every_query_gets_a_ranking_of_the_chunks_that_share_a_term_and_finds_at_least_one_gold_group():
    for entry in REPORT["per_query"]:
        assert entry["retrieved"] >= 1 and entry["first_gold_group_rank"] is not None, entry["query_id"]


def test_a_gold_group_that_shares_no_term_with_its_query_is_never_returned_and_two_queries_have_one():
    """Measured, not designed: a lexical retriever cannot return a chunk that shares no term with the query, so a gold group with no shared term has no rank. Two queries have one, and
    their multi-group gold labels are why: M03 (the news bulletin's paragraph 0 says 'brake disc', the query 'braking discs') and MD1 (the maintenance schedule's paragraph 2 says 'record'
    and 'file', the query 'recorded' and 'filed'); both are gold because the fact is stated there, in other words."""
    lost = {entry["query_id"]: entry["gold_group_ranks"].count(None) for entry in REPORT["per_query"] if None in entry["gold_group_ranks"]}
    assert lost == {"M03": 1, "MD1": 1}


def test_the_report_makes_no_judgement_it_holds_measurements_only():
    text = json.dumps(REPORT).lower()
    for word in ("better", "best", "worse", "sufficient", "insufficient", "wins", "passes", "fails", "threshold", "verdict"):
        assert word not in text, word
    assert set(REPORT) == {"fixture_digest", "scheme_id", "snapshot_id", "chunks", "overall", "per_stratum", "per_query"}


# --- the bounds the request carries change nothing about the ranking ---------------------------------------------------------------------------


def test_a_top_k_of_five_returns_exactly_the_first_five_of_the_full_ranking_for_every_query():
    snapshot = build_fixture_snapshot()
    port = LexicalKnowledgePort(snapshot, kb_id=KB_ID)
    for query in QUERIES:
        full = rank_query(port, snapshot, query, LEXICAL_SCHEME_ID)
        five = rank_query(port, snapshot, query, LEXICAL_SCHEME_ID, top_k=5)
        assert isinstance(five, RetrievalResult) and five.hits == full.hits[:5], query.query_id
        assert [h.rank for h in five.hits] == list(range(1, len(five.hits) + 1))


def test_every_ranking_is_ordered_by_score_descending_and_then_chunk_id_ascending_and_ranked_from_one():
    snapshot = build_fixture_snapshot()
    port = LexicalKnowledgePort(snapshot, kb_id=KB_ID)
    for query in QUERIES:
        result = rank_query(port, snapshot, query, LEXICAL_SCHEME_ID)
        keys = [(-h.score, h.chunk.chunk_id) for h in result.hits]
        assert keys == sorted(keys) and len(set(keys)) == len(keys) and result.score_kind == "lexical-bm25-v1"


def test_a_mirror_pair_is_a_real_tie_ordered_by_chunk_id_wherever_both_copies_are_returned():
    snapshot = build_fixture_snapshot()
    port = LexicalKnowledgePort(snapshot, kb_id=KB_ID)
    ties = 0
    for query in QUERIES:
        hits = rank_query(port, snapshot, query, LEXICAL_SCHEME_ID).hits
        by_text = {}
        for h in hits:
            by_text.setdefault(h.chunk.text, []).append(h)
        for copies in by_text.values():
            if len(copies) == 2:
                ties += 1
                assert copies[0].score == copies[1].score and copies[0].chunk.chunk_id < copies[1].chunk.chunk_id
    assert ties > 0


# --- reproducibility --------------------------------------------------------------------------------------------------------------------------


def test_running_the_benchmark_again_gives_a_byte_identical_report():
    assert report_digest(run_lexical_benchmark()) == report_digest(REPORT)


def test_the_report_does_not_depend_on_the_order_the_documents_are_declared_in():
    reference_snapshot = build_fixture_snapshot()
    reference = LexicalKnowledgePort(reference_snapshot, kb_id=KB_ID)
    generator = random.Random(4)
    documents = list(knowledge_documents())
    for _ in range(3):
        generator.shuffle(documents)
        snapshot = build_snapshot(documents, CHUNKING)
        assert snapshot == reference_snapshot
        port = LexicalKnowledgePort(snapshot, kb_id=KB_ID)
        assert all(rank_query(port, snapshot, q, LEXICAL_SCHEME_ID) == rank_query(reference, reference_snapshot, q, LEXICAL_SCHEME_ID) for q in QUERIES)


STORY = """
import sys
sys.path[:0] = ['src', 'tests/support']
from eidos_retrieval_benchmark import report_digest, run_lexical_benchmark
print(report_digest(run_lexical_benchmark()))
"""


@pytest.mark.parametrize("seed", ["0", "1", "42", "2718281828"])
def test_the_report_is_identical_under_any_hash_seed(seed):
    completed = subprocess.run([sys.executable, "-c", STORY], capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED=seed))
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == MEASURED_REPORT_DIGEST


# --- the cost harness is measured from actual runs and is well formed (its numbers are never asserted) ------------------------------------------


def test_the_cost_measurements_are_taken_from_real_runs_and_are_well_formed():
    warm = measure_warm(repeats=2)
    assert warm["index_build_ms"]["median"] > 0 and warm["query_ms"]["median"] > 0 and warm["query_ms"]["samples"] == 2 * len(QUERIES)
    assert warm["query_ms"]["p95"] >= warm["query_ms"]["median"] and warm["query_ms"]["max"] >= warm["query_ms"]["p95"]
    memory = measure_memory()
    assert memory["peak_bytes"] > memory["current_bytes_after"] > 0
    footprint = corpus_footprint()
    assert footprint == {"documents": 12, "chunks": 53, "corpus_bytes_utf8": footprint["corpus_bytes_utf8"], "chunk_text_bytes_utf8": footprint["chunk_text_bytes_utf8"], "index_on_disk_bytes": 0}
    assert 0 < footprint["chunk_text_bytes_utf8"] <= footprint["corpus_bytes_utf8"]


def test_a_cold_run_in_a_fresh_interpreter_loads_no_retrieval_engine_model_or_network_library():
    cold = measure_cold()
    assert cold["first_query_ms"] > 0 and cold["index_ms"] > 0
    loaded = set(cold["third_party_modules_loaded"])
    assert loaded <= {"pydantic", "pydantic_core", "annotated_types", "typing_extensions", "typing_inspection"}  # what the contracts already need, and nothing else
    assert loaded & {"numpy", "scipy", "sklearn", "torch", "transformers", "sentence_transformers", "qdrant_client", "faiss", "requests", "httpx", "langgraph"} == set()
