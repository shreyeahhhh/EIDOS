"""How much the thread count and the batch size move the model's vectors, and whether that moves the ranking or the benchmark report (decisions.md D-220, D-226 reading 9; V1.3 Step 5).

A measurement, run by hand in the isolated Python 3.13 interpreter, never by the test suite:

    py -3.13 tests/support/semantic_sensitivity_experiment.py OUT.json

The pinned model is loaded from its local snapshot with the network refused, exactly as the worker does. The execution configuration the worker fixes (one thread, each text encoded alone) is the baseline;
every other configuration encodes the same 53 chunks and 36 queries of the frozen fixture and is compared with it. The same ``SemanticKnowledgePort`` and the same benchmark runner produce the rankings and
the report, so the question answered is exactly the one that matters: does a different execution configuration on this machine change the answer. It states what was measured on this machine in this
environment; it makes no claim about any other.
"""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests" / "support")]

from eidos.knowledge import PINNED_MODEL, EmbeddedText, SemanticKnowledgePort, semantic_scheme_id, semantic_worker  # noqa: E402
from eidos.knowledge.semantic_process import hub_model_directory  # noqa: E402
from eidos_retrieval_benchmark import rank_query, report_digest, run_benchmark  # noqa: E402
from eidos_retrieval_fixture import KB_ID, QUERIES, build_fixture_snapshot, fixture_digest  # noqa: E402
from eidos_semantic_benchmark import FROZEN_DIGEST, HUB_ROOT, compare_vectors, score_gaps  # noqa: E402

semantic_worker.refuse_network()
import torch  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

ALL_THREADS = os.cpu_count()
CONFIGURATIONS = [  # (name, threads, batch size)
    ("baseline_1_thread_batch_1", 1, 1),
    ("baseline_again", 1, 1),
    ("1_thread_batch_16", 1, 16),
    ("4_threads_batch_1", 4, 1),
    ("all_threads_batch_1", ALL_THREADS, 1),
    ("all_threads_batch_16", ALL_THREADS, 16),
]


class InProcessEmbedder:
    """The model in this process, with a chosen thread count and batch size, behind the same ``Embedder`` protocol the isolated worker serves."""

    identity = PINNED_MODEL

    def __init__(self, model: SentenceTransformer, batch_size: int):
        self.model, self.batch_size = model, batch_size

    def embed(self, texts):
        pieces = [len(self.model.tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"]) for text in texts]
        assert all(p <= PINNED_MODEL.max_pieces for p in pieces), "the fixture fits the window"
        vectors = self.model.encode(list(texts), batch_size=self.batch_size, convert_to_numpy=True, normalize_embeddings=False, show_progress_bar=False)
        return tuple(EmbeddedText(pieces=p, vector=tuple(float(x) for x in v)) for p, v in zip(pieces, vectors))


def main(out: Path) -> None:
    assert fixture_digest() == FROZEN_DIGEST
    directory = hub_model_directory(HUB_ROOT, PINNED_MODEL.model, PINNED_MODEL.revision)
    weights, aggregate = semantic_worker.directory_digests(directory)
    assert (weights, aggregate) == (PINNED_MODEL.weights_sha256, PINNED_MODEL.directory_sha256)
    threads_at_start = torch.get_num_threads()  # what the library chose before this script set anything: the worker's offline setup pins it to one through the environment
    model = SentenceTransformer(str(directory), device="cpu", trust_remote_code=False, local_files_only=True)
    model.eval()
    snapshot = build_fixture_snapshot()
    texts = [chunk.text for chunk in snapshot.chunks] + [query.text for query in QUERIES]
    scheme = semantic_scheme_id(PINNED_MODEL)
    results, baseline = {}, None
    for name, threads, batch in CONFIGURATIONS:
        torch.set_num_threads(threads)
        embedder = InProcessEmbedder(model, batch)
        started = time.perf_counter()
        items = []
        for offset in range(0, len(texts), 16):
            group = texts[offset : offset + 16]
            items.extend(zip(group, embedder.embed(group) if batch != 1 else tuple(embedder.embed([t])[0] for t in group)))
        embed_seconds = time.perf_counter() - started
        port = SemanticKnowledgePort.open(snapshot, kb_id=KB_ID, embedder=embedder, batch_size=16 if batch != 1 else 1)
        assert isinstance(port, SemanticKnowledgePort), port
        rankings = {q.query_id: [(hit.chunk.chunk_id, hit.score) for hit in rank_query(port, snapshot, q, scheme).hits] for q in QUERIES}
        report = run_benchmark(lambda s: SemanticKnowledgePort.open(s, kb_id=KB_ID, embedder=embedder, batch_size=16 if batch != 1 else 1), scheme)
        entry = {"threads": torch.get_num_threads(), "batch_size": batch, "embed_seconds_wall": embed_seconds, "report_digest": report_digest(report)}
        if baseline is None:
            baseline = {"items": items, "rankings": rankings, "digest": entry["report_digest"], "report": report}
            entry["is_baseline"] = True
        else:
            entry["vectors_against_baseline"] = compare_vectors(baseline["items"], items)
            entry["queries_whose_ranking_of_chunks_differs"] = sum(1 for q in rankings if [c for c, _ in rankings[q]] != [c for c, _ in baseline["rankings"][q]])
            entry["largest_score_difference"] = max(abs(a[1] - b[1]) for q in rankings for a, b in zip(rankings[q], baseline["rankings"][q]))
            entry["report_digest_equals_baseline"] = entry["report_digest"] == baseline["digest"]
            entry["overall_test_metrics_equal_baseline"] = report["overall"]["test"] == baseline["report"]["overall"]["test"]
        results[name] = entry
    output = {
        "fixture_digest": fixture_digest(), "python": sys.version, "torch": torch.__version__, "torch_threads_at_start": threads_at_start, "logical_processors": ALL_THREADS,
        "score_gaps_baseline": score_gaps(baseline["rankings"]), "configurations": results,
    }
    out.write_text(json.dumps(output, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps({name: {k: v for k, v in e.items() if k != "vectors_against_baseline"} | ({"vectors": e["vectors_against_baseline"]} if "vectors_against_baseline" in e else {}) for name, e in results.items()}, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
