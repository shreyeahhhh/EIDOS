"""The pure half of semantic retrieval: the pinned identity, exact cosine, and ``SemanticKnowledgePort`` over a fake embedder (decisions.md D-208, D-214, D-215, D-219, D-220, D-226; V1.3 Step 5).

No model, no process and no library is involved: the embedder is a table. What is proven is everything the main runtime decides: the model is pinned by revision and digests; similarity is exact
(``math.fsum``, one division, clamped, never rounded); hits are ordered by score and then ``chunk_id`` and ranked from 1; ``top_k`` and the byte bound only ever cut or refuse the same ranking;
every chunk is a candidate; a text over the model's window is refused and never truncated; nothing an embedder returns is trusted (a wrong count, dimension or length, a non-finite value); every
embedder failure becomes a typed retrieval failure; and the answer depends on nothing but the snapshot, the vectors and the request.
"""

import math
import random
import threading

import pytest

from eidos.knowledge import (
    PINNED_MODEL,
    SEMANTIC_SCORE_KIND,
    EmbeddedText,
    EmbedderFailure,
    EmbedderFailureKind,
    KnowledgePort,
    RetrievalFailure,
    RetrievalFailureKind,
    RetrievalRequest,
    RetrievalResult,
    SemanticKnowledgePort,
    SemanticModelIdentity,
    build_snapshot,
    canonical_query_text,
    cosine_similarity,
    result_problem,
    semantic_scheme_id,
)
from eidos.knowledge import semantic as semantic_module
from eidos.knowledge.semantic import vector_norm
from eidos_knowledge_factories import SCHEME, doc

E_ACUTE = chr(0xE9)
IDENTITY = SemanticModelIdentity(model="test/stub", revision="a" * 40, weights_sha256="b" * 64, directory_sha256="c" * 64, dimension=3, max_pieces=10)
SCHEME_ID = semantic_scheme_id(IDENTITY)
TINY = build_snapshot((doc("s1", "alpha beta beta"), doc("s2", "alpha gamma"), doc("s3", "delta delta delta delta")), SCHEME)
BY_TEXT = {chunk.text: chunk for chunk in TINY.chunks}
BETA, GAMMA, DELTA = BY_TEXT["alpha beta beta"], BY_TEXT["alpha gamma"], BY_TEXT["delta delta delta delta"]
VECTORS = {BETA.text: (1.0, 0.0, 0.0), GAMMA.text: (1.0, 1.0, 0.0), DELTA.text: (0.0, 0.0, 1.0), "alpha": (1.0, 0.5, 0.0)}


def words_plus_two(text: str) -> int:
    return len(text.split()) + 2


class FakeEmbedder:
    """A table for an embedder: a text's vector is looked up, its pieces are its words plus two. ``replace`` overrides the answer for one text, ``transform`` the whole answer of a call."""

    def __init__(self, vectors=None, *, identity=IDENTITY, replace=None, transform=None, failures=None):
        self.identity = identity
        self.vectors = dict(VECTORS if vectors is None else vectors)
        self.replace = replace or {}
        self.transform = transform
        self.failures = failures or {}  # call index -> the failure returned by that call
        self.calls: list[tuple[str, ...]] = []

    def embed(self, texts):
        index = len(self.calls)
        self.calls.append(tuple(texts))
        if index in self.failures:
            return self.failures[index]
        answer = tuple(self.replace.get(text) or EmbeddedText(pieces=words_plus_two(text), vector=self.vectors[text]) for text in texts)
        return self.transform(answer) if self.transform else answer


def opened(embedder=None, snapshot=TINY, **kwargs) -> SemanticKnowledgePort:
    port = SemanticKnowledgePort.open(snapshot, kb_id="kb1", embedder=embedder or FakeEmbedder(), **kwargs)
    assert isinstance(port, SemanticKnowledgePort), port
    return port


def ask(port, text="alpha", *, top_k=50, max_bytes=10**6, snapshot=TINY, **overrides):
    fields = dict(kb_id="kb1", snapshot_id=snapshot.snapshot_id, scheme_id=port.scheme_id, text=canonical_query_text(text), top_k=top_k, max_result_bytes=max_bytes) | overrides
    return port.retrieve(RetrievalRequest(**fields))


def answer(port, text="alpha", **kwargs) -> RetrievalResult:
    result = ask(port, text, **kwargs)
    assert isinstance(result, RetrievalResult), result
    return result


def failure(kind, message_part=None):
    class Matches:
        def __eq__(self, other):
            return isinstance(other, RetrievalFailure) and other.kind is kind and (message_part is None or message_part in other.message)

        def __repr__(self):
            return f"<RetrievalFailure {kind.value} containing {message_part!r}>"

    return Matches()


# --- the pinned identity ---------------------------------------------------------------------------------------------------------------


def test_the_pinned_model_is_the_recorded_revision_and_digests():
    assert PINNED_MODEL.model == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert PINNED_MODEL.revision == "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
    assert PINNED_MODEL.weights_sha256 == "eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b"
    assert PINNED_MODEL.directory_sha256 == "e99a362c5cdf060fe3dec4f42b61f3f847d80ce8881a8c716b3468bdf7ef03dc"
    assert (PINNED_MODEL.dimension, PINNED_MODEL.max_pieces) == (384, 128)


def test_the_scheme_id_names_the_score_the_model_its_revision_the_dimension_and_the_window():
    assert semantic_scheme_id(PINNED_MODEL) == "semantic-cosine-v1/model=paraphrase-multilingual-MiniLM-L12-v2/rev=e8f8c211/dim=384/pieces=128"
    assert SEMANTIC_SCORE_KIND == "semantic-cosine-v1"
    assert semantic_scheme_id(IDENTITY) == "semantic-cosine-v1/model=stub/rev=aaaaaaaa/dim=3/pieces=10"


@pytest.mark.parametrize(
    "change",
    [{"model": "test/other"}, {"revision": "b" * 40}, {"dimension": 4}, {"max_pieces": 11}],
)
def test_a_different_model_revision_dimension_or_window_is_a_different_scheme(change):
    other = IDENTITY.model_copy(update=change)
    assert semantic_scheme_id(other) != SCHEME_ID


def test_the_digests_do_not_change_the_scheme_id_only_the_revision_prefix_does():
    assert semantic_scheme_id(IDENTITY.model_copy(update={"weights_sha256": "d" * 64, "directory_sha256": "e" * 64})) == SCHEME_ID


@pytest.mark.parametrize(
    "field, value",
    [
        ("model", ""),
        ("model", "-bad"),
        ("model", "has space"),
        ("model", "x" * 97),
        ("revision", "a" * 39),
        ("revision", "A" * 40),
        ("revision", "g" * 40),
        ("weights_sha256", "b" * 63),
        ("directory_sha256", "C" * 64),
        ("dimension", 0),
        ("max_pieces", 2),
    ],
)
def test_an_identity_refuses_what_is_not_a_model_revision_digest_dimension_or_window(field, value):
    with pytest.raises(ValueError):
        SemanticModelIdentity(**(IDENTITY.model_dump() | {field: value}))


def test_a_model_name_too_long_to_make_a_scheme_id_is_refused():
    name = "a" * 95  # a legal name whose scheme id would be over 128 characters
    with pytest.raises(ValueError, match="scheme id"):
        SemanticModelIdentity(**(IDENTITY.model_dump() | {"model": name}))


def test_the_smallest_dimension_is_one_and_a_model_name_without_an_organisation_names_itself():
    tiny = SemanticModelIdentity(**(IDENTITY.model_dump() | {"dimension": 1, "model": "plain-name"}))
    assert tiny.dimension == 1 and semantic_scheme_id(tiny) == "semantic-cosine-v1/model=plain-name/rev=aaaaaaaa/dim=1/pieces=10"
    assert semantic_scheme_id(IDENTITY.model_copy(update={"model": "org/team/deep-name"})).split("/")[1] == "model=deep-name"


def test_the_smallest_embedded_text_is_one_piece_and_the_smallest_failure_message_is_one_character():
    assert EmbeddedText(pieces=1, vector=None).pieces == 1
    with pytest.raises(ValueError):
        EmbeddedText(pieces=0, vector=None)
    assert EmbedderFailure(kind=EmbedderFailureKind.CRASHED, message="x").message == "x"
    with pytest.raises(ValueError):
        EmbedderFailure(kind=EmbedderFailureKind.CRASHED, message="")


def test_the_smallest_window_is_three_pieces():
    assert SemanticModelIdentity(**(IDENTITY.model_dump() | {"max_pieces": 3})).max_pieces == 3


# --- exact cosine ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ((1.0, 0.0), (1.0, 0.0), 1.0),
        ((1.0, 0.0), (-1.0, 0.0), -1.0),
        ((1.0, 0.0), (0.0, 1.0), 0.0),
        ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0), 32 / (math.sqrt(14) * math.sqrt(77))),
        ((1.0, 1.0), (1.0, 0.0), 1 / math.sqrt(2)),
        ((3.0, 4.0), (4.0, 3.0), 24 / 25),
    ],
)
def test_cosine_is_the_dot_product_over_the_product_of_the_lengths(a, b, expected):
    assert cosine_similarity(a, b) == pytest.approx(expected, rel=1e-14, abs=1e-15)


def test_cosine_does_not_depend_on_the_scale_of_either_vector():
    assert cosine_similarity((2.0, 4.0, 6.0), (1.0, 0.0, 1.0)) == pytest.approx(cosine_similarity((1.0, 2.0, 3.0), (5.0, 0.0, 5.0)), rel=1e-14)


def test_cosine_is_symmetric():
    rng = random.Random(7)
    for _ in range(50):
        a = tuple(rng.uniform(-1, 1) for _ in range(16))
        b = tuple(rng.uniform(-1, 1) for _ in range(16))
        assert cosine_similarity(a, b) == cosine_similarity(b, a)


def test_a_score_never_leaves_minus_one_to_one_even_by_the_last_place_of_one_division():
    rng = random.Random(11)
    for _ in range(2000):
        a = tuple(rng.uniform(-1e3, 1e3) for _ in range(24))
        assert cosine_similarity(a, a) <= 1.0
        assert cosine_similarity(a, tuple(-x for x in a)) >= -1.0


def test_the_clamp_is_what_keeps_a_score_at_one_when_the_division_lands_one_place_beyond_it():
    v = (-0.681, 0.915, -0.914)  # unclamped, v against itself is 1.0000000000000002 and against its negation -1.0000000000000002
    assert cosine_similarity(v, v) == 1.0
    assert cosine_similarity(v, tuple(-x for x in v)) == -1.0


def test_the_length_of_a_vector_is_summed_exactly_too():
    # a left-to-right sum loses every 1e-16 added to 1.0 and gets 1.0; the exact sum is 1 + 1000 * 1e-16
    assert vector_norm((1.0,) + (1e-8,) * 1000) == pytest.approx(math.sqrt(1.0 + 1000 * 1e-16), rel=1e-15, abs=0)
    assert vector_norm((1.0,) + (1e-8,) * 1000) > 1.0


def test_the_dot_product_and_the_lengths_are_summed_exactly_not_left_to_right():
    # 1e16 + 1 - 1e16 is 0.0 summed left to right and 1.0 summed exactly: the exact sum makes the dot product 1.0, so this is not orthogonal
    a, b = (1e16, 1.0, -1e16), (1.0, 1.0, 1.0)
    assert cosine_similarity(a, b) == pytest.approx(1.0 / (math.sqrt(2e32 + 1) * math.sqrt(3.0)), rel=1e-9, abs=0)
    assert cosine_similarity(a, b) > 0.0


def test_cosine_refuses_vectors_of_different_lengths_and_vectors_it_cannot_measure():
    with pytest.raises(ValueError, match="one length"):
        cosine_similarity((1.0, 0.0), (1.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="non-zero"):
        cosine_similarity((0.0, 0.0), (1.0, 0.0))
    with pytest.raises(ValueError, match="non-zero"):
        cosine_similarity((1.0, 0.0), (0.0, 0.0))
    with pytest.raises(ValueError, match="non-zero"):
        cosine_similarity((1e200, 1e200), (1e200, 1e200))


# --- opening a port --------------------------------------------------------------------------------------------------------------------


def test_opening_embeds_every_chunk_once_in_canonical_order_and_a_query_embeds_one_text():
    embedder = FakeEmbedder()
    port = opened(embedder, batch_size=16)
    assert embedder.calls == [tuple(chunk.text for chunk in TINY.chunks)]
    answer(port)
    assert embedder.calls[1:] == [("alpha",)]


@pytest.mark.parametrize("batch_size, calls", [(1, 3), (2, 2), (3, 1), (16, 1)])
def test_chunks_are_sent_in_batches_in_canonical_order_and_a_batch_size_does_not_change_the_answer(batch_size, calls):
    embedder = FakeEmbedder()
    port = opened(embedder, batch_size=batch_size)
    assert len(embedder.calls) == calls
    assert [text for call in embedder.calls for text in call] == [chunk.text for chunk in TINY.chunks]
    assert all(len(call) <= batch_size for call in embedder.calls)
    assert answer(port) == answer(opened(FakeEmbedder(), batch_size=16))


def test_opening_serves_the_snapshot_it_was_opened_with_and_names_the_scheme_of_its_embedders_model():
    port = opened()
    assert (port.kb_id, port.snapshot_id, port.scheme_id, port.identity) == ("kb1", TINY.snapshot_id, SCHEME_ID, IDENTITY)


def test_a_knowledge_base_id_and_a_batch_size_are_checked_at_opening():
    with pytest.raises(ValueError, match="knowledge base id"):
        SemanticKnowledgePort.open(TINY, kb_id="Not A Source Id", embedder=FakeEmbedder())
    with pytest.raises(ValueError, match="at least one"):
        SemanticKnowledgePort.open(TINY, kb_id="kb1", embedder=FakeEmbedder(), batch_size=0)


@pytest.mark.parametrize(
    ("embedder_kind", "retrieval_kind"),
    [
        (EmbedderFailureKind.UNAVAILABLE, RetrievalFailureKind.UNAVAILABLE),
        (EmbedderFailureKind.TIMEOUT, RetrievalFailureKind.UNAVAILABLE),
        (EmbedderFailureKind.CRASHED, RetrievalFailureKind.UNAVAILABLE),
        (EmbedderFailureKind.IDENTITY_MISMATCH, RetrievalFailureKind.UNAVAILABLE),
        (EmbedderFailureKind.MALFORMED_REPLY, RetrievalFailureKind.MALFORMED_RESULT),
        (EmbedderFailureKind.REQUEST_REFUSED, RetrievalFailureKind.REQUEST_MISMATCH),
    ],
)
def test_every_embedder_failure_becomes_the_typed_retrieval_failure_it_maps_to_when_opening_and_when_asking(embedder_kind, retrieval_kind):
    the_failure = EmbedderFailure(kind=embedder_kind, message="scripted")
    assert SemanticKnowledgePort.open(TINY, kb_id="kb1", embedder=FakeEmbedder(failures={0: the_failure})) == failure(retrieval_kind, f"({embedder_kind.value}): scripted")
    port = opened(FakeEmbedder(failures={1: the_failure}))
    assert ask(port) == failure(retrieval_kind, f"({embedder_kind.value}): scripted")


def test_the_embedder_failure_kinds_are_these_and_have_these_values():
    assert {kind.name: kind.value for kind in EmbedderFailureKind} == {
        "UNAVAILABLE": "unavailable", "TIMEOUT": "timeout", "CRASHED": "crashed", "MALFORMED_REPLY": "malformed_reply", "IDENTITY_MISMATCH": "identity_mismatch",
        "REQUEST_REFUSED": "request_refused",
    }


def test_every_embedder_failure_kind_has_a_mapping():
    assert set(semantic_module._FAILURE_KIND) == set(EmbedderFailureKind)


def test_a_failure_in_a_later_batch_fails_the_opening_and_no_port_is_made():
    embedder = FakeEmbedder(failures={1: EmbedderFailure(kind=EmbedderFailureKind.CRASHED, message="second batch")})
    assert SemanticKnowledgePort.open(TINY, kb_id="kb1", embedder=embedder, batch_size=1) == failure(RetrievalFailureKind.UNAVAILABLE, "second batch")
    assert len(embedder.calls) == 2  # it stopped at the failure


# --- the window: refused, never truncated ----------------------------------------------------------------------------------------------


def over_window(text: str) -> EmbeddedText:
    return EmbeddedText(pieces=IDENTITY.max_pieces + 1, vector=None)


def test_a_chunk_over_the_window_makes_the_index_unbuildable_and_is_named_never_truncated():
    embedder = FakeEmbedder(replace={GAMMA.text: over_window(GAMMA.text)})
    result = SemanticKnowledgePort.open(TINY, kb_id="kb1", embedder=embedder)
    assert result == failure(RetrievalFailureKind.UNAVAILABLE, f"chunk {GAMMA.chunk_id[:12]} has 11 word pieces, over the model's window of 10")
    assert "never truncated" in result.message


def test_the_first_chunk_over_the_window_in_canonical_order_is_the_one_named():
    embedder = FakeEmbedder(replace={DELTA.text: over_window(DELTA.text), GAMMA.text: over_window(GAMMA.text)})
    result = SemanticKnowledgePort.open(TINY, kb_id="kb1", embedder=embedder, batch_size=1)
    first = min((GAMMA, DELTA), key=lambda chunk: TINY.chunks.index(chunk))
    assert first.chunk_id[:12] in result.message


def test_a_chunk_exactly_at_the_window_is_embedded():
    at_the_window = EmbeddedText(pieces=IDENTITY.max_pieces, vector=(1.0, 1.0, 0.0))
    assert isinstance(SemanticKnowledgePort.open(TINY, kb_id="kb1", embedder=FakeEmbedder(replace={GAMMA.text: at_the_window})), SemanticKnowledgePort)


def test_a_chunk_over_the_window_that_came_back_with_a_vector_is_a_malformed_answer():
    lying = EmbeddedText(pieces=IDENTITY.max_pieces + 1, vector=(1.0, 1.0, 0.0))
    assert SemanticKnowledgePort.open(TINY, kb_id="kb1", embedder=FakeEmbedder(replace={GAMMA.text: lying})) == failure(
        RetrievalFailureKind.MALFORMED_RESULT, "over the window of 10"
    )


@pytest.mark.parametrize("pieces", [3, 9, 10])
def test_a_chunk_within_the_window_that_came_back_with_no_vector_is_a_malformed_answer(pieces):
    empty = EmbeddedText(pieces=pieces, vector=None)  # the window is 10 pieces: at it, a text is within it
    result = SemanticKnowledgePort.open(TINY, kb_id="kb1", embedder=FakeEmbedder(replace={GAMMA.text: empty}))
    assert result == failure(RetrievalFailureKind.MALFORMED_RESULT, f"chunk {GAMMA.chunk_id[:12]}: a text within the window came back with no vector")


@pytest.mark.parametrize("pieces", [3, 9, 10])
def test_a_query_within_the_window_that_came_back_with_no_vector_is_a_malformed_answer_not_a_refusal_of_the_request(pieces):
    embedder = FakeEmbedder()
    port = opened(embedder)
    embedder.replace["alpha"] = EmbeddedText(pieces=pieces, vector=None)
    assert ask(port) == failure(RetrievalFailureKind.MALFORMED_RESULT, "the query: a text within the window came back with no vector")


def test_the_default_batch_is_sixteen_texts_to_a_request():
    snapshot = build_snapshot(tuple(doc(f"s{n}", f"word{n} alpha") for n in range(40)), SCHEME)
    embedder = FakeEmbedder(vectors={chunk.text: (1.0, 0.0, 0.0) for chunk in snapshot.chunks})
    assert isinstance(SemanticKnowledgePort.open(snapshot, kb_id="kb1", embedder=embedder), SemanticKnowledgePort)
    assert [len(call) for call in embedder.calls] == [16, 16, 8]


def test_a_query_over_the_window_is_a_request_that_cannot_be_served_and_is_never_truncated():
    embedder = FakeEmbedder()
    port = opened(embedder)
    long_query = " ".join(["alpha"] * 9)  # 9 words + 2 = 11 pieces, over the window of 10
    embedder.replace[long_query] = over_window(long_query)
    result = ask(port, long_query)
    assert result == failure(RetrievalFailureKind.REQUEST_MISMATCH, "the query has 11 word pieces, over the model's window of 10")
    assert "never truncated" in result.message


def test_a_query_exactly_at_the_window_is_answered():
    embedder = FakeEmbedder()
    port = opened(embedder)
    at_the_window = " ".join(["alpha"] * 8)  # 8 words + 2 = 10 pieces
    embedder.replace[at_the_window] = EmbeddedText(pieces=10, vector=(1.0, 0.5, 0.0))
    assert len(answer(port, at_the_window).hits) == 3


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        (EmbeddedText(pieces=3, vector=(1.0, 0.0)), "2 components"),
        (EmbeddedText(pieces=3, vector=(1.0, 0.0, 0.0, 0.0)), "4 components"),
        (EmbeddedText(pieces=3, vector=(1.0, math.nan, 0.0)), "not a finite number"),
        (EmbeddedText(pieces=3, vector=(1.0, math.inf, 0.0)), "not a finite number"),
        (EmbeddedText(pieces=3, vector=(1.0, -math.inf, 0.0)), "not a finite number"),
        (EmbeddedText(pieces=3, vector=(0.0, 0.0, 0.0)), "no usable length"),
        (EmbeddedText(pieces=3, vector=(1e-101, 0.0, 0.0)), "no usable length"),
        (EmbeddedText(pieces=3, vector=(1e101, 0.0, 0.0)), "no usable length"),
        (EmbeddedText(pieces=3, vector=(1e200, 1e200, 0.0)), "no usable length"),
    ],
)
def test_a_vector_that_is_not_of_the_models_dimension_finite_and_of_usable_length_is_a_malformed_answer(bad, message):
    result = SemanticKnowledgePort.open(TINY, kb_id="kb1", embedder=FakeEmbedder(replace={GAMMA.text: bad}))
    assert result == failure(RetrievalFailureKind.MALFORMED_RESULT, message)
    assert result.message.startswith(f"chunk {GAMMA.chunk_id[:12]}: ")
    embedder = FakeEmbedder()
    port = opened(embedder)
    embedder.replace["alpha"] = bad
    result = ask(port)
    assert result == failure(RetrievalFailureKind.MALFORMED_RESULT, message)
    assert result.message.startswith("the query: ")


@pytest.mark.parametrize(
    ("length", "usable"),
    [(0.99e-100, False), (1.01e-100, True), (0.99e100, True), (1.01e100, False), (1.5e100, False), (2.5e100, False), (1e-99, True), (1e99, True)],
)
def test_a_vector_is_usable_from_1e_minus_100_to_1e_100_in_length_and_not_a_hair_outside(length, usable):
    outcome = SemanticKnowledgePort.open(TINY, kb_id="kb1", embedder=FakeEmbedder(replace={GAMMA.text: EmbeddedText(pieces=3, vector=(length, 0.0, 0.0))}))
    assert isinstance(outcome, SemanticKnowledgePort) == usable


def test_a_vector_at_the_edges_of_the_usable_length_is_accepted():
    for length in (1e-100, 1e100):
        assert isinstance(SemanticKnowledgePort.open(TINY, kb_id="kb1", embedder=FakeEmbedder(replace={GAMMA.text: EmbeddedText(pieces=3, vector=(length, 0.0, 0.0))})), SemanticKnowledgePort)


@pytest.mark.parametrize(
    "transform",
    [
        lambda answer: answer[:-1],
        lambda answer: answer + answer[:1],
        lambda answer: (),
        lambda answer: list(answer),
        lambda answer: answer + (None,),
        lambda answer: (None,) * len(answer),
        lambda answer: "not an answer",
        lambda answer: None,
    ],
)
def test_an_answer_that_is_not_one_embedded_text_for_each_text_asked_is_a_malformed_answer(transform):
    assert SemanticKnowledgePort.open(TINY, kb_id="kb1", embedder=FakeEmbedder(transform=transform)) == failure(RetrievalFailureKind.MALFORMED_RESULT, "one embedded text for each text asked")
    embedder = FakeEmbedder()
    port = opened(embedder)
    embedder.transform = transform
    assert ask(port) == failure(RetrievalFailureKind.MALFORMED_RESULT, "one embedded text for the query")


# --- what a request may name -----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["kb_id", "snapshot_id", "scheme_id"])
def test_a_request_naming_another_knowledge_base_snapshot_or_scheme_is_refused_before_anything_is_embedded(name):
    embedder = FakeEmbedder()
    port = opened(embedder)
    calls = len(embedder.calls)
    other = {"kb_id": "kb2", "snapshot_id": "f" * 64, "scheme_id": semantic_scheme_id(IDENTITY.model_copy(update={"revision": "b" * 40}))}[name]
    result = ask(port, **{name: other})
    assert result == failure(RetrievalFailureKind.REQUEST_MISMATCH, f"this port serves {name}")
    assert len(embedder.calls) == calls


def test_the_lexical_scheme_is_not_served_by_the_semantic_port():
    assert ask(opened(), scheme_id="lexical-bm25-v1/k1=1.2/b=0.75/tokens=word-v1") == failure(RetrievalFailureKind.REQUEST_MISMATCH, "scheme_id")


# --- ranking ---------------------------------------------------------------------------------------------------------------------------


def test_hits_are_ranked_from_one_by_cosine_with_the_scores_worked_out_by_hand():
    result = answer(opened())
    assert [hit.rank for hit in result.hits] == [1, 2, 3]
    assert [hit.chunk for hit in result.hits] == [GAMMA, BETA, DELTA]
    assert [hit.score for hit in result.hits] == pytest.approx([1.5 / (math.sqrt(1.25) * math.sqrt(2.0)), 1.0 / math.sqrt(1.25), 0.0], rel=1e-14, abs=1e-15)


def test_a_result_names_its_query_snapshot_scheme_and_what_a_score_is_and_answers_its_request():
    port = opened()
    request = RetrievalRequest(kb_id="kb1", snapshot_id=TINY.snapshot_id, scheme_id=port.scheme_id, text="alpha", top_k=2, max_result_bytes=10**6)
    result = port.retrieve(request)
    assert (result.query_id, result.kb_id, result.snapshot_id, result.scheme_id, result.score_kind) == (request.query_id, "kb1", TINY.snapshot_id, SCHEME_ID, "semantic-cosine-v1")
    assert result_problem(request, result) is None
    assert all(isinstance(hit.score, float) for hit in result.hits)


def test_every_chunk_is_a_candidate_so_a_query_that_shares_nothing_still_gets_a_full_ranking():
    embedder = FakeEmbedder(vectors=VECTORS | {"zebra": (0.0, 1.0, 0.0)})
    result = answer(opened(embedder), "zebra", top_k=50)
    assert len(result.hits) == 3
    assert result.hits[0].score >= result.hits[1].score >= result.hits[2].score


def test_a_negative_cosine_is_a_score_and_ranks_last():
    embedder = FakeEmbedder(vectors=VECTORS | {"opposite": (-1.0, 0.0, 0.0)})
    result = answer(opened(embedder), "opposite")
    assert [hit.chunk for hit in result.hits] == [DELTA, GAMMA, BETA]
    assert result.hits[-1].score == -1.0
    assert result.hits[0].score == 0.0


def test_a_tie_is_broken_by_chunk_id_ascending_and_a_score_is_never_rounded_to_make_one():
    tied = VECTORS | {GAMMA.text: (1.0, 0.0, 0.0)}  # the same vector as BETA: exactly the same score
    result = answer(opened(FakeEmbedder(vectors=tied)), "alpha")
    assert result.hits[0].score == result.hits[1].score
    assert [hit.chunk.chunk_id for hit in result.hits[:2]] == sorted([BETA.chunk_id, GAMMA.chunk_id])
    close = VECTORS | {GAMMA.text: (1.0, 1e-9, 0.0)}  # nearly the same direction as BETA: a different score, and the better one first
    ordered = answer(opened(FakeEmbedder(vectors=close)), "alpha")
    assert ordered.hits[0].score != ordered.hits[1].score


def test_all_scores_tied_are_ordered_by_chunk_id_alone():
    same = {BETA.text: (1.0, 0.0, 0.0), GAMMA.text: (1.0, 0.0, 0.0), DELTA.text: (1.0, 0.0, 0.0), "alpha": (0.0, 1.0, 0.0)}
    result = answer(opened(FakeEmbedder(vectors=same)), "alpha")
    assert [hit.chunk.chunk_id for hit in result.hits] == sorted(chunk.chunk_id for chunk in TINY.chunks)


def test_the_order_of_the_hits_does_not_depend_on_the_order_the_chunks_are_held_in():
    reordered = TINY.model_copy(update={"chunks": tuple(reversed(TINY.chunks))})
    tied = FakeEmbedder(vectors={text: (1.0, 0.0, 0.0) for text in VECTORS} | {"alpha": (1.0, 0.0, 0.0)})
    assert [hit.chunk.chunk_id for hit in answer(opened(tied, snapshot=reordered), "alpha").hits] == sorted(chunk.chunk_id for chunk in TINY.chunks)


@pytest.mark.parametrize("top_k, expected", [(1, 1), (2, 2), (3, 3), (4, 3), (50, 3)])
def test_top_k_cuts_the_ranking_and_a_larger_top_k_returns_every_chunk(top_k, expected):
    port = opened()
    result = answer(port, top_k=top_k)
    assert len(result.hits) == expected
    assert [hit.chunk for hit in result.hits] == [hit.chunk for hit in answer(port, top_k=50).hits][:expected]


def test_top_k_never_changes_a_score_or_an_order():
    port = opened()
    full = answer(port, top_k=3)
    assert answer(port, top_k=1).hits == full.hits[:1]
    assert answer(port, top_k=2).hits == full.hits[:2]


@pytest.mark.parametrize("text", ["alpha", "alpha gamma"])
def test_asking_twice_gives_equal_results_and_the_query_does_not_change_the_index(text):
    port = opened()
    assert answer(port, text) == answer(port, text)


# --- one query, one text; one snapshot, one index --------------------------------------------------------------------------------------------


def test_two_spellings_of_one_query_are_one_query_and_the_embedder_is_asked_the_same_canonical_text():
    precomposed = "caf" + E_ACUTE
    decomposed = "cafe" + chr(0x301)
    embedder = FakeEmbedder(vectors=VECTORS | {precomposed: (1.0, 0.5, 0.0)})
    port = opened(embedder)
    with pytest.raises(ValueError, match="canonical"):
        RetrievalRequest(kb_id="kb1", snapshot_id=TINY.snapshot_id, scheme_id=port.scheme_id, text=decomposed, top_k=3, max_result_bytes=10**6)
    results = [answer(port, spelling) for spelling in (decomposed, "  " + precomposed + chr(13) + chr(10), precomposed)]
    assert results[0] == results[1] == results[2]
    assert embedder.calls[1:] == [(precomposed,)] * 3


def test_the_index_is_built_once_when_the_port_is_opened_and_a_later_change_of_the_embedder_does_not_reach_it():
    embedder = FakeEmbedder()
    port = opened(embedder)
    before = answer(port)
    embedder.vectors[GAMMA.text] = (0.0, 0.0, 1.0)  # the embedder would now embed this chunk differently
    embedder.vectors[DELTA.text] = (1.0, 1.0, 0.0)
    assert answer(port) == before
    assert len(embedder.calls) == 3  # the corpus once, and one text for each of the two queries


def test_two_ports_over_two_snapshots_each_serve_only_their_own():
    other = build_snapshot((doc("s9", "alpha gamma gamma"),), SCHEME)
    embedder = FakeEmbedder(vectors=VECTORS | {other.chunks[0].text: (0.0, 1.0, 0.0)})
    first, second = opened(embedder), opened(embedder, snapshot=other)
    assert ask(first) == answer(first) and isinstance(ask(second, snapshot=other), RetrievalResult)
    assert ask(first, snapshot_id=other.snapshot_id) == failure(RetrievalFailureKind.REQUEST_MISMATCH, "snapshot_id")
    assert ask(second, snapshot_id=TINY.snapshot_id, snapshot=other) == failure(RetrievalFailureKind.REQUEST_MISMATCH, "snapshot_id")
    assert [hit.chunk for hit in answer(second, snapshot=other).hits] == [other.chunks[0]]


# --- the byte bound --------------------------------------------------------------------------------------------------------------------


def test_the_byte_bound_is_on_the_chosen_hits_text_and_the_exact_size_is_allowed():
    port = opened()
    size = len(GAMMA.text.encode("utf-8")) + len(BETA.text.encode("utf-8"))
    assert [hit.chunk for hit in answer(port, top_k=2, max_bytes=size).hits] == [GAMMA, BETA]
    assert ask(port, top_k=2, max_bytes=size - 1) == failure(RetrievalFailureKind.RESULT_TOO_LARGE, f"the 2 best hits hold {size} bytes of text, over the bound of {size - 1}")


def test_a_hit_that_would_exceed_the_bound_is_refused_not_dropped_and_a_smaller_top_k_can_fit():
    port = opened()
    assert isinstance(ask(port, top_k=1, max_bytes=len(GAMMA.text.encode("utf-8"))), RetrievalResult)
    assert isinstance(ask(port, top_k=3, max_bytes=len(GAMMA.text.encode("utf-8"))), RetrievalFailure)


def test_the_bound_counts_utf_8_bytes_not_characters():
    snapshot = build_snapshot((doc("s1", f"caf{E_ACUTE} caf{E_ACUTE}"),), SCHEME)
    text = snapshot.chunks[0].text
    embedder = FakeEmbedder(vectors={text: (1.0, 0.0, 0.0), "q": (1.0, 0.0, 0.0)})
    port = opened(embedder, snapshot=snapshot)
    assert len(text.encode("utf-8")) == len(text) + 2
    assert isinstance(ask(port, "q", snapshot=snapshot, top_k=1, max_bytes=len(text) + 2), RetrievalResult)
    assert ask(port, "q", snapshot=snapshot, top_k=1, max_bytes=len(text) + 1) == failure(RetrievalFailureKind.RESULT_TOO_LARGE, "over the bound")


# --- a port is a KnowledgePort, and it is deterministic and thread safe -----------------------------------------------------------------


def test_the_port_is_a_knowledge_port():
    port: KnowledgePort = opened()
    assert callable(port.retrieve)


def test_concurrent_retrievals_give_the_answer_a_single_thread_gives():
    port = opened()
    expected = answer(port)
    results, errors = [], []

    def work():
        try:
            for _ in range(20):
                results.append(answer(port))
        except Exception as error:  # pragma: no cover - reported below
            errors.append(error)

    threads = [threading.Thread(target=work) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors and len(results) == 120 and all(result == expected for result in results)


def test_hits_carry_the_snapshots_own_chunks():
    result = answer(opened())
    assert all(hit.chunk in TINY.chunks for hit in result.hits)
    assert {hit.evidence_ref for hit in result.hits} == {chunk.evidence_ref for chunk in TINY.chunks}
