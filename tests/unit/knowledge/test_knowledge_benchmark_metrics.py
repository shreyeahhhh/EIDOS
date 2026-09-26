"""The benchmark's metrics and runner, against rankings worked out by hand (decisions.md D-213, D-225 reading 10; V1.3 Step 4, phase C).

Nothing here retrieves with a real retriever. The metrics are pure functions of a ranking and gold labels, so each is checked on small rankings whose answers are worked out on paper, on
the way a byte-identical mirror counts once, and on the runner with scripted ports (one that always answers perfectly and one that never answers) whose reports are known in advance.
"""

import json
from fractions import Fraction

from eidos.knowledge import KnowledgeSnapshot, RetrievalRequest, RetrievalResult, RetrievedChunk, build_snapshot
from eidos_knowledge_factories import SCHEME, doc
from eidos_retrieval_benchmark import (
    KS,
    evaluate,
    gold_group_ranks,
    group_ranking,
    macro_mean,
    percentile,
    recall_at_k,
    reciprocal_rank,
    report_digest,
    run_benchmark,
    source_coverage_at_k,
    summarise,
)
from eidos_retrieval_fixture import QUERIES, build_fixture_snapshot, chunk_of, gold_groups, group_of

# Six chunks, each its own document: A, B, C, D, E under sources s1 to s5, and M, a byte-identical mirror of A under s6 (so A and M are one content-equivalence group).
SNAPSHOT = build_snapshot(
    (doc("s1", "aa aa"), doc("s2", "bb bb"), doc("s3", "cc cc"), doc("s4", "dd dd"), doc("s5", "ee ee"), doc("s6", "aa aa")),
    SCHEME,
)
BY_SOURCE = {chunk.source_id: chunk for chunk in SNAPSHOT.chunks}
A, B, C, D, E, M = (BY_SOURCE[s] for s in ("s1", "s2", "s3", "s4", "s5", "s6"))
GA, GB, GC, GD, GE = (group_of(x) for x in (A, B, C, D, E))


def test_the_mirror_is_one_group_with_the_original_and_the_others_are_their_own():
    assert group_of(A) == group_of(M) and len({GA, GB, GC, GD, GE}) == 5
    assert A.chunk_id != M.chunk_id and A.source_id != M.source_id


# --- the group ranking -------------------------------------------------------------------------------------------------------------------


def test_a_group_counts_once_at_its_first_appearance():
    assert group_ranking([M, A, B]) == [GA, GB]
    assert group_ranking([B, A, M]) == [GB, GA]
    assert group_ranking([A, B, C, M, D]) == [GA, GB, GC, GD]
    assert group_ranking([]) == []


# --- Recall@k ------------------------------------------------------------------------------------------------------------------------------


def test_recall_at_k_is_the_share_of_gold_groups_among_the_first_k_groups():
    ranking, gold = [B, C, A, D, E], frozenset({GA, GE})
    assert [recall_at_k(ranking, gold, k) for k in (1, 2, 3, 4, 5)] == [Fraction(0), Fraction(0), Fraction(1, 2), Fraction(1, 2), Fraction(1)]


def test_recall_with_one_gold_group_is_zero_or_one_and_saturates_past_the_ranking():
    assert recall_at_k([A, B], frozenset({GA}), 1) == 1
    assert recall_at_k([B, A], frozenset({GA}), 1) == 0
    assert recall_at_k([B, A], frozenset({GA}), 99) == 1
    assert recall_at_k([B, C], frozenset({GA}), 99) == 0


def test_recall_has_a_ceiling_below_one_when_there_are_several_gold_groups():
    assert recall_at_k([A, B, C], frozenset({GA, GB, GC}), 1) == Fraction(1, 3)
    assert recall_at_k([A, B, C], frozenset({GA, GB, GC}), 3) == 1


def test_a_mirror_copy_neither_double_credits_nor_double_penalises():
    gold = frozenset({GA})
    assert recall_at_k([A, M, B], gold, 1) == 1 and recall_at_k([M, A, B], gold, 1) == 1
    assert recall_at_k([B, M, A], gold, 2) == 1  # the mirror is the group's first appearance, at group position 2
    assert recall_at_k([M, B, A], frozenset({GA, GB}), 2) == 1  # the deduplicated second copy does not take a slot from B


# --- MRR -----------------------------------------------------------------------------------------------------------------------------------


def test_the_reciprocal_rank_is_one_over_the_position_of_the_first_gold_group():
    assert reciprocal_rank([A, B], frozenset({GA})) == 1
    assert reciprocal_rank([B, A], frozenset({GA})) == Fraction(1, 2)
    assert reciprocal_rank([B, C, D, A], frozenset({GA, GE})) == Fraction(1, 4)
    assert reciprocal_rank([B, C, E, A], frozenset({GA, GE})) == Fraction(1, 3)  # the first of the gold groups to appear
    assert reciprocal_rank([B, C], frozenset({GA})) == 0
    assert reciprocal_rank([], frozenset({GA})) == 0


def test_the_reciprocal_rank_counts_positions_in_the_group_ranking_not_the_chunk_ranking():
    assert reciprocal_rank([B, M, A], frozenset({GA})) == Fraction(1, 2)  # not 1/3: the mirror sits at group position 2
    assert reciprocal_rank([M, B, A], frozenset({GA})) == 1
    assert reciprocal_rank([B, A, M], frozenset({GA})) == Fraction(1, 2)  # the later copy changes nothing


def test_the_rank_of_every_gold_group_is_reported_and_absent_ones_say_so():
    ranks = gold_group_ranks([B, M, C, E], frozenset({GA, GE, GD}))
    assert {GA: ranks[GA], GE: ranks[GE], GD: ranks[GD]} == {GA: 2, GE: 4, GD: None}
    assert list(ranks) == sorted(ranks)


# --- source coverage ----------------------------------------------------------------------------------------------------------------------


def test_source_coverage_is_the_share_of_gold_sources_the_first_k_chunks_cover_with_a_gold_chunk():
    chunks = SNAPSHOT.chunks
    assert source_coverage_at_k([A, B, M], chunks, frozenset({GA}), 1) == Fraction(1, 2)  # gold sources are s1 and s6: the mirror is a second source (D-221)
    assert source_coverage_at_k([A, B, M], chunks, frozenset({GA}), 3) == 1
    assert source_coverage_at_k([B, C, D], chunks, frozenset({GA}), 3) == 0
    assert source_coverage_at_k([A, C, B], chunks, frozenset({GA, GB}), 1) == Fraction(1, 3)
    assert source_coverage_at_k([A, C, B], chunks, frozenset({GA, GB}), 3) == Fraction(2, 3)


def test_a_chunk_that_is_not_gold_covers_nothing_however_high_it_ranks():
    assert source_coverage_at_k([B, C, D, A], SNAPSHOT.chunks, frozenset({GA}), 3) == 0


def test_source_coverage_counts_the_first_k_chunks_where_recall_counts_the_first_k_groups():
    ranking, gold = [A, M, B], frozenset({GA, GB})
    assert recall_at_k(ranking, gold, 2) == 1  # the groups are A's and B's
    assert source_coverage_at_k(ranking, SNAPSHOT.chunks, gold, 2) == Fraction(2, 3)  # the chunks are A and M: s1 and s6 of the gold sources s1, s6 and s2


# --- averaging and percentiles -----------------------------------------------------------------------------------------------------------


def test_the_macro_mean_is_exact():
    assert macro_mean([Fraction(1, 2), Fraction(1), Fraction(0)]) == Fraction(1, 2)
    assert macro_mean([Fraction(1, 3)] * 3) == Fraction(1, 3)
    assert macro_mean([Fraction(1, 3), Fraction(2, 3)]) == Fraction(1, 2)


def test_a_percentile_is_the_smallest_value_at_or_above_the_fraction_of_the_sorted_samples():
    values = list(range(1, 11))
    assert (percentile(values, 0.5), percentile(values, 0.95), percentile(values, 1.0), percentile(values, 0.0 + 1e-9)) == (5, 10, 10, 1)
    assert percentile([7], 0.95) == 7


# --- one query on the real fixture, with a ranking made up by hand ---------------------------------------------------------------------


FIXTURE = build_fixture_snapshot()
QUERY = {q.query_id: q for q in QUERIES}


def test_a_query_is_evaluated_against_its_gold_groups_with_every_metric():
    query = QUERY["L01"]  # one gold group: paragraph 1 of ops-startup
    gold_chunk = chunk_of(FIXTURE, "ops-startup", 1)
    other = chunk_of(FIXTURE, "ops-startup", 0)
    outcome = evaluate(query, FIXTURE, [other, gold_chunk])
    assert (outcome.gold_groups, outcome.gold_sources, outcome.retrieved, outcome.first_gold_group_rank) == (1, 1, 2, 2)
    assert outcome.recall == (Fraction(0), Fraction(1), Fraction(1)) and outcome.reciprocal_rank == Fraction(1, 2)
    assert outcome.source_coverage == (Fraction(0), Fraction(1), Fraction(1)) and outcome.gold_group_ranks == (2,)


def test_the_mirrored_gold_group_is_one_group_in_two_sources_on_the_real_fixture():
    query = QUERY["L06"]  # paragraph 0 of the safety audit, which the archive holds a byte-identical copy of
    original, mirror = chunk_of(FIXTURE, "safety-audit", 0), chunk_of(FIXTURE, "archive-audit-copy", 0)
    assert group_of(original) == group_of(mirror) and gold_groups(FIXTURE, query) == frozenset({group_of(original)})
    outcome = evaluate(query, FIXTURE, [mirror, original])
    assert (outcome.gold_groups, outcome.gold_sources) == (1, 2)
    assert outcome.recall == (Fraction(1), Fraction(1), Fraction(1)) and outcome.reciprocal_rank == 1
    assert outcome.source_coverage == (Fraction(1, 2), Fraction(1), Fraction(1))


def test_a_query_whose_gold_is_never_returned_scores_zero_everywhere_and_says_so():
    outcome = evaluate(QUERY["L04"], FIXTURE, [chunk_of(FIXTURE, "ops-startup", 0)])
    assert outcome.recall == (0, 0, 0) and outcome.reciprocal_rank == 0 and outcome.source_coverage == (0, 0, 0)
    assert outcome.first_gold_group_rank is None and outcome.gold_group_ranks == (None,)


def test_the_metrics_are_computed_at_exactly_the_ks_the_owner_approved():
    assert KS == (1, 3, 5)


def test_a_summary_reports_exact_values_a_four_place_rendering_and_how_many_queries_found_nothing():
    found = evaluate(QUERY["L01"], FIXTURE, [chunk_of(FIXTURE, "ops-startup", 1)])
    lost = evaluate(QUERY["L04"], FIXTURE, [])
    summary = summarise([found, lost])
    assert summary["queries"] == 2 and summary["queries_with_no_gold_group_retrieved"] == 1
    assert summary["recall@1"] == {"exact": "1/2", "decimal": "0.5000"} and summary["mrr"] == {"exact": "1/2", "decimal": "0.5000"}
    assert summary["source_coverage@5"] == {"exact": "1/2", "decimal": "0.5000"}
    assert set(summary) == {"queries", "recall@1", "recall@3", "recall@5", "mrr", "source_coverage@1", "source_coverage@3", "source_coverage@5", "queries_with_no_gold_group_retrieved"}


# --- the runner, with scripted ports ------------------------------------------------------------------------------------------------------


SCHEME_ID = "scripted/v1"


class Scripted:
    """A port that answers each fixture query from a script, whatever the retrieval scheme: ``ranking(query)`` gives the chunks in rank order."""

    def __init__(self, snapshot: KnowledgeSnapshot, ranking):
        self.snapshot, self.ranking = snapshot, ranking
        self.by_text = {q.text: q for q in QUERIES}

    def retrieve(self, request: RetrievalRequest):
        query = self.by_text[request.text]
        chunks = self.ranking(self.snapshot, query)[: request.top_k]
        return RetrievalResult(
            query_id=request.query_id, kb_id=request.kb_id, snapshot_id=request.snapshot_id, scheme_id=request.scheme_id,
            hits=tuple(RetrievedChunk(rank=i, chunk=chunk) for i, chunk in enumerate(chunks, start=1)),
        )


def oracle(snapshot, query):
    """Every gold chunk first, the mirror's copy included, then the rest in canonical order: the best ranking there is."""
    gold = gold_groups(snapshot, query)
    return [c for c in snapshot.chunks if group_of(c) in gold] + [c for c in snapshot.chunks if group_of(c) not in gold]


def nothing(snapshot, query):
    return []


def test_a_retriever_that_always_answers_perfectly_scores_the_ceilings_the_gold_sizes_allow():
    report = run_benchmark(lambda snapshot: Scripted(snapshot, oracle), SCHEME_ID)
    test = [q for q in QUERIES if q.split == "test"]
    sizes = [len(gold_groups(FIXTURE, q)) for q in test]
    for index, k in enumerate(KS):
        expected = macro_mean([Fraction(min(k, n), n) for n in sizes])
        assert report["overall"]["test"][f"recall@{k}"]["exact"] == str(expected), k
    assert report["overall"]["test"]["mrr"]["exact"] == "1" and report["overall"]["test"]["queries_with_no_gold_group_retrieved"] == 0


def test_a_retriever_that_never_answers_scores_zero_and_every_query_says_it_found_nothing():
    report = run_benchmark(lambda snapshot: Scripted(snapshot, nothing), SCHEME_ID)
    for split, count in (("test", 30), ("dev", 6)):
        summary = report["overall"][split]
        assert summary["queries"] == count and summary["queries_with_no_gold_group_retrieved"] == count
        assert all(summary[name]["exact"] == "0" for name in ("recall@1", "recall@3", "recall@5", "mrr", "source_coverage@1", "source_coverage@3", "source_coverage@5"))


def test_the_report_states_the_frozen_fixture_the_scheme_and_the_snapshot_it_was_measured_on():
    report = run_benchmark(lambda snapshot: Scripted(snapshot, oracle), SCHEME_ID)
    assert report["scheme_id"] == SCHEME_ID and report["snapshot_id"] == FIXTURE.snapshot_id and report["chunks"] == len(FIXTURE.chunks) == 53
    assert len(report["fixture_digest"]) == 64


def test_the_report_is_divided_by_split_and_stratum_with_the_counts_the_design_gives():
    report = run_benchmark(lambda snapshot: Scripted(snapshot, oracle), SCHEME_ID)
    counts = {split: {stratum: s["queries"] for stratum, s in strata.items()} for split, strata in report["per_stratum"].items()}
    assert counts["test"] == {"distractor": 6, "lexical": 8, "multi_source": 6, "paraphrase": 10}
    assert counts["dev"] == {"distractor": 1, "lexical": 2, "multi_source": 1, "paraphrase": 2}
    assert [q["query_id"] for q in report["per_query"]] == [q.query_id for q in QUERIES]


def test_the_report_carries_the_rank_of_every_gold_group_for_every_query():
    report = run_benchmark(lambda snapshot: Scripted(snapshot, oracle), SCHEME_ID)
    for query, entry in zip(QUERIES, report["per_query"]):
        assert entry["gold_groups"] == len(gold_groups(FIXTURE, query))
        assert sorted(entry["gold_group_ranks"]) == list(range(1, entry["gold_groups"] + 1))  # an oracle ranks the gold groups 1 to n


def test_a_report_is_json_and_its_digest_is_stable_and_sensitive():
    first = run_benchmark(lambda snapshot: Scripted(snapshot, oracle), SCHEME_ID)
    again = run_benchmark(lambda snapshot: Scripted(snapshot, oracle), SCHEME_ID)
    assert report_digest(first) == report_digest(again) and json.loads(json.dumps(first)) == first
    worse = run_benchmark(lambda snapshot: Scripted(snapshot, nothing), SCHEME_ID)
    assert report_digest(worse) != report_digest(first)


def test_a_partial_ranking_the_retriever_returns_is_scored_as_returned():
    def first_gold_only(snapshot, query):
        return [chunk_of(snapshot, *query.gold[0])]

    report = run_benchmark(lambda snapshot: Scripted(snapshot, first_gold_only), SCHEME_ID)
    test = [q for q in QUERIES if q.split == "test"]
    assert report["overall"]["test"]["mrr"]["exact"] == "1" and report["overall"]["test"]["queries"] == 30
    expected = macro_mean([Fraction(1, len(gold_groups(FIXTURE, q))) for q in test])  # only the first gold group was returned, so only 1 of n is ever found
    assert report["overall"]["test"]["recall@5"]["exact"] == str(expected)
