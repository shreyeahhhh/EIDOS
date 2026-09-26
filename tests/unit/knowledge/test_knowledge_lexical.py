"""The lexical retriever: tokens, scores, order, ties, bounds and determinism (decisions.md D-208, D-216, D-220, D-225; V1.3 Step 4, phase B).

What is proven: a chunk's score is the weighting the scheme names, checked against values worked out by hand and against an independent float implementation; hits come back ranked
from 1, best score first and, for a tie, by chunk id; ``top_k`` only ever cuts the same ranking; nothing that shares no term is a hit; a request the port does not serve, or an answer
over the byte bound, is a typed failure and never a truncation; and the answer depends on nothing but the snapshot and the request: not the hash seed, the ambient decimal context, the
declaration order or the thread.
"""

import functools
import hashlib
import math
import os
import random
import re
import subprocess
import sys
import threading
import unicodedata
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Context, Decimal, getcontext, localcontext
from pathlib import Path

import pytest

from eidos.knowledge import (
    LEXICAL_SCHEME_ID,
    LEXICAL_SCORE_KIND,
    LexicalKnowledgePort,
    RetrievalFailure,
    RetrievalFailureKind,
    RetrievalRequest,
    RetrievalResult,
    build_snapshot,
    canonical_query_text,
)
from eidos.knowledge.lexical import K1, B, tokenise
from eidos_knowledge_factories import SCHEME, doc, small_corpus

ROOT = Path(__file__).resolve().parents[3]
TINY = build_snapshot((doc("s1", "alpha beta beta"), doc("s2", "alpha gamma"), doc("s3", "delta delta delta delta")), SCHEME)
SMALL = build_snapshot(small_corpus(), SCHEME)


def port_for(snapshot, kb_id="kb1") -> LexicalKnowledgePort:
    return LexicalKnowledgePort(snapshot, kb_id=kb_id)


def ask(port, snapshot, text, *, top_k=50, max_bytes=10**6, **overrides):
    fields = dict(
        kb_id=port.kb_id, snapshot_id=snapshot.snapshot_id, scheme_id=LEXICAL_SCHEME_ID, text=canonical_query_text(text), top_k=top_k, max_result_bytes=max_bytes
    ) | overrides
    return port.retrieve(RetrievalRequest(**fields))


def answer(port, snapshot, text, **kwargs) -> RetrievalResult:
    result = ask(port, snapshot, text, **kwargs)
    assert isinstance(result, RetrievalResult), result
    return result


# --- tokens ---------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "tokens"),
    [
        ("alpha beta", ("alpha", "beta")),
        ("Alpha BETA", ("alpha", "beta")),
        ("well-known fact", ("well", "known", "fact")),
        ("it's 3.14 (pi)", ("it", "s", "3", "14", "pi")),
        ("snake_case stays", ("snake_case", "stays")),
        ("route 66, exit 4b", ("route", "66", "exit", "4b")),
        ("a\nb\tc  d", ("a", "b", "c", "d")),
        ("", ()),
        ("   ", ()),
        ("!!! ??? ...", ()),
        ("same same Same", ("same", "same", "same")),
    ],
)
def test_a_token_is_a_run_of_word_characters_lower_cased(text, tokens):
    assert tokenise(text) == tokens


def test_tokens_are_taken_from_the_nfc_form_so_composed_and_decomposed_text_agree():
    composed = "caf" + chr(0xE9)
    decomposed = "cafe" + chr(0x301)
    assert tokenise(composed) == tokenise(decomposed) == (composed,)
    assert tokenise("line one\r\nline two") == ("line", "one", "line", "two")


# --- scores, by hand and against an independent implementation ------------------------------------------------------------------------


def test_the_scheme_and_its_parameters_are_the_ones_fixed_before_any_run():
    assert LEXICAL_SCHEME_ID == "lexical-bm25-v1/k1=1.2/b=0.75/tokens=word-v1"
    assert LEXICAL_SCORE_KIND == "lexical-bm25-v1"
    assert (str(K1), str(B)) == ("1.2", "0.75")


def test_scores_on_a_tiny_corpus_are_the_values_worked_out_by_hand():
    """Chunks 'alpha beta beta' (3 tokens), 'alpha gamma' (2) and 'delta delta delta delta' (4): N = 3, average length 3, df(alpha) = 2, df(beta) = 1.
    idf(alpha) = ln(1.6), idf(beta) = ln(1 + 2.5 / 1.5); the first chunk scores idf(alpha) * 1 + idf(beta) * 1.375 = 1.8186438521..., the second
    idf(alpha) * 2.2 / 1.9 = 0.5442147286..., and the third shares no term. Each is rounded to nine decimal places."""
    port = port_for(TINY)
    result = answer(port, TINY, "alpha beta")
    (first, second) = result.hits
    assert (first.chunk.text, first.rank, first.score) == ("alpha beta beta", 1, 1.818643852)
    assert (second.chunk.text, second.rank, second.score) == ("alpha gamma", 2, 0.544214729)
    assert len(result.hits) == 2  # the third chunk shares no term, so it is not a hit


def float_oracle(snapshot, query):
    """The scheme restated with floats and ``math.log``, sharing nothing with the implementation but the formula."""
    docs = [re.findall(r"\w+", unicodedata.normalize("NFC", c.text).lower()) for c in snapshot.chunks]
    n, average = len(docs), sum(len(d) for d in docs) / len(docs)
    terms = set(re.findall(r"\w+", query.lower()))
    scores = {}
    for chunk, tokens in zip(snapshot.chunks, docs):
        total, matched = 0.0, False
        for term in terms:
            tf = tokens.count(term)
            df = sum(1 for d in docs if term in d)
            if tf == 0:
                continue
            matched = True
            total += math.log(1 + (n - df + 0.5) / (df + 0.5)) * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * len(tokens) / average))
        if matched:
            scores[chunk.chunk_id] = total
    return scores


@pytest.mark.parametrize(
    "query",
    ["inspection checklist before restart", "the tidal barrier sensors", "grid operator notified", "turbine", "audit found that no turbine may be released", "zzz nothing"],
)
def test_every_score_agrees_with_an_independent_float_implementation(query):
    result = answer(port_for(SMALL), SMALL, query)
    expected = float_oracle(SMALL, query)
    assert {h.chunk.chunk_id for h in result.hits} == set(expected)
    for hit in result.hits:
        assert hit.score == pytest.approx(expected[hit.chunk.chunk_id], abs=2e-9)


def exact_scores(snapshot, query):
    """The scheme restated in decimal arithmetic at 80 digits, rounded to the same quantum: what each score is to nine places, however many digits it takes to know."""
    context = Context(prec=80, rounding=ROUND_HALF_EVEN)
    docs = [re.findall(r"\w+", c.text.lower()) for c in snapshot.chunks]
    n, average = Decimal(len(docs)), context.divide(Decimal(sum(len(d) for d in docs)), Decimal(len(docs)))
    scores = {}
    for chunk, tokens in zip(snapshot.chunks, docs):
        total, matched = Decimal(0), False
        for term in sorted(set(re.findall(r"\w+", query.lower()))):
            tf = tokens.count(term)
            if tf == 0:
                continue
            matched = True
            df = Decimal(sum(1 for d in docs if term in d))
            idf = context.ln(1 + context.divide(n - df + Decimal("0.5"), df + Decimal("0.5")))
            scale = Decimal("0.25") + Decimal("0.75") * context.divide(Decimal(len(tokens)), average)
            total = context.add(total, context.multiply(idf, context.divide(Decimal(tf) * Decimal("2.2"), Decimal(tf) + Decimal("1.2") * scale)))
        if matched:
            scores[chunk.chunk_id] = total.quantize(Decimal("1e-9"), rounding=ROUND_HALF_EVEN, context=context)
    return scores


def big_corpus():
    """Three hundred one-chunk documents of two to eleven words from a vocabulary of forty, so that scores are sums of many terms and many differ only in their last places."""
    generator = random.Random(20260925)
    vocabulary = [f"w{n}" for n in range(40)]
    documents = tuple(doc(f"s{n}", " ".join(generator.choice(vocabulary) for _ in range(generator.randint(2, 11)))) for n in range(300))
    return build_snapshot(documents, SCHEME), vocabulary


def test_every_score_is_exactly_the_value_an_80_digit_computation_gives_to_nine_places_over_a_large_corpus():
    snapshot, vocabulary = big_corpus()
    port = port_for(snapshot)
    generator = random.Random(7)
    checked = 0
    for _ in range(12):
        query = " ".join(generator.sample(vocabulary, 8))
        result = answer(port, snapshot, query, top_k=1000)
        expected = exact_scores(snapshot, query)
        assert {h.chunk.chunk_id: h.score for h in result.hits} == {chunk_id: float(score) for chunk_id, score in expected.items()}
        checked += len(expected)
    assert checked > 2000  # a few thousand scores, each one compared exactly


def test_every_score_is_rounded_to_nine_decimal_places():
    for hit in answer(port_for(SMALL), SMALL, "inspection checklist before restart").hits:
        assert round(hit.score * 10**9) / 10**9 == hit.score


def test_a_repeated_query_term_counts_once_and_case_is_ignored():
    port = port_for(SMALL)
    once = answer(port, SMALL, "checklist")
    assert answer(port, SMALL, "checklist checklist CHECKLIST").hits == once.hits


def test_a_mirror_doubles_the_document_frequency_of_its_terms_because_df_counts_chunks():
    """Identical text under a second source is two chunks, so a term of it appears in twice as many chunks and weighs less (a stated property of the scheme, not a bug)."""
    without = build_snapshot((doc("ops", "alpha beta"), doc("blog", "gamma delta"), doc("grid", "epsilon zeta")), SCHEME)
    with_mirror = build_snapshot((doc("ops", "alpha beta"), doc("mirror", "alpha beta"), doc("blog", "gamma delta"), doc("grid", "epsilon zeta")), SCHEME)
    plain = answer(port_for(without), without, "alpha").hits[0].score
    mirrored = answer(port_for(with_mirror), with_mirror, "alpha")
    assert len(mirrored.hits) == 2 and mirrored.hits[0].score == mirrored.hits[1].score  # the mirror's copy scores exactly as the original
    assert plain == pytest.approx(math.log(1 + (3 - 1 + 0.5) / 1.5) * 2.2 / (1 + 1.2 * (0.25 + 0.75 * 2 / 2)), abs=2e-9)
    assert mirrored.hits[0].score == pytest.approx(math.log(1 + (4 - 2 + 0.5) / 2.5) * 2.2 / (1 + 1.2 * (0.25 + 0.75 * 2 / 2)), abs=2e-9)
    assert mirrored.hits[0].score < plain


def test_a_longer_chunk_scores_lower_for_the_same_term_frequency():
    snapshot = build_snapshot((doc("s1", "alpha beta"), doc("s2", "alpha beta gamma delta epsilon")), SCHEME)
    hits = answer(port_for(snapshot), snapshot, "alpha").hits
    assert [h.chunk.text for h in hits] == ["alpha beta", "alpha beta gamma delta epsilon"]
    assert hits[0].score > hits[1].score


def test_a_more_frequent_term_scores_higher_but_saturates():
    snapshot = build_snapshot(
        (doc("s1", "alpha x y z"), doc("s2", "alpha alpha x y"), doc("s3", "alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha"), doc("s4", "filler filler filler")),
        SCHEME,
    )
    scores = {h.chunk.text: h.score for h in answer(port_for(snapshot), snapshot, "alpha").hits}
    one, two, ten = scores["alpha x y z"], scores["alpha alpha x y"], scores["alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha"]
    assert one < two
    assert ten < one * 2.2  # the (k1 + 1) ceiling: ten occurrences are nowhere near ten times one


# --- order, ties and top_k --------------------------------------------------------------------------------------------------------------


def test_hits_are_ranked_from_one_best_score_first():
    result = answer(port_for(SMALL), SMALL, "inspection checklist before restart")
    assert [h.rank for h in result.hits] == list(range(1, len(result.hits) + 1))
    scores = [h.score for h in result.hits]
    assert scores == sorted(scores, reverse=True) and result.score_kind == LEXICAL_SCORE_KIND


def test_equal_scores_are_ordered_by_chunk_id_ascending_and_the_mirror_is_a_real_tie():
    result = answer(port_for(SMALL), SMALL, "inspection checklist before restart")
    tied = [h for h in result.hits if h.score == result.hits[0].score]
    assert len(tied) == 2 and {h.chunk.source_id for h in tied} == {"ops", "mirror"}
    assert tied[0].chunk.chunk_id < tied[1].chunk.chunk_id
    for a, b in zip(result.hits, result.hits[1:]):
        assert (-a.score, a.chunk.chunk_id) < (-b.score, b.chunk.chunk_id)


def test_the_tie_order_follows_chunk_id_not_source_name_or_declaration_order():
    hits_by_order = []
    for documents in (
        (doc("aaa", "alpha beta"), doc("zzz", "alpha beta"), doc("other", "gamma delta")),
        (doc("zzz", "alpha beta"), doc("other", "gamma delta"), doc("aaa", "alpha beta")),
    ):
        snapshot = build_snapshot(documents, SCHEME)
        hits = answer(port_for(snapshot), snapshot, "alpha").hits
        hits_by_order.append([h.chunk.chunk_id for h in hits])
        assert [h.chunk.chunk_id for h in hits] == sorted(h.chunk.chunk_id for h in hits)
    assert hits_by_order[0] == hits_by_order[1]


@pytest.mark.parametrize("top_k", [1, 2, 3, 5, 8])
def test_top_k_only_ever_cuts_the_same_ranking(top_k):
    port = port_for(SMALL)
    full = answer(port, SMALL, "inspection checklist before restart", top_k=100).hits
    cut = answer(port, SMALL, "inspection checklist before restart", top_k=top_k).hits
    assert len(full) > 5
    assert cut == full[:top_k]


def test_top_k_larger_than_the_matches_returns_only_the_matches():
    result = answer(port_for(TINY), TINY, "alpha beta", top_k=99)
    assert len(result.hits) == 2


def test_top_k_of_one_returns_the_single_best_hit():
    (only,) = answer(port_for(TINY), TINY, "alpha beta", top_k=1).hits
    assert only.chunk.text == "alpha beta beta" and only.rank == 1


# --- nothing shared, nothing retrieved ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("query", ["zzzz qqqq", "!!! ???", "0", "epsilon-free", ", ,"])
def test_a_query_that_shares_no_term_is_an_empty_result_not_a_failure(query):
    result = answer(port_for(TINY), TINY, query)
    assert result.hits == () and result.result_bytes == 0 and result.score_kind == LEXICAL_SCORE_KIND


def test_a_chunk_is_a_hit_only_if_it_shares_a_term_with_the_query():
    result = answer(port_for(TINY), TINY, "gamma")
    assert [h.chunk.text for h in result.hits] == ["alpha gamma"]
    assert answer(port_for(TINY), TINY, "delta").hits[0].chunk.text == "delta delta delta delta"


def test_a_snapshot_whose_chunks_hold_no_word_character_retrieves_nothing():
    snapshot = build_snapshot((doc("s1", "!!! ???"), doc("s2", "... ---")), SCHEME)
    assert answer(port_for(snapshot), snapshot, "anything").hits == ()


# --- bounds -------------------------------------------------------------------------------------------------------------------------------


def test_a_result_over_the_byte_bound_is_a_typed_failure_never_a_truncation():
    port = port_for(SMALL)
    best = answer(port, SMALL, "inspection checklist before restart", top_k=3).hits
    size = sum(len(h.chunk.text.encode("utf-8")) for h in best)
    assert isinstance(ask(port, SMALL, "inspection checklist before restart", top_k=3, max_bytes=size), RetrievalResult)
    failure = ask(port, SMALL, "inspection checklist before restart", top_k=3, max_bytes=size - 1)
    assert isinstance(failure, RetrievalFailure) and failure.kind is RetrievalFailureKind.RESULT_TOO_LARGE
    assert str(size) in failure.message and str(size - 1) in failure.message


def test_the_bound_is_measured_on_the_hits_that_are_returned_only():
    port = port_for(SMALL)
    one = answer(port, SMALL, "inspection checklist before restart", top_k=1).hits[0]
    size = len(one.chunk.text.encode("utf-8"))
    assert isinstance(ask(port, SMALL, "inspection checklist before restart", top_k=1, max_bytes=size), RetrievalResult)
    assert ask(port, SMALL, "inspection checklist before restart", top_k=2, max_bytes=size).kind is RetrievalFailureKind.RESULT_TOO_LARGE


def test_the_bound_counts_utf8_bytes_not_characters():
    text = "caf" + chr(0xE9) + " " + chr(0x6C34) + " opens"
    snapshot = build_snapshot((doc("s1", text), doc("s2", "other words here")), SCHEME)
    port = port_for(snapshot)
    characters, size = len(text), len(text.encode("utf-8"))
    assert size > characters
    assert isinstance(ask(port, snapshot, "opens", max_bytes=size), RetrievalResult)
    assert ask(port, snapshot, "opens", max_bytes=characters).kind is RetrievalFailureKind.RESULT_TOO_LARGE


def test_an_empty_result_fits_any_bound():
    assert isinstance(ask(port_for(TINY), TINY, "zzz", max_bytes=1), RetrievalResult)


# --- a request the port does not serve ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("override", "named"),
    [(dict(kb_id="other"), "kb_id"), (dict(snapshot_id="b" * 64), "snapshot_id"), (dict(scheme_id="other-scheme/x"), "scheme_id")],
)
def test_a_request_naming_another_knowledge_base_snapshot_or_scheme_is_a_typed_mismatch(override, named):
    failure = ask(port_for(TINY), TINY, "alpha", **override)
    assert isinstance(failure, RetrievalFailure) and failure.kind is RetrievalFailureKind.REQUEST_MISMATCH
    assert named in failure.message


def test_a_mismatch_is_returned_before_anything_is_scored():
    failure = ask(port_for(TINY), TINY, "alpha", kb_id="other", max_bytes=1)  # the byte bound would fail too, but the mismatch comes first
    assert failure.kind is RetrievalFailureKind.REQUEST_MISMATCH


# --- the port is pinned to its snapshot ---------------------------------------------------------------------------------------------------


def test_the_port_serves_exactly_its_snapshots_chunks_and_names_what_it_serves():
    port = port_for(SMALL, kb_id="facility")
    assert (port.kb_id, port.snapshot_id, port.scheme_id) == ("facility", SMALL.snapshot_id, LEXICAL_SCHEME_ID)
    result = answer(port, SMALL, "inspection checklist before restart")
    assert {h.chunk.chunk_id for h in result.hits} <= {c.chunk_id for c in SMALL.chunks}
    assert all(h.chunk in SMALL.chunks for h in result.hits)
    assert (result.kb_id, result.snapshot_id, result.scheme_id) == ("facility", SMALL.snapshot_id, LEXICAL_SCHEME_ID)


def test_the_result_carries_the_identity_of_the_query_it_answers():
    port = port_for(SMALL)
    request = RetrievalRequest(
        kb_id="kb1", snapshot_id=SMALL.snapshot_id, scheme_id=LEXICAL_SCHEME_ID, text="inspection checklist", top_k=3, max_result_bytes=10**6
    )
    assert port.retrieve(request).query_id == request.query_id


@pytest.mark.parametrize("kb_id", ["", " kb", "k b", "-kb", "x" * 65])
def test_a_port_refuses_a_malformed_knowledge_base_id_when_it_is_made(kb_id):
    with pytest.raises(ValueError, match="knowledge base id"):
        LexicalKnowledgePort(TINY, kb_id=kb_id)


# --- determinism -----------------------------------------------------------------------------------------------------------------------------


def test_the_same_snapshot_and_request_give_the_same_answer_every_time():
    port = port_for(SMALL)
    first = answer(port, SMALL, "inspection checklist before restart")
    for _ in range(5):
        assert answer(port, SMALL, "inspection checklist before restart") == first
    assert answer(port_for(SMALL), SMALL, "inspection checklist before restart") == first


def test_the_answer_does_not_depend_on_the_order_the_documents_were_declared_in():
    reference = answer(port_for(SMALL), SMALL, "inspection checklist before restart")
    for documents in (tuple(reversed(small_corpus())), small_corpus()[2:] + small_corpus()[:2]):
        snapshot = build_snapshot(documents, SCHEME)
        assert answer(port_for(snapshot), snapshot, "inspection checklist before restart") == reference


def test_the_ambient_decimal_context_plays_no_part():
    port = port_for(SMALL)
    reference = answer(port, SMALL, "inspection checklist before restart")
    with localcontext() as ambient:
        ambient.prec, ambient.rounding = 3, ROUND_DOWN
        assert answer(port, SMALL, "inspection checklist before restart") == reference
    assert getcontext().prec == 28  # the test itself left the ambient context as it found it


def test_many_threads_asking_at_once_all_get_the_same_answer():
    port = port_for(SMALL)
    reference = answer(port, SMALL, "inspection checklist before restart")
    barrier, answers, failures = threading.Barrier(8), [], []

    def work():
        try:
            barrier.wait()
            for _ in range(20):
                answers.append(answer(port, SMALL, "inspection checklist before restart"))
        except BaseException as error:  # pragma: no cover - reported below
            failures.append(error)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert failures == [] and len(answers) == 160 and all(a == reference for a in answers)


STORY = r"""
import hashlib, sys
sys.path[:0] = ['src', 'tests/support']
from eidos.knowledge import LEXICAL_SCHEME_ID, LexicalKnowledgePort, RetrievalRequest, build_snapshot, canonical_query_text
from eidos_knowledge_factories import SCHEME, small_corpus

snapshot = build_snapshot(small_corpus(), SCHEME)
port = LexicalKnowledgePort(snapshot, kb_id="kb1")
digest = hashlib.sha256()
for text in ("inspection checklist before restart", "the tidal barrier sensors", "grid operator notified", "audit turbine released", "zzz", "turbine"):
    request = RetrievalRequest(kb_id="kb1", snapshot_id=snapshot.snapshot_id, scheme_id=LEXICAL_SCHEME_ID, text=canonical_query_text(text), top_k=50, max_result_bytes=10**6)
    digest.update(port.retrieve(request).model_dump_json().encode())
print(digest.hexdigest())
"""


@functools.lru_cache(maxsize=None)
def story_digest(seed: str) -> str:
    completed = subprocess.run([sys.executable, "-c", STORY], capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED=seed))
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


@pytest.mark.parametrize("seed", ["1", "42", "112233", "2718281828"])
def test_every_answer_is_identical_under_any_hash_seed(seed):
    assert story_digest(seed) == story_digest("0") and len(story_digest("0")) == 64


def test_the_story_is_what_an_in_process_run_gives():
    port = port_for(SMALL)
    digest = hashlib.sha256()
    for text in ("inspection checklist before restart", "the tidal barrier sensors", "grid operator notified", "audit turbine released", "zzz", "turbine"):
        digest.update(answer(port, SMALL, text, top_k=50).model_dump_json().encode())
    assert digest.hexdigest() == story_digest("0")


def test_the_port_holds_no_state_a_call_could_change():
    port = port_for(SMALL)
    before = (port.kb_id, port.snapshot_id, port.scheme_id)
    for text in ("turbine", "audit", "zzz"):
        ask(port, SMALL, text)
    assert (port.kb_id, port.snapshot_id, port.scheme_id) == before
