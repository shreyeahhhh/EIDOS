"""Building a snapshot from declared documents (decisions.md D-211, D-212, D-220, D-221; V1.3 Step 2).

Every special character is built from its code point, never typed, so no tool that rewrites text can quietly change what a test does.
"""

import itertools

import pytest

from eidos.knowledge import (
    ChunkingScheme,
    Derivation,
    IngestionRefusal,
    IngestionRefusalCode,
    KnowledgeSnapshot,
    build_snapshot,
    document_id_of,
)
from eidos_knowledge_factories import (
    BLOG_POST,
    GRID_AGREEMENT,
    OPS_MANUAL,
    SAFETY_AUDIT,
    SCHEME,
    doc,
    ref_of,
    small_corpus,
)

Code = IngestionRefusalCode
E_ACUTE = chr(0xE9)
ACUTE = chr(0x301)
NBSP = chr(0xA0)
IDEOGRAPHIC_SPACE = chr(0x3000)
LONE_SURROGATE = chr(0xD800)


def refusal(documents, scheme=SCHEME) -> IngestionRefusal:
    result = build_snapshot(documents, scheme)
    assert isinstance(result, IngestionRefusal), result
    return result


def snapshot(documents, scheme=SCHEME) -> KnowledgeSnapshot:
    result = build_snapshot(documents, scheme)
    assert isinstance(result, KnowledgeSnapshot), result
    return result


# --- a snapshot ------------------------------------------------------------------------------------------------------------------


def test_the_small_corpus_becomes_thirteen_chunks_counted_by_hand():
    # 17 + 17 words in two paragraphs of the manual (12 + 5 each), 21 in the audit (12 + 9), 10 in the grid agreement, 18 in the blog (12 + 6), and the mirror as the manual
    result = snapshot(small_corpus())
    counts = {}
    for chunk in result.chunks:
        counts[chunk.source_id] = counts.get(chunk.source_id, 0) + 1
    assert counts == {"ops": 4, "audit": 2, "grid": 1, "blog": 2, "mirror": 4}
    assert len(result.chunks) == 13
    assert result.chunking_scheme_id == SCHEME.scheme_id == "paragraph-pack-v1/max_words=12"


def test_every_chunk_is_within_the_bound_and_is_a_span_of_its_document():
    for chunk in snapshot(small_corpus()).chunks:
        assert 1 <= len(chunk.text.split()) <= SCHEME.max_words
        assert len(chunk.text) == chunk.end - chunk.start


def test_chunks_are_in_canonical_order():
    chunks = snapshot(small_corpus()).chunks
    keys = [(c.source_id, c.document_id, c.start) for c in chunks]
    assert keys == sorted(keys) and len(set(keys)) == len(keys)


def test_the_documents_are_the_declared_ones_and_the_derivation_is_recorded_once():
    result = snapshot(small_corpus())
    assert {r.source_id for r in result.documents} == {"ops", "audit", "grid", "blog", "mirror"}
    assert result.derivations == (Derivation(document=ref_of("blog", BLOG_POST), origin=ref_of("audit", SAFETY_AUDIT)),)
    assert result.derivation_map == {ref_of("blog", BLOG_POST): frozenset({ref_of("audit", SAFETY_AUDIT)})}


# --- the same content under two sources ------------------------------------------------------------------------------------------


def test_a_byte_identical_mirror_is_one_document_content_under_two_sources_with_no_shared_chunk_or_reference():
    result = snapshot(small_corpus())
    original = [c for c in result.chunks if c.source_id == "ops"]
    mirror = [c for c in result.chunks if c.source_id == "mirror"]
    assert [c.text for c in original] == [c.text for c in mirror]
    assert {c.document_id for c in original} == {c.document_id for c in mirror} == {document_id_of(OPS_MANUAL)}
    assert not {c.chunk_id for c in original} & {c.chunk_id for c in mirror}
    assert not {c.evidence_ref for c in original} & {c.evidence_ref for c in mirror}
    assert ref_of("ops", OPS_MANUAL) != ref_of("mirror", OPS_MANUAL) and ref_of("ops", OPS_MANUAL).document_id == ref_of("mirror", OPS_MANUAL).document_id


def test_a_mirror_may_declare_that_it_derives_from_the_original_across_sources():
    result = snapshot((doc("ops", OPS_MANUAL), doc("mirror", OPS_MANUAL, ref_of("ops", OPS_MANUAL))))
    assert result.derivations == (Derivation(document=ref_of("mirror", OPS_MANUAL), origin=ref_of("ops", OPS_MANUAL)),)


# --- identity of the snapshot ----------------------------------------------------------------------------------------------------


def test_the_snapshot_does_not_depend_on_the_order_the_documents_were_given_in():
    baseline = snapshot(small_corpus())
    for order in itertools.permutations(small_corpus()):
        assert snapshot(order) == baseline


def test_the_snapshot_accepts_any_iterable_of_documents():
    baseline = snapshot(small_corpus())
    assert snapshot(list(small_corpus())) == baseline
    assert snapshot(iter(small_corpus())) == baseline
    assert snapshot(document for document in small_corpus()) == baseline


@pytest.mark.parametrize("change", ["scheme", "document added", "text changed", "source renamed", "derivation dropped", "derivation added"])
def test_every_part_of_the_corpus_changes_the_snapshot_id(change):
    base = list(small_corpus())
    scheme = SCHEME
    if change == "scheme":
        scheme = ChunkingScheme(max_words=13)
    elif change == "document added":
        base.append(doc("extra", "one more document"))
    elif change == "text changed":
        base[2] = doc("grid", GRID_AGREEMENT + " ")  # a trailing space is a different document: only line endings and the Unicode form are normalised
    elif change == "source renamed":
        base[2] = doc("grid2", GRID_AGREEMENT)
    elif change == "derivation dropped":
        base[3] = doc("blog", BLOG_POST)
    else:
        base[2] = doc("grid", GRID_AGREEMENT, ref_of("audit", SAFETY_AUDIT))
    assert snapshot(base, scheme).snapshot_id != snapshot(small_corpus()).snapshot_id


def test_line_endings_and_unicode_form_do_not_change_the_snapshot():
    text = "Caf" + E_ACUTE + " au lait is served.\n\nSecond paragraph here."
    variants = [text, text.replace("\n", "\r\n"), text.replace(E_ACUTE, "e" + ACUTE), text.replace("\n", "\r")]
    assert variants[2] != variants[0]
    assert len({snapshot((doc("cafe", variant),)).snapshot_id for variant in variants}) == 1


def test_building_twice_gives_equal_snapshots():
    assert snapshot(small_corpus()) == snapshot(small_corpus())


# --- refusals --------------------------------------------------------------------------------------------------------------------


def test_a_corpus_with_no_document_is_refused():
    for empty in ((), [], iter(())):
        assert refusal(empty).code is Code.EMPTY_CORPUS


@pytest.mark.parametrize("source_id", ["", " ", "a b", "a\n", "-a", ".a", "x" * 65, E_ACUTE, "a/b"])
def test_a_document_without_a_valid_declared_source_is_refused_and_no_source_is_invented(source_id):
    result = refusal((doc(source_id, "some words here"),))
    assert result.code is Code.INVALID_SOURCE_ID
    assert "document 0" in result.message and "no default is invented" in result.message


def test_text_that_cannot_be_encoded_is_refused():
    result = refusal((doc("ops", "lone surrogate " + LONE_SURROGATE + " inside"),))
    assert result.code is Code.INVALID_TEXT and "document 0" in result.message and "'ops'" in result.message


@pytest.mark.parametrize("text", ["", " ", "\n\n", "  \t \r\n ", NBSP + IDEOGRAPHIC_SPACE])
def test_a_document_with_no_words_is_refused(text):
    assert refusal((doc("ops", text),)).code is Code.EMPTY_DOCUMENT


def test_the_same_document_declared_twice_under_one_source_is_refused_even_when_written_differently():
    assert refusal((doc("ops", "one two"), doc("ops", "one two"))).code is Code.DUPLICATE_DOCUMENT
    assert refusal((doc("ops", "one\ntwo"), doc("ops", "one\r\ntwo"))).code is Code.DUPLICATE_DOCUMENT
    assert refusal((doc("ops", "caf" + E_ACUTE + " x"), doc("ops", "cafe" + ACUTE + " x"))).code is Code.DUPLICATE_DOCUMENT
    assert "document 1" in refusal((doc("ops", "one two"), doc("ops", "one two"))).message


def test_the_same_document_under_two_sources_is_not_a_duplicate():
    assert isinstance(build_snapshot((doc("a", "one two"), doc("b", "one two")), SCHEME), KnowledgeSnapshot)


def test_a_derivation_from_a_document_that_is_not_in_the_corpus_is_refused():
    result = refusal((doc("blog", BLOG_POST, ref_of("audit", SAFETY_AUDIT)),))
    assert result.code is Code.UNKNOWN_DERIVATION_TARGET and "not in the corpus" in result.message
    assert refusal((doc("audit", SAFETY_AUDIT), doc("blog", BLOG_POST, ref_of("wrongsource", SAFETY_AUDIT)))).code is Code.UNKNOWN_DERIVATION_TARGET


def test_a_document_declared_derived_from_itself_is_refused():
    assert refusal((doc("ops", "a b c", ref_of("ops", "a b c")),)).code is Code.SELF_DERIVATION
    assert refusal((doc("ops", "a\nb c", ref_of("ops", "a\r\nb c")),)).code is Code.SELF_DERIVATION  # the same document written with other line endings


@pytest.mark.parametrize("texts", [("alpha one", "beta two"), ("alpha one", "beta two", "gamma three")])
def test_a_cycle_of_derivations_is_refused(texts):
    sources = [f"s{n}" for n in range(len(texts))]
    documents = tuple(
        doc(sources[n], texts[n], ref_of(sources[(n + 1) % len(texts)], texts[(n + 1) % len(texts)])) for n in range(len(texts))
    )
    result = refusal(documents)
    assert result.code is Code.DERIVATION_CYCLE and "cycle" in result.message


def test_a_chain_and_a_diamond_of_derivations_are_fine():
    a, b, c, d = "text alpha", "text beta", "text gamma", "text delta"
    chain = (doc("s1", a), doc("s2", b, ref_of("s1", a)), doc("s3", c, ref_of("s2", b)))
    diamond = (doc("s1", a), doc("s2", b, ref_of("s1", a)), doc("s3", c, ref_of("s1", a)), doc("s4", d, ref_of("s2", b), ref_of("s3", c)))
    assert len(snapshot(chain).derivations) == 2 and len(snapshot(diamond).derivations) == 4


def test_a_derivation_declared_twice_is_recorded_once():
    result = snapshot((doc("a", "one\ntwo"), doc("b", "three four", ref_of("a", "one\ntwo"), ref_of("a", "one\r\ntwo"))))
    assert len(result.derivations) == 1


def test_two_chunks_that_would_share_an_evidence_reference_are_refused(monkeypatch):
    many = doc("ops", " ".join(f"w{n}" for n in range(60)))
    monkeypatch.setattr("eidos.knowledge.identity.EVIDENCE_REF_HEX_LENGTH", 1)
    result = refusal((many,), ChunkingScheme(max_words=1))
    assert result.code is Code.EVIDENCE_REF_COLLISION and "evidence:" in result.message


def test_a_derivation_problem_is_reported_before_an_evidence_reference_collision(monkeypatch):
    many = doc("ops", " ".join(f"w{n}" for n in range(60)), ref_of("ghost", "nowhere"))
    monkeypatch.setattr("eidos.knowledge.identity.EVIDENCE_REF_HEX_LENGTH", 1)
    assert refusal((many,), ChunkingScheme(max_words=1)).code is Code.UNKNOWN_DERIVATION_TARGET


def test_the_first_refusal_is_reported_in_a_fixed_order():
    valid = doc("ops", "one two")
    # document by document, in the order given
    assert refusal((valid, doc("a", ""), doc("", "x"))).code is Code.EMPTY_DOCUMENT
    assert refusal((valid, doc("", "x"), doc("a", ""))).code is Code.INVALID_SOURCE_ID
    assert "document 1" in refusal((valid, doc("", "x"), doc("a", ""))).message
    # within one document: the source, then the text
    assert refusal((doc("", ""),)).code is Code.INVALID_SOURCE_ID
    assert refusal((doc("", LONE_SURROGATE),)).code is Code.INVALID_SOURCE_ID
    assert refusal((doc("ops", LONE_SURROGATE),)).code is Code.INVALID_TEXT
    # every document is checked before any derivation is
    assert refusal((doc("blog", BLOG_POST, ref_of("audit", SAFETY_AUDIT)), doc("", "x"))).code is Code.INVALID_SOURCE_ID
    # an empty document is refused before it can be counted a duplicate
    assert refusal((doc("ops", " "), doc("ops", " "))).code is Code.EMPTY_DOCUMENT


def test_a_domain_problem_is_returned_not_raised_and_the_input_documents_are_untouched():
    documents = (doc("ops", "one two", ref_of("nowhere", "x")),)
    before = documents[0].model_dump()
    build_snapshot(documents, SCHEME)
    assert documents[0].model_dump() == before


def test_a_manifest_entry_that_is_not_a_document_is_a_programming_error():
    with pytest.raises(AttributeError):
        build_snapshot(("not a document",), SCHEME)  # type: ignore[arg-type]


def test_the_result_of_a_build_is_a_valid_self_checking_snapshot():
    result = snapshot(small_corpus())
    assert KnowledgeSnapshot.model_validate_json(result.model_dump_json()) == result
    assert all(isinstance(d, Derivation) for d in result.derivations)
