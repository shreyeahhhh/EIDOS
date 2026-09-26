"""The retrieval contracts: the request, the query form, ``query_id``, the hits, the result, the failure and the port
(decisions.md D-216, D-217, D-218, D-225; V1.3 Step 4, phase A).

What is proven: a request states everything and only accepts a query in its canonical form; a query has one identity, worked out here by hand and pinned by literals; a result is
ranked, ordered and labelled exactly as the contract says and checks itself; and a caller can tell, without knowing how a port works, when an answer does not answer its request.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from eidos.knowledge import (
    KB_ID_PATTERN,
    LEXICAL_SCHEME_ID,
    KnowledgePort,
    RetrievalFailure,
    RetrievalFailureKind,
    RetrievalRequest,
    RetrievalResult,
    RetrievedChunk,
    build_snapshot,
    canonical_query_text,
    query_id_of,
    result_problem,
)
from eidos.knowledge.retrieval import QUERY_ID_VERSION, QUERY_STRIP_CHARACTERS
from eidos_knowledge_factories import SCHEME, chunk_of, doc, small_corpus

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = build_snapshot(small_corpus(), SCHEME)
SNAPSHOT_ID = "a" * 64
QUERY = "how long must the sensors report normal readings"


def request(**overrides) -> RetrievalRequest:
    fields = dict(kb_id="kb1", snapshot_id=SNAPSHOT_ID, scheme_id=LEXICAL_SCHEME_ID, text=QUERY, top_k=5, max_result_bytes=4096) | overrides
    return RetrievalRequest(**fields)


def by_hand_query_id(*, kb_id, snapshot_id, scheme_id, text, top_k) -> str:
    """The identity of a query, worked out from the rule of D-225 (reading 3), not by calling the implementation."""
    canonical = json.dumps(
        {"version": "query-v1", "kb_id": kb_id, "snapshot_id": snapshot_id, "scheme_id": scheme_id, "text": text, "top_k": top_k},
        sort_keys=True, ensure_ascii=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def scored_result(scores_by_chunk, *, score_kind="test-scheme", query=None, **identity) -> RetrievalResult:
    """A result whose hits are the given ``(chunk, score)`` pairs, ranked in the order given."""
    fields = dict(query_id=(query or request()).query_id, kb_id="kb1", snapshot_id=SNAPSHOT_ID, scheme_id=LEXICAL_SCHEME_ID) | identity
    hits = tuple(RetrievedChunk(rank=rank, chunk=chunk, score=score) for rank, (chunk, score) in enumerate(scores_by_chunk, start=1))
    return RetrievalResult(**fields, score_kind=score_kind if scores_by_chunk else None, hits=hits)


CHUNKS = [chunk_of(SNAPSHOT, source) for source in ("ops", "audit", "grid", "blog", "mirror")]


def ordered_pair():
    """Two chunks in the ascending chunk-id order the contract requires for equal scores."""
    first, second = sorted(CHUNKS[:2], key=lambda c: c.chunk_id)
    return (first, second)


# --- a request states everything, and the query is in its canonical form ------------------------------------------------------------


def test_a_request_carries_the_knowledge_base_the_snapshot_the_scheme_the_query_and_both_bounds():
    r = request()
    assert (r.kb_id, r.snapshot_id, r.scheme_id, r.text, r.top_k, r.max_result_bytes) == ("kb1", SNAPSHOT_ID, LEXICAL_SCHEME_ID, QUERY, 5, 4096)


@pytest.mark.parametrize("missing", ["kb_id", "snapshot_id", "scheme_id", "text", "top_k", "max_result_bytes"])
def test_nothing_in_a_request_has_a_default(missing):
    fields = dict(kb_id="kb1", snapshot_id=SNAPSHOT_ID, scheme_id=LEXICAL_SCHEME_ID, text=QUERY, top_k=5, max_result_bytes=4096)
    del fields[missing]
    with pytest.raises(ValidationError):
        RetrievalRequest(**fields)


@pytest.mark.parametrize("kb_id", ["", " kb", "kb ", "-kb", ".kb", "k b", "kb/1", "x" * 65, "k" + chr(0xE9)])
def test_a_knowledge_base_id_has_the_shape_of_a_source_id(kb_id):
    with pytest.raises(ValidationError):
        request(kb_id=kb_id)


@pytest.mark.parametrize("kb_id", ["k", "kb1", "KB-1.a_b", "x" * 64])
def test_a_well_formed_knowledge_base_id_is_accepted(kb_id):
    assert request(kb_id=kb_id).kb_id == kb_id


def test_the_knowledge_base_id_pattern_is_the_source_id_pattern():
    assert KB_ID_PATTERN == r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"


@pytest.mark.parametrize("snapshot_id", ["", "abc", "A" * 64, "g" * 64, "a" * 63, "a" * 65])
def test_a_snapshot_id_is_sixty_four_lower_case_hex_digits(snapshot_id):
    with pytest.raises(ValidationError):
        request(snapshot_id=snapshot_id)


@pytest.mark.parametrize("scheme_id", ["", "/x", "-x", "x y", "x" * 129])
def test_a_scheme_id_has_the_shape_of_a_scheme_id(scheme_id):
    with pytest.raises(ValidationError):
        request(scheme_id=scheme_id)


@pytest.mark.parametrize("top_k", [0, -1, True, False, 1.5, "3", None])
def test_top_k_is_an_integer_of_at_least_one(top_k):
    with pytest.raises(ValidationError):
        request(top_k=top_k)


@pytest.mark.parametrize("bound", [0, -1, True, 1.5, "10", None])
def test_the_byte_bound_is_an_integer_of_at_least_one(bound):
    with pytest.raises(ValidationError):
        request(max_result_bytes=bound)


def test_the_smallest_bounds_are_accepted_and_the_contract_sets_no_ceiling():
    assert request(top_k=1, max_result_bytes=1).top_k == 1
    assert request(top_k=10**9, max_result_bytes=10**12).max_result_bytes == 10**12


def test_a_request_is_frozen_and_takes_no_undeclared_field():
    r = request()
    with pytest.raises(ValidationError):
        r.top_k = 6
    with pytest.raises(ValidationError):
        request(filters={"source": "ops"})


# --- the form of the query: one query, one text --------------------------------------------------------------------------------------


NBSP, IDEOGRAPHIC, LINE_SEPARATOR, UNIT_SEPARATOR = chr(0xA0), chr(0x3000), chr(0x2028), chr(0x1F)
E_ACUTE, COMBINING_ACUTE = chr(0xE9), chr(0x301)


@pytest.mark.parametrize(
    ("given", "canonical"),
    [
        ("plain query", "plain query"),
        ("  padded  ", "padded"),
        ("\t\n tabbed \r\n", "tabbed"),
        (NBSP + "no-break" + NBSP, "no-break"),
        (IDEOGRAPHIC + "wide" + IDEOGRAPHIC, "wide"),
        (LINE_SEPARATOR + "separated" + LINE_SEPARATOR, "separated"),
        ("two  spaces  inside", "two  spaces  inside"),
        ("line one\r\nline two", "line one\nline two"),
        ("line one\rline two", "line one\nline two"),
        ("cafe" + COMBINING_ACUTE + " opens", "caf" + E_ACUTE + " opens"),
        ("  Mixed CASE is kept  ", "Mixed CASE is kept"),
    ],
    ids=["plain", "spaces", "controls", "no-break", "ideographic", "line-separator", "inner-spaces", "crlf", "cr", "nfd", "case"],
)
def test_the_canonical_form_is_nfc_lf_and_stripped_of_the_fixed_whitespace_and_nothing_else(given, canonical):
    assert canonical_query_text(given) == canonical


def test_the_canonical_form_is_idempotent():
    for given in ("  a\r\nb  ", "cafe" + COMBINING_ACUTE, NBSP + "x", "already canonical"):
        once = canonical_query_text(given)
        assert canonical_query_text(once) == once


def test_the_four_separator_controls_are_not_stripped_unlike_str_strip():
    """The one place the canonical form differs from ``goal.strip()``: U+001C to U+001F are whitespace to ``str.strip`` but not to the fixed set (D-225 reading 2)."""
    text = UNIT_SEPARATOR + "query" + UNIT_SEPARATOR
    assert text.strip() == "query"
    assert canonical_query_text(text) == text
    assert set(QUERY_STRIP_CHARACTERS) == {chr(c) for c in (9, 10, 11, 12, 13, 32, 0x85, 0xA0, 0x1680, *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F, 0x205F, 0x3000)}


def test_a_request_accepts_only_a_query_that_is_already_canonical():
    assert request(text="already canonical").text == "already canonical"
    for text in (" leading", "trailing ", "line\r\nbreak", "cafe" + COMBINING_ACUTE, "tab\t"):
        with pytest.raises(ValidationError, match="canonical"):
            request(text=text)


def test_a_query_of_nothing_but_whitespace_cannot_be_a_request():
    for text in ("", " ", "\t\r\n", NBSP + IDEOGRAPHIC):
        with pytest.raises(ValidationError):
            request(text=text)
        assert canonical_query_text(text) == ""


# --- query_id --------------------------------------------------------------------------------------------------------------------------


def test_query_id_is_the_digest_worked_out_by_hand_and_pinned_by_a_literal():
    r = request()
    assert r.query_id == by_hand_query_id(kb_id="kb1", snapshot_id=SNAPSHOT_ID, scheme_id=LEXICAL_SCHEME_ID, text=QUERY, top_k=5)
    assert r.query_id == "90b228105d7ec9f1215886dbc14d7a20978ee7abe33ea5545ca1ac81932312ca"  # a change to the rule is a deliberate, recorded change
    assert QUERY_ID_VERSION == "query-v1"


def test_query_id_of_takes_keywords_and_agrees_with_the_request_property():
    r = request()
    assert query_id_of(top_k=5, text=QUERY, scheme_id=LEXICAL_SCHEME_ID, snapshot_id=SNAPSHOT_ID, kb_id="kb1") == r.query_id


def test_a_non_ascii_query_is_identified_through_ascii_escapes():
    text = "caf" + E_ACUTE + " opens"
    r = request(text=text, top_k=3)
    assert r.query_id == "0808b6d1a7e01e6f879b71871dd6287fad43f0c23ac10c4ecd052995a207e589"
    assert r.query_id == by_hand_query_id(kb_id="kb1", snapshot_id=SNAPSHOT_ID, scheme_id=LEXICAL_SCHEME_ID, text=text, top_k=3)


@pytest.mark.parametrize(
    "change",
    [dict(kb_id="kb2"), dict(snapshot_id="b" * 64), dict(scheme_id="lexical-bm25-v2/k1=1.2/b=0.75/tokens=word-v1"), dict(text="another query"), dict(top_k=6)],
    ids=["kb", "snapshot", "scheme", "text", "top_k"],
)
def test_every_input_of_the_identity_changes_it(change):
    assert request(**change).query_id != request().query_id


def test_the_byte_bound_is_not_part_of_a_query_identity():
    assert request(max_result_bytes=1).query_id == request(max_result_bytes=10**9).query_id == request().query_id


def test_the_same_inputs_give_the_same_query_id_however_they_are_stated():
    a = RetrievalRequest(kb_id="kb1", snapshot_id=SNAPSHOT_ID, scheme_id=LEXICAL_SCHEME_ID, text=QUERY, top_k=5, max_result_bytes=1)
    b = RetrievalRequest(max_result_bytes=99, top_k=5, text=QUERY, scheme_id=LEXICAL_SCHEME_ID, snapshot_id=SNAPSHOT_ID, kb_id="kb1")
    assert a.query_id == b.query_id


def test_a_query_id_is_sixty_four_lower_case_hex_digits_and_depends_on_no_other_state():
    r = request()
    assert len(r.query_id) == 64 and set(r.query_id) <= set("0123456789abcdef")
    assert request().query_id == r.query_id  # nothing about the caller, the plan, the execution, the clock or a counter


IDENTITY_STORY = """
import sys
sys.path.insert(0, 'src')
from eidos.knowledge import RetrievalRequest, canonical_query_text
texts = ["alpha beta", "gamma  delta", "epsilon", "zeta eta theta"]
ids = [RetrievalRequest(kb_id="kb1", snapshot_id="a" * 64, scheme_id="lexical-bm25-v1/k1=1.2/b=0.75/tokens=word-v1", text=canonical_query_text("  " + t + "\\r\\n"), top_k=n, max_result_bytes=9).query_id
       for n, t in enumerate(texts, start=1)]
print(",".join(ids))
"""


@pytest.mark.parametrize("seed", ["0", "1", "42", "2718281828"])
def test_query_ids_are_identical_under_every_hash_seed(seed):
    def run(value):
        result = subprocess.run([sys.executable, "-c", IDENTITY_STORY], capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED=value))
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    assert run(seed) == run("7")
    assert len(run(seed).split(",")) == 4


# --- hits --------------------------------------------------------------------------------------------------------------------------------


def test_a_hit_is_a_rank_a_chunk_and_a_score_only_where_the_scheme_provides_one():
    hit = RetrievedChunk(rank=1, chunk=CHUNKS[0])
    assert hit.score is None and hit.chunk == CHUNKS[0]
    assert RetrievedChunk(rank=2, chunk=CHUNKS[0], score=0.5).score == 0.5
    assert RetrievedChunk(rank=2, chunk=CHUNKS[0], score=3).score == 3.0  # an integer is a valid score


@pytest.mark.parametrize("rank", [0, -1, True, 1.0, "1", None])
def test_a_rank_is_an_integer_from_one(rank):
    with pytest.raises(ValidationError):
        RetrievedChunk(rank=rank, chunk=CHUNKS[0])


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf"), True, "0.5"])
def test_a_score_is_a_finite_number(score):
    with pytest.raises(ValidationError):
        RetrievedChunk(rank=1, chunk=CHUNKS[0], score=score)


def test_a_hit_knows_its_content_digest_and_its_evidence_reference():
    hit = RetrievedChunk(rank=1, chunk=CHUNKS[0])
    assert hit.content_digest == hashlib.sha256(CHUNKS[0].text.encode("utf-8")).hexdigest()
    assert hit.evidence_ref == "evidence:" + CHUNKS[0].chunk_id[:16]


def test_a_byte_identical_mirror_has_the_same_content_digest_and_a_different_evidence_reference():
    original, mirror = RetrievedChunk(rank=1, chunk=chunk_of(SNAPSHOT, "ops")), RetrievedChunk(rank=2, chunk=chunk_of(SNAPSHOT, "mirror"))
    assert original.content_digest == mirror.content_digest
    assert original.evidence_ref != mirror.evidence_ref


# --- a result is ranked, ordered and labelled ---------------------------------------------------------------------------------------


def test_an_empty_result_is_a_real_result_with_or_without_a_score_label():
    for kind in (None, "test-scheme"):
        result = RetrievalResult(query_id=request().query_id, kb_id="kb1", snapshot_id=SNAPSHOT_ID, scheme_id=LEXICAL_SCHEME_ID, score_kind=kind)
        assert result.hits == () and result.result_bytes == 0


def test_a_scored_result_is_ordered_by_score_descending_and_then_chunk_id_ascending():
    low, high = CHUNKS[0], CHUNKS[1]
    assert scored_result([(high, 2.0), (low, 1.0)]).hits[0].chunk == high
    first, second = ordered_pair()
    assert scored_result([(first, 1.0), (second, 1.0)]).hits[1].chunk == second  # equal scores: chunk id ascending


def test_a_result_out_of_order_is_rejected():
    low, high = CHUNKS[0], CHUNKS[1]
    with pytest.raises(ValidationError, match="ordered"):
        scored_result([(low, 1.0), (high, 2.0)])
    first, second = ordered_pair()
    with pytest.raises(ValidationError, match="ordered"):
        scored_result([(second, 1.0), (first, 1.0)])  # a tie in the wrong chunk-id order


def test_negative_scores_are_ordered_by_the_same_rule():
    a, b = CHUNKS[0], CHUNKS[1]
    assert scored_result([(a, -0.5), (b, -2.0)]).hits[0].chunk == a
    with pytest.raises(ValidationError, match="ordered"):
        scored_result([(a, -2.0), (b, -0.5)])


def test_ranks_run_from_one_in_order_with_no_gap_and_no_repeat():
    def hits(ranks):
        return tuple(RetrievedChunk(rank=r, chunk=CHUNKS[i]) for i, r in enumerate(ranks))

    identity = dict(query_id=request().query_id, kb_id="kb1", snapshot_id=SNAPSHOT_ID, scheme_id=LEXICAL_SCHEME_ID)
    RetrievalResult(**identity, hits=hits([1, 2, 3]))
    for bad in ([2, 3], [1, 3], [2, 1], [1, 1], [0, 1]):
        with pytest.raises(ValidationError):
            RetrievalResult(**identity, hits=hits(bad))


def test_a_chunk_is_a_hit_at_most_once():
    identity = dict(query_id=request().query_id, kb_id="kb1", snapshot_id=SNAPSHOT_ID, scheme_id=LEXICAL_SCHEME_ID)
    with pytest.raises(ValidationError, match="at most once"):
        RetrievalResult(**identity, hits=(RetrievedChunk(rank=1, chunk=CHUNKS[0]), RetrievedChunk(rank=2, chunk=CHUNKS[0])))


def test_a_score_is_labelled_and_a_labelled_result_scores_every_hit():
    identity = dict(query_id=request().query_id, kb_id="kb1", snapshot_id=SNAPSHOT_ID, scheme_id=LEXICAL_SCHEME_ID)
    scored = RetrievedChunk(rank=1, chunk=CHUNKS[0], score=1.0)
    unscored = RetrievedChunk(rank=2, chunk=CHUNKS[1])
    with pytest.raises(ValidationError, match="labelled"):
        RetrievalResult(**identity, hits=(scored,))  # a score without a label
    with pytest.raises(ValidationError, match="scores every hit"):
        RetrievalResult(**identity, score_kind="test-scheme", hits=(RetrievedChunk(rank=1, chunk=CHUNKS[0]),))
    with pytest.raises(ValidationError):
        RetrievalResult(**identity, score_kind="test-scheme", hits=(scored, unscored))
    unlabelled = RetrievalResult(**identity, hits=(RetrievedChunk(rank=1, chunk=CHUNKS[0]), unscored))  # a scheme with no score orders by its own rule
    assert unlabelled.score_kind is None


@pytest.mark.parametrize("kind", ["", "-x", "x y", "x" * 129])
def test_a_score_label_has_the_shape_of_a_scheme_id(kind):
    with pytest.raises(ValidationError):
        RetrievalResult(query_id=request().query_id, kb_id="kb1", snapshot_id=SNAPSHOT_ID, scheme_id=LEXICAL_SCHEME_ID, score_kind=kind)


def test_a_result_measures_its_text_in_utf8_bytes():
    hits = [(CHUNKS[0], 2.0), (CHUNKS[1], 1.0)]
    assert scored_result(hits).result_bytes == sum(len(c.text.encode("utf-8")) for c, _ in hits)


def test_a_result_measures_multi_byte_text_by_its_utf8_size_not_its_length():
    text = "caf" + chr(0xE9) + " " + chr(0x6C34) + " opens"
    snapshot = build_snapshot((doc("s1", text), doc("s2", "other words here")), SCHEME)
    chunk = next(c for c in snapshot.chunks if c.text == text)
    result = scored_result([(chunk, 1.0)])
    assert len(text) < len(text.encode("utf-8")) and result.result_bytes == len(text.encode("utf-8"))


def test_a_result_round_trips_through_json_and_a_tampered_one_is_rejected():
    result = scored_result([(CHUNKS[0], 2.0), (CHUNKS[1], 1.0)])
    assert RetrievalResult.model_validate_json(result.model_dump_json()) == result
    document = json.loads(result.model_dump_json())
    document["hits"][0]["rank"] = 2
    with pytest.raises(ValidationError):
        RetrievalResult.model_validate_json(json.dumps(document))
    document = json.loads(result.model_dump_json())
    document["hits"][0]["score"], document["hits"][1]["score"] = 1.0, 2.0
    with pytest.raises(ValidationError, match="ordered"):
        RetrievalResult.model_validate_json(json.dumps(document))


# --- what a caller can check without knowing the port -----------------------------------------------------------------------------


def test_a_result_that_answers_its_request_has_no_problem():
    r = request()
    assert result_problem(r, scored_result([(CHUNKS[0], 2.0), (CHUNKS[1], 1.0)], query=r)) is None
    assert result_problem(r, scored_result([], query=r)) is None


def test_a_result_for_another_query_is_a_problem():
    assert "different query" in result_problem(request(), scored_result([(CHUNKS[0], 1.0)], query=request(top_k=4)))


@pytest.mark.parametrize("field", ["kb_id", "snapshot_id", "scheme_id"])
def test_a_result_naming_another_knowledge_base_snapshot_or_scheme_is_a_problem(field):
    other = {"kb_id": "kb2", "snapshot_id": "b" * 64, "scheme_id": "other-scheme"}[field]
    assert field in result_problem(request(), scored_result([(CHUNKS[0], 1.0)], **{field: other}))


def test_more_hits_than_top_k_is_a_problem_and_exactly_top_k_is_not():
    r = request(top_k=2)
    two = scored_result([(CHUNKS[0], 3.0), (CHUNKS[1], 2.0)], query=r)
    three = scored_result([(CHUNKS[0], 3.0), (CHUNKS[1], 2.0), (CHUNKS[2], 1.0)], query=r)
    assert result_problem(r, two) is None
    assert "top_k" in result_problem(r, three)


def test_more_bytes_than_the_bound_is_a_problem_and_exactly_the_bound_is_not():
    hits = [(CHUNKS[0], 2.0)]
    size = len(CHUNKS[0].text.encode("utf-8"))
    at = request(max_result_bytes=size)
    over = request(max_result_bytes=size - 1)
    assert result_problem(at, scored_result(hits, query=at)) is None
    assert "byte bound" in result_problem(over, scored_result(hits, query=over))


def test_the_checks_are_made_in_a_fixed_order():
    r = request(top_k=1, max_result_bytes=1)
    bad = scored_result([(CHUNKS[0], 2.0), (CHUNKS[1], 1.0)], query=request(top_k=2), kb_id="kb2")
    assert "different query" in result_problem(r, bad)


# --- failures and the port ---------------------------------------------------------------------------------------------------------


def test_a_failure_names_one_of_four_kinds_and_says_why():
    assert [k.value for k in RetrievalFailureKind] == ["unavailable", "request_mismatch", "result_too_large", "malformed_result"]
    failure = RetrievalFailure(kind=RetrievalFailureKind.UNAVAILABLE, message="the index is not built")
    assert failure.kind is RetrievalFailureKind.UNAVAILABLE
    with pytest.raises(ValidationError):
        RetrievalFailure(kind=RetrievalFailureKind.UNAVAILABLE, message="")
    with pytest.raises(ValidationError):
        RetrievalFailure(kind="exploded", message="x")


def test_a_port_is_anything_that_answers_a_request_with_a_result_or_a_failure():
    class Fixed:
        def retrieve(self, request: RetrievalRequest) -> RetrievalResult | RetrievalFailure:
            return RetrievalFailure(kind=RetrievalFailureKind.UNAVAILABLE, message="closed")

    port: KnowledgePort = Fixed()
    assert port.retrieve(request()).kind is RetrievalFailureKind.UNAVAILABLE
