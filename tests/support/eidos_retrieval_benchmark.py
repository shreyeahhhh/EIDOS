"""The retrieval benchmark's metrics and its runner (decisions.md D-213, D-225 reading 10; V1.3 Step 4, phase C).

Recall@k, MRR and source-coverage@k are exact rationals until the last step, so a report never depends on floating-point summation order. They are computed from a retriever's full ranking
(the request's ``top_k`` is the corpus size for measurement) and reported overall and per stratum, the development and the frozen test queries separately, with the rank of every gold
group per query and no significance test. **Nothing here judges a retriever**: it measures one, and a reader compares measurements; no threshold, margin or verdict is defined anywhere in
this module (D-225 reading 11).

- **Recall@k** and **MRR** work on the group ranking: the retriever's chunks in rank order, each content-equivalence group counted once at its first appearance (so a byte-identical mirror
  neither double-credits nor double-penalises). Recall@k is the share of a query's gold groups among the first k groups; the reciprocal rank is 1 over the position of the first gold group
  in the group ranking, 0 if none appears.
- **Source-coverage@k** works on the chunk ranking: the share of a query's gold sources (the declared sources of every chunk of every gold group) that the first k *chunks* cover with a
  gold chunk. A mirror is two chunks under two declared sources, so it is two sources (D-221). It is a supplementary measure, not a substitute for Recall.

The runner also measures cost from actual runs only: index-build and warm query latency, a cold run in a fresh interpreter, the peak memory Python allocated, the corpus size and the
third-party modules a retrieval loads. Those numbers describe one machine on one day and are recorded with their environment, never asserted.
"""

import hashlib
import json
import math
import statistics
import subprocess
import sys
import time
import tracemalloc
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from eidos.knowledge import (
    LEXICAL_SCHEME_ID,
    KnowledgeChunk,
    KnowledgePort,
    KnowledgeSnapshot,
    LexicalKnowledgePort,
    RetrievalRequest,
    RetrievalResult,
    canonical_query_text,
)

from eidos_retrieval_fixture import (
    DOCUMENTS,
    KB_ID,
    QUERIES,
    FixtureQuery,
    build_fixture_snapshot,
    fixture_digest,
    gold_chunks,
    gold_groups,
    group_of,
)

ROOT = Path(__file__).resolve().parents[2]
KS = (1, 3, 5)


# --- metrics: pure functions of a ranking and its gold labels -------------------------------------------------------------------------------


def group_ranking(ranked: Sequence[KnowledgeChunk]) -> list[str]:
    """The content-equivalence groups of a chunk ranking, in the order each first appears."""
    seen: dict[str, None] = {}
    for chunk in ranked:
        seen.setdefault(group_of(chunk), None)
    return list(seen)


def recall_at_k(ranked: Sequence[KnowledgeChunk], gold: frozenset[str], k: int) -> Fraction:
    return Fraction(len(gold & set(group_ranking(ranked)[:k])), len(gold))


def reciprocal_rank(ranked: Sequence[KnowledgeChunk], gold: frozenset[str]) -> Fraction:
    for position, group in enumerate(group_ranking(ranked), start=1):
        if group in gold:
            return Fraction(1, position)
    return Fraction(0)


def gold_group_ranks(ranked: Sequence[KnowledgeChunk], gold: frozenset[str]) -> dict[str, int | None]:
    """The position of each gold group in the group ranking, or ``None`` if the retriever never returned it."""
    positions = {group: position for position, group in enumerate(group_ranking(ranked), start=1)}
    return {group: positions.get(group) for group in sorted(gold)}


def source_coverage_at_k(ranked: Sequence[KnowledgeChunk], all_chunks: Sequence[KnowledgeChunk], gold: frozenset[str], k: int) -> Fraction:
    gold_sources = {chunk.source_id for chunk in all_chunks if group_of(chunk) in gold}
    covered = {chunk.source_id for chunk in ranked[:k] if group_of(chunk) in gold}
    return Fraction(len(covered), len(gold_sources))


def macro_mean(values: Sequence[Fraction]) -> Fraction:
    return sum(values, Fraction(0)) / len(values)


# --- one query, and a whole run ------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class QueryOutcome:
    query_id: str
    split: str
    stratum: str
    gold_groups: int
    gold_sources: int
    retrieved: int  # how many chunks the retriever returned (those that share a term with the query)
    first_gold_group_rank: int | None
    gold_group_ranks: tuple[int | None, ...]
    recall: tuple[Fraction, ...]  # at K = 1, 3, 5
    reciprocal_rank: Fraction
    source_coverage: tuple[Fraction, ...]  # at K = 1, 3, 5

    def as_json(self) -> dict:
        return {
            "query_id": self.query_id, "split": self.split, "stratum": self.stratum, "gold_groups": self.gold_groups, "gold_sources": self.gold_sources, "retrieved": self.retrieved,
            "first_gold_group_rank": self.first_gold_group_rank, "gold_group_ranks": list(self.gold_group_ranks),
            "recall": [str(r) for r in self.recall], "reciprocal_rank": str(self.reciprocal_rank), "source_coverage": [str(c) for c in self.source_coverage],
        }


def evaluate(query: FixtureQuery, snapshot: KnowledgeSnapshot, ranked: Sequence[KnowledgeChunk]) -> QueryOutcome:
    gold = gold_groups(snapshot, query)
    ranks = gold_group_ranks(ranked, gold)
    found = [rank for rank in ranks.values() if rank is not None]
    return QueryOutcome(
        query_id=query.query_id, split=query.split, stratum=query.stratum, gold_groups=len(gold), gold_sources=len({c.source_id for c in gold_chunks(snapshot, query)}),
        retrieved=len(ranked), first_gold_group_rank=min(found) if found else None, gold_group_ranks=tuple(ranks.values()),
        recall=tuple(recall_at_k(ranked, gold, k) for k in KS), reciprocal_rank=reciprocal_rank(ranked, gold),
        source_coverage=tuple(source_coverage_at_k(ranked, snapshot.chunks, gold, k) for k in KS),
    )


def summarise(outcomes: Sequence[QueryOutcome]) -> dict:
    """The macro-averages of a set of queries. Exact rationals, with a decimal rendering to four places for reading."""
    def entry(values):
        mean = macro_mean(values)
        return {"exact": str(mean), "decimal": f"{float(mean):.4f}"}

    return {
        "queries": len(outcomes),
        **{f"recall@{k}": entry([o.recall[i] for o in outcomes]) for i, k in enumerate(KS)},
        "mrr": entry([o.reciprocal_rank for o in outcomes]),
        **{f"source_coverage@{k}": entry([o.source_coverage[i] for o in outcomes]) for i, k in enumerate(KS)},
        "queries_with_no_gold_group_retrieved": sum(1 for o in outcomes if o.first_gold_group_rank is None),
    }


def full_ranking_request(snapshot: KnowledgeSnapshot, query: FixtureQuery, scheme_id: str, *, top_k: int | None = None) -> RetrievalRequest:
    return RetrievalRequest(
        kb_id=KB_ID, snapshot_id=snapshot.snapshot_id, scheme_id=scheme_id, text=canonical_query_text(query.text),
        top_k=len(snapshot.chunks) if top_k is None else top_k, max_result_bytes=sum(len(c.text.encode("utf-8")) for c in snapshot.chunks),
    )


def rank_query(port: KnowledgePort, snapshot: KnowledgeSnapshot, query: FixtureQuery, scheme_id: str, *, top_k: int | None = None) -> RetrievalResult:
    result = port.retrieve(full_ranking_request(snapshot, query, scheme_id, top_k=top_k))
    assert isinstance(result, RetrievalResult), result
    return result


def run_benchmark(port_factory: Callable[[KnowledgeSnapshot], KnowledgePort], scheme_id: str) -> dict:
    """Run every fixture query once against the port ``port_factory`` makes over the frozen snapshot, and report."""
    snapshot = build_fixture_snapshot()
    port = port_factory(snapshot)
    outcomes = []
    for query in QUERIES:
        result = rank_query(port, snapshot, query, scheme_id)
        outcomes.append(evaluate(query, snapshot, [hit.chunk for hit in result.hits]))
    report = {
        "fixture_digest": fixture_digest(),
        "scheme_id": scheme_id,
        "snapshot_id": snapshot.snapshot_id,
        "chunks": len(snapshot.chunks),
        "overall": {
            "test": summarise([o for o in outcomes if o.split == "test"]),
            "dev": summarise([o for o in outcomes if o.split == "dev"]),
        },
        "per_stratum": {
            split: {stratum: summarise([o for o in outcomes if o.split == split and o.stratum == stratum]) for stratum in sorted({o.stratum for o in outcomes if o.split == split})}
            for split in ("test", "dev")
        },
        "per_query": [o.as_json() for o in outcomes],
    }
    return report


def lexical_port(snapshot: KnowledgeSnapshot) -> LexicalKnowledgePort:
    return LexicalKnowledgePort(snapshot, kb_id=KB_ID)


def run_lexical_benchmark() -> dict:
    return run_benchmark(lexical_port, LEXICAL_SCHEME_ID)


def report_digest(report: dict) -> str:
    """The digest of a whole report, so two runs can be compared byte for byte."""
    return hashlib.sha256(json.dumps(report, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")).hexdigest()


# --- cost: measured from actual runs, never asserted ---------------------------------------------------------------------------------------


def percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1)]


def measure_warm(repeats: int = 30) -> dict:
    """Index-build time and per-query latency in a warm process: the port is built ``repeats`` times, then every query is asked ``repeats`` times. Milliseconds."""
    snapshot = build_fixture_snapshot()
    builds = []
    for _ in range(repeats):
        started = time.perf_counter()
        lexical_port(snapshot)
        builds.append((time.perf_counter() - started) * 1000)
    port = lexical_port(snapshot)
    requests = [full_ranking_request(snapshot, q, LEXICAL_SCHEME_ID) for q in QUERIES]
    for request in requests:  # one untimed pass, so the first timed call is warm
        port.retrieve(request)
    latencies = []
    for _ in range(repeats):
        for request in requests:
            started = time.perf_counter()
            port.retrieve(request)
            latencies.append((time.perf_counter() - started) * 1000)
    return {
        "index_build_ms": {"median": statistics.median(builds), "p95": percentile(builds, 0.95), "repeats": repeats},
        "query_ms": {"median": statistics.median(latencies), "p95": percentile(latencies, 0.95), "max": max(latencies), "samples": len(latencies)},
    }


def measure_memory() -> dict:
    """The peak memory Python allocated while the snapshot and the index were built and every query asked once (``tracemalloc``: Python allocations, not the process's memory)."""
    tracemalloc.start()
    snapshot = build_fixture_snapshot()
    port = lexical_port(snapshot)
    for query in QUERIES:
        rank_query(port, snapshot, query, LEXICAL_SCHEME_ID)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"peak_bytes": peak, "current_bytes_after": current}


def corpus_footprint() -> dict:
    snapshot = build_fixture_snapshot()
    return {
        "documents": len(DOCUMENTS), "chunks": len(snapshot.chunks), "corpus_bytes_utf8": sum(len(d.text.encode("utf-8")) for d in DOCUMENTS),
        "chunk_text_bytes_utf8": sum(len(c.text.encode("utf-8")) for c in snapshot.chunks), "index_on_disk_bytes": 0,  # the index is in memory only and nothing is written
    }


COLD_STORY = """
import json, sys, time
started = time.perf_counter()
sys.path[:0] = ['src', 'tests/support']
before = set(sys.modules)
from eidos_retrieval_benchmark import lexical_port, rank_query, build_fixture_snapshot, QUERIES, LEXICAL_SCHEME_ID
imported = time.perf_counter()
snapshot = build_fixture_snapshot()
built_snapshot = time.perf_counter()
port = lexical_port(snapshot)
built_index = time.perf_counter()
rank_query(port, snapshot, QUERIES[0], LEXICAL_SCHEME_ID)
first_query = time.perf_counter()
stdlib = set(sys.stdlib_module_names)
third_party = sorted({m.split('.')[0] for m in set(sys.modules) - before if m.split('.')[0] not in stdlib and not m.startswith('_')} - {'eidos', 'eidos_retrieval_benchmark', 'eidos_retrieval_fixture'})
print(json.dumps({
    "import_ms": (imported - started) * 1000, "snapshot_ms": (built_snapshot - imported) * 1000, "index_ms": (built_index - built_snapshot) * 1000,
    "first_query_ms": (first_query - built_index) * 1000, "third_party_modules_loaded": third_party,
}))
"""


def measure_cold() -> dict:
    """One run in a fresh interpreter: import, build the snapshot and the index, and answer the first query. Milliseconds; the third-party modules that run loaded are listed."""
    completed = subprocess.run([sys.executable, "-c", COLD_STORY], capture_output=True, text=True, cwd=ROOT)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def environment() -> dict:
    import platform

    return {"python": platform.python_version(), "implementation": platform.python_implementation(), "platform": platform.platform(), "machine": platform.machine(), "processor": platform.processor()}
