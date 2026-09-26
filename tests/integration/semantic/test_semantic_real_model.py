"""The pinned model, for real, behind the process boundary (decisions.md D-214, D-215, D-220, D-222, D-226; V1.3 Step 5).

These tests start the real worker: the isolated Python 3.13 interpreter, the model library, and the cached ``paraphrase-multilingual-MiniLM-L12-v2`` at its pinned revision. They run only when selected
(``-m real_model``, D-136): they are deselected by default, never skipped, and fail loudly, with what is missing named, if the interpreter or the cached snapshot is not there. Nothing is downloaded and
the network is never used. They run the same under the main interpreter (which spawns the worker) and under the isolated interpreter itself.

What is proven: the cached snapshot is the pinned revision and digests; the worker measures and reports exactly that identity, and the environment it ran in (a recorded environment: a different one is
a different environment, honestly named, to be re-measured and re-recorded, never edited to pass); a model that is not the pinned one is refused before it is loaded; the window is enforced on the
real tokenizer, refusing and never truncating; a text embedded alone, in a batch, again, or in another worker has the bit-for-bit same vector in this environment (no claim beyond it); the retriever over
the real worker answers a full, deterministic ranking of the frozen fixture; a worker that cannot answer in time is a typed timeout; and no file is downloaded.
"""

import hashlib
import importlib.util
import math
import subprocess
import sys

import pytest

from eidos.knowledge import (
    PINNED_MODEL,
    EmbedderFailure,
    EmbedderFailureKind,
    RetrievalFailure,
    RetrievalFailureKind,
    RetrievalRequest,
    RetrievalResult,
    SemanticKnowledgePort,
    build_snapshot,
    cosine_similarity,
    result_problem,
    semantic_scheme_id,
)
from eidos.knowledge import semantic_worker
from eidos.knowledge.semantic_process import IsolatedEmbedder, WorkerLimits
from eidos_knowledge_factories import SCHEME, doc
from eidos_retrieval_benchmark import full_ranking_request
from eidos_retrieval_fixture import KB_ID, QUERIES, build_fixture_snapshot
from eidos_semantic_benchmark import cache_file_count, collect_vectors, model_directory, real_command, semantic_python, start_real_embedder, vector_facts

pytestmark = pytest.mark.real_model

RECORDED_LIBRARIES = (("torch", "2.9.0+cpu"), ("sentence-transformers", "5.1.1"), ("transformers", "4.57.1"), ("tokenizers", "0.22.1"), ("numpy", "2.2.1"))
RECORDED_FILES = [
    "1_Pooling/config.json", "README.md", "config.json", "config_sentence_transformers.json", "model.safetensors", "modules.json", "sentence_bert_config.json",
    "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json",
]
TOKENIZER_SHA256 = "2c3387be76557bd40970cec13153b3bbf80407865484b209e655e5e4729076b8"


@pytest.fixture(scope="module")
def embedder():
    cache_before = cache_file_count()
    with start_real_embedder() as started:
        yield started
    assert cache_file_count() == cache_before, "the worker changed the model cache: something was downloaded or written"


# --- the snapshot and the identity -----------------------------------------------------------------------------------------------------


def test_the_cached_snapshot_is_the_pinned_revision_with_the_recorded_files_and_digests():
    directory = model_directory()
    assert directory.name == PINNED_MODEL.revision
    assert sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()) == RECORDED_FILES
    weights, aggregate = semantic_worker.directory_digests(directory)
    assert (weights, aggregate) == (PINNED_MODEL.weights_sha256, PINNED_MODEL.directory_sha256)
    assert hashlib.sha256((directory / "tokenizer.json").read_bytes()).hexdigest() == TOKENIZER_SHA256


def test_the_worker_reports_the_pinned_identity_and_the_recorded_environment_it_measured(embedder):
    ready = embedder.ready
    assert ready.identity == PINNED_MODEL and (PINNED_MODEL.dimension, PINNED_MODEL.max_pieces) == (384, 128)
    environment = ready.environment
    assert environment.python_version == "3.13.1" and environment.implementation == "CPython"
    assert environment.libraries == RECORDED_LIBRARIES
    assert (environment.threads, environment.device, environment.dtype) == (1, "cpu", "float32")
    assert ready.import_seconds > 0 and ready.verify_seconds > 0 and ready.load_seconds > 0


def test_the_isolated_interpreter_is_python_3_13_1_and_the_main_environment_of_the_project_has_no_model_library():
    completed = subprocess.run([semantic_python(), "-I", "-c", "import sys; print(sys.version_info[:3])"], capture_output=True, text=True, timeout=60)
    assert completed.stdout.strip() == "(3, 13, 1)"
    if sys.version_info[:2] == (3, 12):  # the project's main environment: D-226 ruling 2, nothing of the model library is installed in it
        assert [name for name in ("torch", "sentence_transformers", "transformers", "tokenizers") if importlib.util.find_spec(name) is not None] == []


def test_a_model_that_is_not_the_pinned_one_is_refused_by_the_worker_before_it_is_loaded():
    wrong = PINNED_MODEL.model_copy(update={"weights_sha256": "0" * 64})
    limits = WorkerLimits()
    refused = IsolatedEmbedder.start(real_command(limits, expected=wrong), expected=wrong, limits=limits)
    assert isinstance(refused, EmbedderFailure) and refused.kind is EmbedderFailureKind.IDENTITY_MISMATCH
    assert "the worker could not serve (identity_mismatch)" in refused.message and "weights digest" in refused.message  # the worker's own refusal, made before the library was imported


def test_a_worker_that_reports_another_model_than_the_one_expected_is_refused_by_the_client():
    wrong = PINNED_MODEL.model_copy(update={"weights_sha256": "0" * 64})
    limits = WorkerLimits()
    refused = IsolatedEmbedder.start(real_command(limits), expected=wrong, limits=limits)  # the worker was told the pinned model, and loaded it
    assert isinstance(refused, EmbedderFailure) and refused.kind is EmbedderFailureKind.IDENTITY_MISMATCH
    assert "the worker's model has weights_sha256" in refused.message


# --- vectors ---------------------------------------------------------------------------------------------------------------------------


TEXTS = ["The tidal barrier sensors must report normal readings.", "Ein Satz auf Deutsch, der etwas ganz anderes sagt.", "inspection checklist before restart"]


def test_a_vector_has_the_models_dimension_is_finite_and_is_not_normalised(embedder):
    items = embedder.embed(TEXTS)
    assert all(item.vector is not None and len(item.vector) == 384 and all(math.isfinite(x) for x in item.vector) for item in items)
    norms = [math.sqrt(math.fsum(x * x for x in item.vector)) for item in items]
    assert all(abs(norm - 1.0) > 1e-3 for norm in norms), "the model was asked for no normalisation: cosine is scale-free"


def test_a_text_embedded_alone_in_a_batch_again_or_in_another_worker_has_the_same_bits_here(embedder):
    alone = [embedder.embed([text])[0] for text in TEXTS]
    assert list(embedder.embed(TEXTS)) == alone  # batch position changes nothing: each text is encoded on its own
    assert list(embedder.embed(list(reversed(TEXTS)))) == list(reversed(alone))
    assert [embedder.embed([text])[0] for text in TEXTS] == alone  # and again
    with start_real_embedder() as other:
        assert [other.embed([text])[0] for text in TEXTS] == alone


def test_a_text_is_its_own_nearest_neighbour_and_a_different_text_is_not_identical(embedder):
    a, b = (item.vector for item in embedder.embed(TEXTS[:2]))
    assert cosine_similarity(a, a) == pytest.approx(1.0, abs=1e-12)
    assert cosine_similarity(a, b) < 1.0 - 1e-6


# --- the window, on the real tokenizer -------------------------------------------------------------------------------------------------------


def test_the_window_is_enforced_on_the_real_tokenizer_refusing_and_never_truncating(embedder):
    over = embedder.embed([" ".join(["word"] * 400)])[0]
    assert over.pieces > 128 and over.vector is None
    at_window = next(item for words in range(1, 200) if (item := embedder.embed([" ".join(["the"] * words)])[0]).pieces == 128 or item.pieces > 128)
    assert at_window.pieces == 128 and at_window.vector is not None
    one_over = embedder.embed([" ".join(["the"] * (128 - 2 + 1))])[0]
    assert one_over.pieces == 129 and one_over.vector is None
    assert embedder.running


def test_the_frozen_fixture_fits_the_window_and_its_piece_counts_are_the_recorded_ones(embedder):
    facts = vector_facts(collect_vectors(embedder, build_fixture_snapshot()))
    assert facts["chunk_pieces"] == {"min": 53, "max": 82, "count": 53}
    assert facts["query_pieces"] == {"min": 11, "max": 36, "count": 36}
    assert facts["token_piece_rejections"] == 0 and facts["dimension"] == [384] and facts["window"] == 128


# --- the retriever over the real worker ------------------------------------------------------------------------------------------------------


def test_the_retriever_over_the_real_worker_answers_a_full_valid_deterministic_ranking_of_the_fixture(embedder):
    snapshot = build_fixture_snapshot()
    port = SemanticKnowledgePort.open(snapshot, kb_id=KB_ID, embedder=embedder)
    assert isinstance(port, SemanticKnowledgePort)
    scheme = semantic_scheme_id(PINNED_MODEL)
    for query in QUERIES:
        request = full_ranking_request(snapshot, query, scheme)
        result = port.retrieve(request)
        assert isinstance(result, RetrievalResult) and result_problem(request, result) is None
        assert len(result.hits) == 53 and {hit.chunk.chunk_id for hit in result.hits} == {chunk.chunk_id for chunk in snapshot.chunks}
        assert result.score_kind == "semantic-cosine-v1" and result.scheme_id == scheme
        assert all(-1.0 <= hit.score <= 1.0 for hit in result.hits)
        assert port.retrieve(request) == result


def test_a_chunk_over_the_window_makes_the_real_retriever_unavailable_and_names_it(embedder):
    snapshot = build_snapshot((doc("s1", "a short chunk"), doc("s2", " ".join(["word"] * 300))), SCHEME.model_copy(update={"max_words": 400}))
    result = SemanticKnowledgePort.open(snapshot, kb_id=KB_ID, embedder=embedder)
    assert isinstance(result, RetrievalFailure) and result.kind is RetrievalFailureKind.UNAVAILABLE
    assert "never truncated" in result.message and "over the model's window of 128" in result.message
    assert embedder.running


def test_a_query_over_the_window_is_refused_as_a_request_mismatch_and_the_port_still_serves(embedder):
    snapshot = build_fixture_snapshot()
    port = SemanticKnowledgePort.open(snapshot, kb_id=KB_ID, embedder=embedder)
    scheme = semantic_scheme_id(PINNED_MODEL)
    long_query = RetrievalRequest(kb_id=KB_ID, snapshot_id=snapshot.snapshot_id, scheme_id=scheme, text=" ".join(["word"] * 300), top_k=3, max_result_bytes=10**6)
    refused = port.retrieve(long_query)
    assert isinstance(refused, RetrievalFailure) and refused.kind is RetrievalFailureKind.REQUEST_MISMATCH and "never truncated" in refused.message
    assert isinstance(port.retrieve(full_ranking_request(snapshot, QUERIES[0], scheme)), RetrievalResult)


# --- a worker that cannot answer in time -----------------------------------------------------------------------------------------------------


def test_a_worker_that_cannot_answer_in_time_is_a_typed_timeout_and_is_stopped_and_the_retrieval_says_unavailable():
    limits = WorkerLimits(request_timeout_seconds=0.001)
    started = IsolatedEmbedder.start(real_command(limits), expected=PINNED_MODEL, limits=limits)
    assert isinstance(started, IsolatedEmbedder), started
    result = started.embed(["a text"])
    assert isinstance(result, EmbedderFailure) and result.kind is EmbedderFailureKind.TIMEOUT
    assert not started.running
    snapshot = build_snapshot((doc("s1", "alpha beta"),), SCHEME)
    outcome = SemanticKnowledgePort.open(snapshot, kb_id=KB_ID, embedder=started)
    assert isinstance(outcome, RetrievalFailure) and outcome.kind is RetrievalFailureKind.UNAVAILABLE and "not running" in outcome.message
