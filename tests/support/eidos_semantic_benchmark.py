"""The semantic measurement: the real model behind the process boundary, on the frozen retrieval fixture (decisions.md D-213, D-226; V1.3 Step 5).

The semantic retriever is measured with the SAME fixture, gold labels, query text, strata, metrics and runner as the lexical baseline (``eidos_retrieval_benchmark``): nothing about the benchmark is
modified, and the fixture's digest is checked before anything is run. **Nothing here judges a retriever.** There is no threshold, margin or verdict (D-226 ruling 1); a report holds measurements, and
a reader compares them. No parameter is tuned: the execution configuration (CPU, float32, one thread, one text per forward pass, no normalisation, no prefix) was fixed before the first run.

What is added to the lexical report are the facts only a semantic run has, each taken from an actual run and never asserted: the model's revision and digests and its dimension, the environment the model
ran in, how long the worker took to start and to load the model, how long embedding the corpus and a query took (in the worker and through the boundary), warm and cold retrieval latency, the memory
the worker and this process used, the model's size on disk, how many texts the window refused, how much the vectors and the ranking varied between repeated runs and workers, the smallest gap between
adjacent scores (how much jitter a ranking could absorb) and the resolution of the environment. They describe one machine on one day, in one environment, and are recorded with it.

Run as ``python tests/support/eidos_semantic_benchmark.py OUT.json`` from the repository root (the main interpreter; the worker runs in the isolated one).
"""

import json
import os
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if __name__ == "__main__":
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests" / "support")]

from eidos.knowledge import PINNED_MODEL, EmbeddedText, EmbedderFailure, KnowledgeSnapshot, RetrievalResult, SemanticKnowledgePort, semantic_scheme_id  # noqa: E402
from eidos.knowledge.semantic_process import IsolatedEmbedder, WorkerLimits, hub_model_directory, semantic_worker_command  # noqa: E402
from eidos_retrieval_benchmark import (  # noqa: E402
    environment,
    full_ranking_request,
    percentile,
    rank_query,
    report_digest,
    run_benchmark,
    run_lexical_benchmark,
)
from eidos_retrieval_fixture import DOCUMENTS, KB_ID, QUERIES, build_fixture_snapshot, fixture_digest  # noqa: E402

FROZEN_DIGEST = "93db0b1f14c7c444073f86c763e891f1ccab92e5259f62351305b374db57df6b"
HUB_ROOT = Path.home() / ".cache" / "huggingface" / "hub"


# --- the environment: found, or the failure says exactly what is missing (a real-model test never skips) ------------------------------------------


def semantic_python() -> str:
    """The isolated interpreter that holds the model library: ``EIDOS_SEMANTIC_PYTHON``, or Python 3.13 as the launcher finds it."""
    given = os.environ.get("EIDOS_SEMANTIC_PYTHON")
    if given:
        assert Path(given).is_file(), f"EIDOS_SEMANTIC_PYTHON names {given}, which is not a file"
        return given
    try:
        completed = subprocess.run(["py", "-3.13", "-c", "import sys; print(sys.executable)"], capture_output=True, text=True, timeout=60)
    except OSError as error:
        raise AssertionError(f"no isolated Python 3.13 interpreter: set EIDOS_SEMANTIC_PYTHON ({error})") from error
    assert completed.returncode == 0 and completed.stdout.strip(), f"no isolated Python 3.13 interpreter: set EIDOS_SEMANTIC_PYTHON ({completed.stderr.strip()})"
    return completed.stdout.strip()


def model_directory() -> Path:
    """The cached snapshot of the pinned revision: ``EIDOS_SEMANTIC_MODEL_DIR``, or the local cache of the model library. It must exist: nothing is downloaded."""
    given = os.environ.get("EIDOS_SEMANTIC_MODEL_DIR")
    directory = Path(given) if given else hub_model_directory(HUB_ROOT, PINNED_MODEL.model, PINNED_MODEL.revision)
    assert directory.is_dir(), f"the pinned model is not cached at {directory}: this test never downloads it"
    return directory


def real_command(limits: WorkerLimits, *, python: str | None = None, directory: Path | None = None, expected=PINNED_MODEL) -> tuple[str, ...]:
    return semantic_worker_command(python or semantic_python(), directory or model_directory(), expected, limits)


def start_real_embedder(limits: WorkerLimits | None = None) -> IsolatedEmbedder:
    limits = limits or WorkerLimits()
    embedder = IsolatedEmbedder.start(real_command(limits), expected=PINNED_MODEL, limits=limits)
    assert isinstance(embedder, IsolatedEmbedder), f"the real worker did not start: {embedder}"
    return embedder


def cache_file_count() -> int:
    return sum(1 for path in HUB_ROOT.rglob("*") if path.is_file()) if HUB_ROOT.is_dir() else 0


def directory_bytes(directory: Path) -> tuple[int, int]:
    sizes = [path.stat().st_size for path in directory.rglob("*") if path.is_file()]
    return len(sizes), sum(sizes)


def process_memory(pid: int) -> dict | None:
    """The peak and current working set and the peak page file of a process, as Windows reports them; ``None`` where this platform has no such counter here."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32, psapi = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    handle = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)  # PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
    if not handle:
        return None
    try:
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return {"peak_working_set_bytes": counters.PeakWorkingSetSize, "working_set_bytes": counters.WorkingSetSize, "peak_pagefile_bytes": counters.PeakPagefileUsage}
    finally:
        kernel32.CloseHandle(handle)


# --- a timing wrapper: what an embedding cost through the boundary and inside the worker ---------------------------------------------------------


class TimedEmbedder:
    """An ``Embedder`` that passes every call through and notes how long it took (wall, through the boundary) and how long the worker says it spent."""

    def __init__(self, inner: IsolatedEmbedder):
        self.inner = inner
        self.calls: list[dict] = []

    @property
    def identity(self):
        return self.inner.identity

    def embed(self, texts: Sequence[str]):
        started = time.perf_counter()
        answer = self.inner.embed(texts)
        wall = time.perf_counter() - started
        self.calls.append({"texts": len(texts), "wall_seconds": wall, "worker_seconds": self.inner.last_worker_seconds})
        return answer


def milliseconds(values: Sequence[float]) -> dict:
    return {"median": statistics.median(values), "p95": percentile(values, 0.95), "max": max(values), "min": min(values), "samples": len(values)}


# --- the benchmark itself: the same runner as the lexical baseline --------------------------------------------------------------------------------


def run_semantic_benchmark(embedder, *, batch_size: int = 16) -> dict:
    assert fixture_digest() == FROZEN_DIGEST, "the fixture is not the frozen one: nothing is run"

    def factory(snapshot: KnowledgeSnapshot):
        port = SemanticKnowledgePort.open(snapshot, kb_id=KB_ID, embedder=embedder, batch_size=batch_size)
        assert isinstance(port, SemanticKnowledgePort), port
        return port

    return run_benchmark(factory, semantic_scheme_id(PINNED_MODEL))


def collect_vectors(embedder: IsolatedEmbedder, snapshot: KnowledgeSnapshot, *, batch_size: int = 16) -> list[tuple[str, EmbeddedText]]:
    """Every chunk's and then every query's raw embedding (pieces and vector), as ``(text, embedding)`` in canonical order, the way the port asks for them. A text that occurs twice (a mirrored chunk) is listed twice."""
    texts = [chunk.text for chunk in snapshot.chunks] + [query.text for query in QUERIES]
    items: list[EmbeddedText] = []
    for offset in range(0, len(texts), batch_size):
        answer = embedder.embed(texts[offset : offset + batch_size])
        assert not isinstance(answer, EmbedderFailure), answer
        items.extend(answer)
    return list(zip(texts, items))


def vector_facts(collected: list[tuple[str, EmbeddedText]]) -> dict:
    items = [item for _, item in collected]
    chunk_count = len(build_fixture_snapshot().chunks)
    chunk_pieces, query_pieces = [i.pieces for i in items[:chunk_count]], [i.pieces for i in items[chunk_count:]]
    return {
        "chunk_pieces": {"min": min(chunk_pieces), "max": max(chunk_pieces), "count": len(chunk_pieces)},
        "query_pieces": {"min": min(query_pieces), "max": max(query_pieces), "count": len(query_pieces)},
        "window": PINNED_MODEL.max_pieces,
        "token_piece_rejections": sum(1 for i in items if i.vector is None),
        "dimension": sorted({len(i.vector) for i in items if i.vector is not None}),
    }


def compare_vectors(first: list[tuple[str, EmbeddedText]], second: list[tuple[str, EmbeddedText]]) -> dict:
    """How two collections of embeddings of the same texts differ: bit for bit, by component and by the largest difference."""
    assert [text for text, _ in first] == [text for text, _ in second]
    identical, components, different_components, largest = 0, 0, 0, 0.0
    for (_, one), (_, other) in zip(first, second):
        a, b = one.vector, other.vector
        if a == b:
            identical += 1
        for x, y in zip(a, b):
            components += 1
            if x != y:
                different_components += 1
                largest = max(largest, abs(x - y))
    return {"texts": len(first), "identical_texts": identical, "components": components, "different_components": different_components, "largest_absolute_difference": largest}


def rankings_of(embedder, snapshot: KnowledgeSnapshot) -> dict:
    """The full ranking, with its scores, of every fixture query."""
    port = SemanticKnowledgePort.open(snapshot, kb_id=KB_ID, embedder=embedder)
    assert isinstance(port, SemanticKnowledgePort), port
    scheme = semantic_scheme_id(PINNED_MODEL)
    return {query.query_id: [(hit.chunk.chunk_id, hit.score) for hit in rank_query(port, snapshot, query, scheme).hits] for query in QUERIES}


def score_gaps(rankings: dict) -> dict:
    """The gaps between adjacent scores in every full ranking: how large a change of a score could move a rank."""
    gaps = [a[1] - b[1] for ranking in rankings.values() for a, b in zip(ranking, ranking[1:])]
    nonzero = [g for g in gaps if g > 0]
    return {"adjacent_pairs": len(gaps), "exact_ties": len(gaps) - len(nonzero), "smallest_nonzero_gap": min(nonzero), "pairs_closer_than_1e-6": sum(1 for g in nonzero if g < 1e-6), "pairs_closer_than_1e-4": sum(1 for g in nonzero if g < 1e-4)}


def measure_determinism() -> dict:
    """The same texts embedded twice in one worker and once in a second worker: are the vectors, the rankings and the report identical, bit for bit."""
    snapshot = build_fixture_snapshot()
    with start_real_embedder() as first:
        a = collect_vectors(first, snapshot)
        b = collect_vectors(first, snapshot)
        rankings_a, report_a = rankings_of(first, snapshot), run_semantic_benchmark(first)
        rankings_a_again, report_a_again = rankings_of(first, snapshot), run_semantic_benchmark(first)
        first_pid = first.pid
    with start_real_embedder() as second:
        c = collect_vectors(second, snapshot)
        rankings_c, report_c = rankings_of(second, snapshot), run_semantic_benchmark(second)
        second_pid = second.pid
    return {
        "same_worker_twice": {"vectors": compare_vectors(a, b), "rankings_with_scores_identical": rankings_a == rankings_a_again, "report_digests_identical": report_digest(report_a) == report_digest(report_a_again)},
        "two_workers": {"vectors": compare_vectors(a, c), "rankings_with_scores_identical": rankings_a == rankings_c, "report_digests_identical": report_digest(report_a) == report_digest(report_c), "distinct_processes": first_pid != second_pid},
        "score_gaps": score_gaps(rankings_a),
        "report_digest": report_digest(report_a),
    }


def measure_cost(repeats: int = 5) -> dict:
    """Start, index and query cost, cold and warm, and the memory the worker and this process used. Seconds and milliseconds from actual runs; an environment's numbers, never asserted."""
    snapshot = build_fixture_snapshot()
    scheme = semantic_scheme_id(PINNED_MODEL)
    cache_before = cache_file_count()
    started = time.perf_counter()
    inner = start_real_embedder()
    start_seconds = time.perf_counter() - started
    timed = TimedEmbedder(inner)
    try:
        ready = inner.ready
        memory_after_load = process_memory(inner.pid)
        tracemalloc.start()
        started = time.perf_counter()
        port = SemanticKnowledgePort.open(snapshot, kb_id=KB_ID, embedder=timed, batch_size=16)
        open_seconds = time.perf_counter() - started
        assert isinstance(port, SemanticKnowledgePort), port
        index_calls = list(timed.calls)
        timed.calls.clear()
        requests = [full_ranking_request(snapshot, query, scheme) for query in QUERIES]
        started = time.perf_counter()
        first = port.retrieve(requests[0])  # the first query the worker has answered after the corpus: cold in the sense of nothing repeated
        first_query_ms = (time.perf_counter() - started) * 1000
        assert isinstance(first, RetrievalResult), first
        first_embed = dict(timed.calls[0])
        timed.calls.clear()
        retrieval_ms, embed_wall_ms, embed_worker_ms = [], [], []
        for _ in range(repeats):
            for request in requests:
                before = len(timed.calls)
                started = time.perf_counter()
                port.retrieve(request)
                retrieval_ms.append((time.perf_counter() - started) * 1000)
                (call,) = timed.calls[before:]
                embed_wall_ms.append(call["wall_seconds"] * 1000)
                embed_worker_ms.append(call["worker_seconds"] * 1000)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        memory_after_queries = process_memory(inner.pid)
        directory = model_directory()
        files, size = directory_bytes(directory)
        return {
            "worker": {
                "start_seconds_wall": start_seconds, "import_seconds": ready.import_seconds, "digest_verification_seconds": ready.verify_seconds, "model_load_seconds": ready.load_seconds,
                "environment": ready.environment.model_dump(mode="json"),
            },
            "index": {
                "chunks": len(snapshot.chunks), "embed_calls": len(index_calls), "open_seconds_wall": open_seconds, "open_seconds_in_worker": sum(c["worker_seconds"] for c in index_calls),
                "per_chunk_ms_in_worker": sum(c["worker_seconds"] for c in index_calls) / len(snapshot.chunks) * 1000,
            },
            "first_query": {"retrieval_ms": first_query_ms, "embed_wall_ms": first_embed["wall_seconds"] * 1000, "embed_worker_ms": first_embed["worker_seconds"] * 1000},
            "warm_query": {
                "retrieval_ms": milliseconds(retrieval_ms), "embed_through_boundary_ms": milliseconds(embed_wall_ms), "embed_in_worker_ms": milliseconds(embed_worker_ms),
                "port_compute_ms": milliseconds([r - e for r, e in zip(retrieval_ms, embed_wall_ms)]), "repeats": repeats,
            },
            "memory": {
                "worker_after_model_load": memory_after_load, "worker_after_queries": memory_after_queries,
                "this_process_python_allocations": {"peak_bytes": peak, "current_bytes_after": current, "scope": "SemanticKnowledgePort.open and one full pass of queries, tracemalloc"},
            },
            "footprint": {"model_directory_files": files, "model_directory_bytes": size, "vectors_in_memory": len(snapshot.chunks) * PINNED_MODEL.dimension, "index_on_disk_bytes": 0},
            "hugging_face_cache_files": {"before": cache_before, "after": cache_file_count()},
            "requests_answered": inner.requests,
        }
    finally:
        inner.close()


def measure_window_probe() -> dict:
    """The window enforced on the real tokenizer: a text of 400 words is refused with its piece count, and a text exactly at the window is embedded."""
    with start_real_embedder() as embedder:
        long_item = embedder.embed([" ".join(["word"] * 400)])[0]
        at_window = None
        for words in range(1, 200):
            item = embedder.embed([" ".join(["the"] * words)])[0]
            if item.pieces == PINNED_MODEL.max_pieces:
                at_window = {"words": words, "pieces": item.pieces, "embedded": item.vector is not None}
                break
        over = embedder.embed([" ".join(["the"] * (at_window["words"] + 1))])[0]
        return {
            "text_of_400_words": {"pieces": long_item.pieces, "refused": long_item.vector is None},
            "text_at_the_window": at_window,
            "text_one_piece_over": {"pieces": over.pieces, "refused": over.vector is None},
        }


HEADLINE = ("recall@1", "recall@3", "recall@5", "mrr", "source_coverage@1", "source_coverage@3", "source_coverage@5")


def side_by_side(lexical: dict, semantic: dict) -> dict:
    """Both reports' headline numbers next to each other, exact and to four places. It states no difference and no judgement: it puts two measurements where they can be read together."""
    def rows(split: str) -> dict:
        return {
            name: {"lexical": lexical["overall"][split][name], "semantic": semantic["overall"][split][name]} for name in HEADLINE
        }

    strata = {
        split: {
            stratum: {name: {"lexical": lexical["per_stratum"][split][stratum][name], "semantic": semantic["per_stratum"][split][stratum][name]} for name in HEADLINE}
            for stratum in lexical["per_stratum"][split]
        }
        for split in ("test", "dev")
    }
    return {"test": rows("test"), "dev": rows("dev"), "per_stratum": strata}


def main(out: Path) -> None:
    assert fixture_digest() == FROZEN_DIGEST, "the fixture is not the frozen one"
    snapshot = build_fixture_snapshot()
    lexical = run_lexical_benchmark()
    with start_real_embedder() as embedder:
        started = time.perf_counter()
        semantic = run_semantic_benchmark(embedder)
        benchmark_seconds = time.perf_counter() - started
        vectors = vector_facts(collect_vectors(embedder, snapshot))
    output = {
        "fixture_digest": fixture_digest(),
        "snapshot_id": snapshot.snapshot_id,
        "model": PINNED_MODEL.model_dump(mode="json"),
        "scheme_id": semantic_scheme_id(PINNED_MODEL),
        "main_environment": environment(),
        "isolated_interpreter": semantic_python(),
        "semantic_report": semantic,
        "semantic_report_digest": report_digest(semantic),
        "lexical_report_digest": report_digest(lexical),
        "side_by_side": side_by_side(lexical, semantic),
        "benchmark_seconds_wall": benchmark_seconds,
        "vector_facts": vectors,
        "window_probe": measure_window_probe(),
        "determinism": measure_determinism(),
        "cost": measure_cost(),
        "documents": len(DOCUMENTS),
        "platform": platform.platform(),
    }
    out.write_text(json.dumps(output, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps({"semantic_report_digest": output["semantic_report_digest"], "test": semantic["overall"]["test"], "dev": semantic["overall"]["dev"]}, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
