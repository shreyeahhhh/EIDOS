"""Evidence records, their merge, the set-based independence resolution and the mapping of V1.2 documents into the knowledge identity
(decisions.md D-209, D-210, D-212, D-221; V1.3 Step 3).

What is proven: a record is exactly the chunk it says it is and traces back to its snapshot, document and source; the same chunk retrieved again is the same
evidence with one more query on it, and nothing else is merged; independence is counted over the set of cited evidence by the D-209 and D-221 rules, and what the
ledger does not hold is reported rather than counted; a V1.2 document receives a deterministic knowledge identity from its reference and its normalised content.
The legacy identities are pinned by literals computed independently of the implementation.
"""

import hashlib
import itertools
import json
import random
import re
import unicodedata

import pytest
from pydantic import ValidationError

from eidos.knowledge import (
    LEGACY_SCHEME_ID,
    EvidenceRecord,
    EvidenceRefusal,
    EvidenceRefusalCode,
    IndependenceResolution,
    KnowledgeChunk,
    build_snapshot,
    chunk_id_of,
    document_id_of,
    evidence_from_snapshot,
    legacy_supplied_record,
    legacy_tool_record,
    merge_evidence,
    normalise_text,
    resolve_independence,
)
from eidos_knowledge_factories import (
    BLOG_POST,
    GRID_AGREEMENT,
    OPS_MANUAL,
    SAFETY_AUDIT,
    SCHEME,
    chunk_of,
    doc,
    evidence_of,
    query_id,
    ref_of,
    small_corpus,
)

SNAPSHOT = build_snapshot(small_corpus(), SCHEME)
SOURCE_ID = re.compile(r"^legacy-[0-9a-f]{32}$")
EVIDENCE_REF = re.compile(r"^evidence:[0-9a-f]{16}$")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")).hexdigest()


def expected_legacy(identity: dict, text: str) -> dict:
    """A V1.2 document's knowledge identity, worked out by hand from the rule of D-210 and D-224, not by calling the implementation."""
    normalised = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    source_id = "legacy-" + canonical_digest({"version": "legacy-source-v1", **identity})[:32]
    document_id = digest(normalised)
    chunk_id = canonical_digest(
        {
            "version": "chunk-v1", "source_id": source_id, "document_id": document_id, "chunking_scheme_id": "legacy-artifact-v1",
            "start": 0, "end": len(normalised), "text_sha256": digest(normalised),
        }
    )
    return {"source_id": source_id, "document_id": document_id, "chunk_id": chunk_id, "evidence_ref": "evidence:" + chunk_id[:16], "text": normalised}


def record_or_fail(outcome) -> EvidenceRecord:
    assert isinstance(outcome, EvidenceRecord), outcome
    return outcome


def refusal_code(outcome) -> EvidenceRefusalCode:
    assert isinstance(outcome, EvidenceRefusal), outcome
    return outcome.code


# --- a record is the chunk it says it is -----------------------------------------------------------------------------------------


def test_a_record_holds_the_snapshots_chunk_and_names_the_snapshot_the_scheme_and_the_query():
    chunk = chunk_of(SNAPSHOT, "audit")
    record = evidence_of(SNAPSHOT, chunk, "goal")
    assert record.chunk == chunk
    assert record.snapshot_id == SNAPSHOT.snapshot_id
    assert record.chunking_scheme_id == SNAPSHOT.chunking_scheme_id == SCHEME.scheme_id
    assert record.retrieved_by == (query_id("goal"),)


def test_the_evidence_reference_is_evidence_and_the_first_sixteen_hex_digits_of_the_chunk_id():
    record = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "grid"))
    assert record.evidence_ref == "evidence:" + record.chunk.chunk_id[:16]
    assert EVIDENCE_REF.fullmatch(record.evidence_ref)


def test_a_record_traces_to_its_document_source_and_snapshot_by_the_step_2_identities():
    record = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "ops", 1))
    assert record.document_ref in SNAPSHOT.documents
    assert record.document_ref == ref_of("ops", OPS_MANUAL)
    assert record.chunk.source_id == "ops" and record.chunk.document_id == document_id_of(OPS_MANUAL)
    assert record.chunk.chunk_id == chunk_id_of(
        source_id="ops", document_id=record.chunk.document_id, chunking_scheme_id=SCHEME.scheme_id, start=record.chunk.start, end=record.chunk.end, text=record.chunk.text
    )
    assert record.snapshot_id == SNAPSHOT.snapshot_id


def test_a_chunk_the_snapshot_does_not_hold_is_refused_not_invented():
    other = build_snapshot((doc("elsewhere", "A chunk that is in a different corpus entirely."),), SCHEME)
    foreign = other.chunks[0]
    assert refusal_code(evidence_from_snapshot(SNAPSHOT, foreign.chunk_id, query_id=query_id("q1"))) is EvidenceRefusalCode.UNKNOWN_CHUNK
    assert refusal_code(evidence_from_snapshot(SNAPSHOT, "0" * 64, query_id=query_id("q1"))) is EvidenceRefusalCode.UNKNOWN_CHUNK


def test_a_malformed_query_id_is_a_contract_violation_not_a_refusal():
    chunk = chunk_of(SNAPSHOT, "grid")
    for bad in ("", "q1", "A" * 64, "g" * 64, "a" * 63):
        with pytest.raises(ValidationError):
            evidence_from_snapshot(SNAPSHOT, chunk.chunk_id, query_id=bad)


# --- identity is deterministic and depends on nothing about how it was reached --------------------------------------------------


def test_the_same_chunk_gives_the_same_evidence_whichever_way_the_corpus_was_declared():
    reference = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"))
    generator = random.Random(7)
    for _ in range(20):
        documents = list(small_corpus())
        generator.shuffle(documents)
        snapshot = build_snapshot(documents, SCHEME)
        assert evidence_of(snapshot, chunk_of(snapshot, "audit")) == reference


def test_the_query_changes_the_provenance_and_never_the_identity():
    chunk = chunk_of(SNAPSHOT, "audit")
    first, second = evidence_of(SNAPSHOT, chunk, "first query"), evidence_of(SNAPSHOT, chunk, "second query")
    assert first != second and first.retrieved_by != second.retrieved_by
    assert (first.evidence_ref, first.chunk, first.snapshot_id) == (second.evidence_ref, second.chunk, second.snapshot_id)


def test_distinct_chunks_have_distinct_evidence_references():
    references = {evidence_of(SNAPSHOT, chunk).evidence_ref for chunk in SNAPSHOT.chunks}
    assert len(references) == len(SNAPSHOT.chunks) == 13


def test_a_byte_identical_mirror_is_the_same_document_under_a_different_source_and_a_different_chunk():
    ops, mirror = chunk_of(SNAPSHOT, "ops"), chunk_of(SNAPSHOT, "mirror")
    a, b = evidence_of(SNAPSHOT, ops), evidence_of(SNAPSHOT, mirror)
    assert a.chunk.document_id == b.chunk.document_id and a.chunk.text == b.chunk.text
    assert a.chunk.source_id != b.chunk.source_id and a.chunk.chunk_id != b.chunk.chunk_id and a.evidence_ref != b.evidence_ref


# --- malformed and tampered evidence is rejected --------------------------------------------------------------------------------


def rebuilt(record: EvidenceRecord, **chunk_changes) -> dict:
    fields = record.model_dump()
    fields["chunk"] = {**fields["chunk"], **chunk_changes}
    fields["retrieved_by"] = tuple(fields["retrieved_by"])
    return fields


def test_a_record_that_claims_a_chunk_id_its_parts_do_not_have_is_rejected():
    record = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"))
    real = record.chunk.chunk_id
    for tampered in ({"chunk_id": real[:-1] + ("0" if real[-1] != "0" else "1")}, {"chunk_id": "f" * 64}):
        with pytest.raises(ValidationError, match="chunk id"):
            EvidenceRecord(**rebuilt(record, **tampered))


def test_a_record_whose_text_source_document_or_span_was_changed_is_rejected_because_its_chunk_id_no_longer_matches():
    record = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"))
    text = record.chunk.text
    same_length_text = ("X" if text[0] != "X" else "Y") + text[1:]
    for tampered in (
        {"text": same_length_text},
        {"source_id": "someone-else"},
        {"document_id": "0" * 64},
        {"start": record.chunk.start + 1, "end": record.chunk.end + 1},
    ):
        with pytest.raises(ValidationError):
            EvidenceRecord(**rebuilt(record, **tampered))


def test_a_record_whose_scheme_is_not_the_one_its_chunk_id_was_made_under_is_rejected():
    record = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"))
    with pytest.raises(ValidationError, match="chunk id"):
        EvidenceRecord(chunk=record.chunk, chunking_scheme_id="paragraph-pack-v1/max_words=13", snapshot_id=record.snapshot_id)


def test_a_record_json_that_was_edited_is_rejected_and_an_untouched_one_round_trips():
    record = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"), "q")
    assert EvidenceRecord.model_validate_json(record.model_dump_json()) == record
    document = json.loads(record.model_dump_json())
    document["chunk"]["text"] = document["chunk"]["text"].replace("audit", "AUDIT", 1)
    assert document["chunk"]["text"] != record.chunk.text
    with pytest.raises(ValidationError):
        EvidenceRecord.model_validate_json(json.dumps(document))


@pytest.mark.parametrize(
    "retrieved_by",
    [
        tuple(sorted((query_id("a"), query_id("b")), reverse=True)),
        (query_id("a"), query_id("a")),
        ("not-a-digest",),
        (query_id("a").upper(),),
        (query_id("a")[:-1],),
        ("",),
    ],
    ids=["unsorted", "duplicated", "not-hex", "upper-case", "short", "blank"],
)
def test_query_provenance_is_a_sorted_set_of_well_formed_query_ids(retrieved_by):
    record = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"))
    with pytest.raises(ValidationError):
        EvidenceRecord(chunk=record.chunk, chunking_scheme_id=record.chunking_scheme_id, snapshot_id=record.snapshot_id, retrieved_by=retrieved_by)


def test_provenance_must_be_a_tuple_a_list_is_not_accepted():
    record = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"))
    with pytest.raises(ValidationError):
        EvidenceRecord(chunk=record.chunk, chunking_scheme_id=record.chunking_scheme_id, snapshot_id=record.snapshot_id, retrieved_by=[query_id("a")])


def test_a_knowledge_record_must_name_its_snapshot_and_a_snapshot_must_be_well_formed():
    record = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"))
    with pytest.raises(ValidationError, match="snapshot"):
        EvidenceRecord(chunk=record.chunk, chunking_scheme_id=record.chunking_scheme_id)
    for bad in ("", "abc", "F" * 64, "z" * 64):
        with pytest.raises(ValidationError):
            EvidenceRecord(chunk=record.chunk, chunking_scheme_id=record.chunking_scheme_id, snapshot_id=bad)


def test_a_record_is_frozen_and_takes_no_undeclared_field():
    record = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"))
    with pytest.raises(ValidationError):
        record.snapshot_id = "0" * 64
    with pytest.raises(ValidationError):
        EvidenceRecord(chunk=record.chunk, chunking_scheme_id=record.chunking_scheme_id, snapshot_id=record.snapshot_id, score=0.5)


# --- the same evidence recorded again --------------------------------------------------------------------------------------------


def test_the_same_chunk_retrieved_by_the_same_query_again_is_the_same_record():
    record = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"), "q")
    assert merge_evidence(record, record) == record
    assert merge_evidence(record, evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"), "q")) == record


def test_the_same_chunk_retrieved_by_another_query_is_one_record_with_both_queries_sorted():
    chunk = chunk_of(SNAPSHOT, "audit")
    first, second = evidence_of(SNAPSHOT, chunk, "q1"), evidence_of(SNAPSHOT, chunk, "q2")
    merged = record_or_fail(merge_evidence(first, second))
    assert merged.retrieved_by == tuple(sorted({query_id("q1"), query_id("q2")}))
    assert (merged.chunk, merged.evidence_ref, merged.snapshot_id) == (first.chunk, first.evidence_ref, first.snapshot_id)


def test_the_merge_does_not_depend_on_the_order_the_queries_arrive_in():
    chunk = chunk_of(SNAPSHOT, "audit")
    records = [evidence_of(SNAPSHOT, chunk, f"query {n}") for n in range(5)]
    results = set()
    for ordering in itertools.permutations(records):
        held = ordering[0]
        for incoming in ordering[1:]:
            held = record_or_fail(merge_evidence(held, incoming))
        results.add(held)
    assert len(results) == 1
    assert next(iter(results)).retrieved_by == tuple(sorted(query_id(f"query {n}") for n in range(5)))


def test_a_merge_is_associative_with_a_record_that_already_holds_several_queries():
    chunk = chunk_of(SNAPSHOT, "audit")
    a, b, c = (evidence_of(SNAPSHOT, chunk, name) for name in "abc")
    left = record_or_fail(merge_evidence(record_or_fail(merge_evidence(a, b)), c))
    right = record_or_fail(merge_evidence(a, record_or_fail(merge_evidence(b, c))))
    assert left == right and len(left.retrieved_by) == 3


def colliding_records(monkeypatch):
    """Two records of different chunks that share an evidence reference: with references cut to one hex digit, twenty chunks must collide."""
    snapshot = build_snapshot(tuple(doc(f"s{n}", f"Document number {n} says something distinct about the plant.") for n in range(20)), SCHEME)
    monkeypatch.setattr("eidos.knowledge.identity.EVIDENCE_REF_HEX_LENGTH", 1)
    seen: dict[str, KnowledgeChunk] = {}
    for chunk in snapshot.chunks:
        if chunk.evidence_ref in seen:
            return evidence_of(snapshot, seen[chunk.evidence_ref]), evidence_of(snapshot, chunk)
        seen[chunk.evidence_ref] = chunk
    raise AssertionError("twenty chunks with one-digit references must collide")


def test_a_different_chunk_under_the_same_evidence_reference_is_refused_and_nothing_is_merged(monkeypatch):
    first, second = colliding_records(monkeypatch)
    assert first.evidence_ref == second.evidence_ref and first.chunk.chunk_id != second.chunk.chunk_id
    assert refusal_code(merge_evidence(first, second)) is EvidenceRefusalCode.EVIDENCE_REF_COLLISION
    assert refusal_code(merge_evidence(second, first)) is EvidenceRefusalCode.EVIDENCE_REF_COLLISION


def test_the_same_chunk_from_a_different_snapshot_is_refused_not_silently_merged():
    bigger = build_snapshot((*small_corpus(), doc("extra", "An additional document that makes this a different snapshot.")), SCHEME)
    chunk = chunk_of(SNAPSHOT, "audit")
    same_chunk = next(c for c in bigger.chunks if c.chunk_id == chunk.chunk_id)  # a chunk's id does not depend on the snapshot
    assert bigger.snapshot_id != SNAPSHOT.snapshot_id and same_chunk == chunk
    assert refusal_code(merge_evidence(evidence_of(SNAPSHOT, chunk), evidence_of(bigger, chunk))) is EvidenceRefusalCode.SNAPSHOT_CONFLICT


def test_only_records_of_one_evidence_reference_can_be_merged():
    with pytest.raises(ValueError, match="one evidence reference"):
        merge_evidence(evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit")), evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "grid")))


# --- independence is resolved over the set of cited evidence ---------------------------------------------------------------------


def cited_from(snapshot, *sources: str):
    """Evidence for every chunk of the given sources."""
    return [evidence_of(snapshot, chunk) for source in sources for chunk in snapshot.chunks if chunk.source_id == source]


def resolve(records, cited=None, derived_from=None, snapshot=SNAPSHOT):
    references = [r.evidence_ref for r in records] if cited is None else cited
    return resolve_independence(references, records, snapshot.derivation_map if derived_from is None else derived_from)


def test_the_same_chunk_cited_again_is_one_source_and_one_piece_of_evidence():
    (record,) = cited_from(SNAPSHOT, "grid")
    resolution = resolve([record], cited=[record.evidence_ref] * 3)
    assert resolution.sources == ("grid",) and resolution.source_count == 1 and resolution.evidence == (record.evidence_ref,)


def test_the_same_evidence_reached_through_several_retrievals_is_one_source():
    chunk = chunk_of(SNAPSHOT, "grid")
    records = [evidence_of(SNAPSHOT, chunk, f"query {n}") for n in range(4)]
    assert resolve(records).sources == ("grid",)


def test_several_chunks_of_one_document_are_one_source():
    records = cited_from(SNAPSHOT, "ops")
    assert len(records) == 4
    resolution = resolve(records)
    assert resolution.sources == ("ops",) and len(resolution.documents) == 1 and len(resolution.evidence) == 4


def test_several_documents_under_one_declared_source_are_one_source():
    snapshot = build_snapshot((doc("ops", "First procedure document."), doc("ops", "A second, different procedure document."), doc("audit", "An audit.")), SCHEME)
    records = cited_from(snapshot, "ops", "audit")
    resolution = resolve(records, snapshot=snapshot)
    assert len(resolution.documents) == 3 and resolution.sources == ("audit", "ops")


def test_identical_content_under_different_declared_sources_is_separate_sources():
    records = [evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "ops")), evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "mirror"))]
    resolution = resolve(records)
    assert resolution.sources == ("mirror", "ops")
    assert records[0].chunk.document_id == records[1].chunk.document_id


def test_a_declared_derivation_collapses_a_cited_document_onto_its_cited_origin():
    audit, blog = cited_from(SNAPSHOT, "audit")[0], cited_from(SNAPSHOT, "blog")[0]
    assert resolve([audit, blog]).sources == ("audit",)
    assert resolve([blog]).sources == ("blog",)  # the origin was not cited, so nothing collapses


def test_an_undeclared_derivation_is_never_inferred_from_similar_text():
    snapshot = build_snapshot(
        (doc("audit", SAFETY_AUDIT), doc("blog", BLOG_POST), doc("copy", SAFETY_AUDIT.replace("no turbine", "no generator"))), SCHEME
    )  # a blog and a near copy of the audit, both declared with no derivation
    records = cited_from(snapshot, "audit", "blog", "copy")
    assert resolve(records, snapshot=snapshot).sources == ("audit", "blog", "copy")


def chain():
    """Three documents of three sources where C derives from B and B from A, and a fourth that is independent."""
    a_text, b_text, c_text, d_text = "The primary record of the outage.", "A summary of the primary record.", "A summary of the summary.", "An unrelated inspection note."
    snapshot = build_snapshot(
        (doc("a", a_text), doc("b", b_text, ref_of("a", a_text)), doc("c", c_text, ref_of("b", b_text)), doc("d", d_text)), SCHEME
    )
    return snapshot, {source: cited_from(snapshot, source)[0] for source in "abcd"}


def test_a_derivation_is_direct_only_and_is_not_followed_through_a_chain():
    snapshot, e = chain()
    assert resolve([e["a"], e["c"]], snapshot=snapshot).sources == ("a", "c")  # c derives from b, which is not cited: c still counts
    assert resolve([e["a"], e["b"]], snapshot=snapshot).sources == ("a",)
    assert resolve([e["b"], e["c"]], snapshot=snapshot).sources == ("b",)
    assert resolve([e["a"], e["b"], e["c"]], snapshot=snapshot).sources == ("a",)  # c is set aside by b, b by a; only the root counts
    assert resolve([e["c"], e["d"]], snapshot=snapshot).sources == ("c", "d")


def test_every_subset_of_the_chain_counts_exactly_the_cited_documents_whose_declared_origin_is_not_cited():
    snapshot, e = chain()
    origin_of = {"b": "a", "c": "b"}  # the declarations of chain(), restated: c derives from b, b from a
    for size in range(5):
        for subset in itertools.combinations("abcd", size):
            expected = tuple(sorted(name for name in subset if origin_of.get(name) not in subset))
            assert resolve([e[name] for name in subset], snapshot=snapshot).sources == expected, subset


def test_a_reference_the_ledger_does_not_hold_is_reported_and_never_counted():
    (grid,) = cited_from(SNAPSHOT, "grid")
    ghost, other = "evidence:" + "0" * 16, "evidence:" + "f" * 16
    resolution = resolve([grid], cited=[other, grid.evidence_ref, ghost, ghost])
    assert resolution.sources == ("grid",) and resolution.evidence == (grid.evidence_ref,)
    assert resolution.unresolved == (ghost, other)


def test_nothing_cited_or_nothing_held_resolves_to_no_sources():
    empty = resolve_independence([], [], {})
    assert empty == IndependenceResolution(evidence=(), unresolved=(), documents=(), sources=())
    assert empty.source_count == 0
    only_unknown = resolve_independence(["evidence:" + "1" * 16], [], {})
    assert only_unknown.sources == () and only_unknown.unresolved == ("evidence:" + "1" * 16,)


def test_the_order_and_repetition_of_what_is_cited_and_of_what_is_held_change_nothing():
    records = cited_from(SNAPSHOT, "ops", "audit", "blog", "grid", "mirror")
    expected = resolve(records)
    generator = random.Random(2026)
    for _ in range(25):
        shuffled = list(records)
        generator.shuffle(shuffled)
        cited = [r.evidence_ref for r in shuffled] + [shuffled[0].evidence_ref]
        generator.shuffle(cited)
        assert resolve_independence(cited, shuffled + shuffled[:2], SNAPSHOT.derivation_map) == expected
    assert expected.sources == ("audit", "grid", "mirror", "ops")  # the blog derives from the cited audit


def test_the_derivations_of_documents_that_are_not_cited_change_nothing():
    grid, ops = cited_from(SNAPSHOT, "grid")[0], cited_from(SNAPSHOT, "ops")[0]
    assert resolve([grid, ops], derived_from={}).sources == resolve([grid, ops]).sources == ("grid", "ops")


def test_two_different_chunks_under_one_evidence_reference_cannot_be_resolved(monkeypatch):
    records = colliding_records(monkeypatch)
    with pytest.raises(ValueError, match="share an evidence reference"):
        resolve_independence([records[0].evidence_ref], records, {})


# --- V1.2 documents are given a knowledge identity from their reference and their normalised content (D-210) ------------------------

SUPPLIED_TEXT = "The tide gates close at dusk."
TOOL_TEXT = "Replay rebuilds a mission from its recorded events."


def test_a_supplied_document_has_the_identity_worked_out_by_hand():
    expected = expected_legacy({"kind": "supplied", "ref": "brief-1"}, SUPPLIED_TEXT)
    record = record_or_fail(legacy_supplied_record("brief-1", SUPPLIED_TEXT))
    assert (record.chunk.source_id, record.chunk.document_id, record.chunk.chunk_id, record.evidence_ref, record.chunk.text) == (
        expected["source_id"], expected["document_id"], expected["chunk_id"], expected["evidence_ref"], expected["text"],
    )
    assert expected["source_id"] == "legacy-330e9c098f149e8d1493bb101b0e3e25"  # literals: a change to any derivation is a deliberate, recorded change
    assert expected["document_id"] == "c147dcbc635add2585296a9b008e2678c7211127ae1ea4c7b33fa64a9e0a5bb6"
    assert expected["evidence_ref"] == "evidence:56f30299d3b696b8"


def test_a_tool_document_has_the_identity_worked_out_by_hand():
    expected = expected_legacy({"kind": "tool", "tool_id": "docs/search_documents", "document_id": "doc-replay"}, TOOL_TEXT)
    record = record_or_fail(legacy_tool_record("docs/search_documents", "doc-replay", TOOL_TEXT))
    assert (record.chunk.source_id, record.chunk.document_id, record.chunk.chunk_id, record.evidence_ref) == (
        expected["source_id"], expected["document_id"], expected["chunk_id"], expected["evidence_ref"],
    )
    assert expected["source_id"] == "legacy-0b712ff4dd9a5bedb32ef9ece037dab9"
    assert expected["document_id"] == "8330a691871b015f95e95959c97c44b211cb8fbd337450e6ff2d2754c0eef0f6"
    assert expected["evidence_ref"] == "evidence:5fbd82af98a10c98"


def test_a_v1_2_document_is_one_whole_chunk_with_no_snapshot_under_the_legacy_scheme():
    for record in (legacy_supplied_record("brief-1", SUPPLIED_TEXT), legacy_tool_record("docs/search_documents", "doc-replay", TOOL_TEXT)):
        record = record_or_fail(record)
        assert record.snapshot_id is None and record.chunking_scheme_id == LEGACY_SCHEME_ID == "legacy-artifact-v1" and record.retrieved_by == ()
        assert (record.chunk.start, record.chunk.end) == (0, len(record.chunk.text))
        assert SOURCE_ID.fullmatch(record.chunk.source_id) and EVIDENCE_REF.fullmatch(record.evidence_ref)
        assert record.chunk.chunk_id == chunk_id_of(
            source_id=record.chunk.source_id, document_id=record.chunk.document_id, chunking_scheme_id=LEGACY_SCHEME_ID, start=0, end=record.chunk.end, text=record.chunk.text
        )  # the Step 2 rule is reused as it stands


def test_the_same_reference_and_content_give_the_same_evidence_every_time():
    assert legacy_supplied_record("brief-1", SUPPLIED_TEXT) == legacy_supplied_record("brief-1", SUPPLIED_TEXT)
    assert legacy_tool_record("docs/search_documents", "doc-replay", TOOL_TEXT) == legacy_tool_record("docs/search_documents", "doc-replay", TOOL_TEXT)


def test_the_content_is_normalised_so_line_endings_and_unicode_form_do_not_change_the_identity():
    composed, decomposed = "caf" + chr(0xE9) + " opens\nat dawn", "cafe" + chr(0x301) + " opens\r\nat dawn"
    assert composed != decomposed
    assert legacy_supplied_record("menu", composed) == legacy_supplied_record("menu", decomposed) == legacy_supplied_record("menu", decomposed.replace("\r\n", "\r"))
    assert record_or_fail(legacy_supplied_record("menu", decomposed)).chunk.text == composed == normalise_text(decomposed)


def test_identical_content_under_different_references_is_separate_sources_with_one_document():
    a, b = record_or_fail(legacy_supplied_record("brief-1", SUPPLIED_TEXT)), record_or_fail(legacy_supplied_record("brief-2", SUPPLIED_TEXT))
    assert a.chunk.document_id == b.chunk.document_id
    assert a.chunk.source_id != b.chunk.source_id and a.evidence_ref != b.evidence_ref
    assert resolve_independence([a.evidence_ref, b.evidence_ref], [a, b], {}).source_count == 2


def test_one_reference_with_different_content_is_one_source_with_two_documents():
    a, b = record_or_fail(legacy_supplied_record("brief-1", "First version.")), record_or_fail(legacy_supplied_record("brief-1", "Second version."))
    assert a.chunk.source_id == b.chunk.source_id and a.chunk.document_id != b.chunk.document_id
    resolution = resolve_independence([a.evidence_ref, b.evidence_ref], [a, b], {})
    assert resolution.source_count == 1 and len(resolution.documents) == 2


def test_the_same_tool_and_provider_document_is_one_source_whatever_it_is_called_elsewhere():
    a = record_or_fail(legacy_tool_record("docs/search_documents", "doc-replay", TOOL_TEXT))
    assert a == record_or_fail(legacy_tool_record("docs/search_documents", "doc-replay", TOOL_TEXT))
    for other in (legacy_tool_record("docs/search_documents", "doc-budgets", TOOL_TEXT), legacy_tool_record("docs/other_tool", "doc-replay", TOOL_TEXT)):
        assert record_or_fail(other).chunk.source_id != a.chunk.source_id


def test_a_supplied_reference_and_a_tool_document_never_share_an_identity_even_when_they_read_alike():
    tool = record_or_fail(legacy_tool_record("docs/search_documents", "doc-replay", TOOL_TEXT))
    supplied = record_or_fail(legacy_supplied_record("tool:docs/search_documents:doc-replay", TOOL_TEXT))
    assert tool.chunk.source_id != supplied.chunk.source_id and tool.evidence_ref != supplied.evidence_ref


def test_a_document_with_no_content_is_refused_and_a_document_of_whitespace_is_one_chunk():
    assert refusal_code(legacy_supplied_record("empty", "")) is EvidenceRefusalCode.EMPTY_DOCUMENT
    assert refusal_code(legacy_tool_record("docs/search_documents", "doc-empty", "")) is EvidenceRefusalCode.EMPTY_DOCUMENT
    assert record_or_fail(legacy_supplied_record("blank", "\r\n")).chunk.text == "\n"


def test_the_legacy_source_id_is_a_valid_source_id_whatever_the_reference_looks_like():
    for reference in ("a", "x" * 5000, "spaces and : colons / slashes", "quote\"s and \\ backslash", chr(0x2603) + " snowman", "tool:docs/x:abc:def"):
        record = record_or_fail(legacy_supplied_record(reference, SUPPLIED_TEXT))
        assert SOURCE_ID.fullmatch(record.chunk.source_id)
    assert len({record_or_fail(legacy_supplied_record(r, SUPPLIED_TEXT)).chunk.source_id for r in ("a", "b", "a ", " a")}) == 4


def forged(record: EvidenceRecord, *, scheme: str | None = None, **chunk_changes) -> dict:
    """Fields for a record whose chunk id was recomputed to match the changed parts, so that only the rules specific to the kind of record can reject it."""
    chunk = {**record.chunk.model_dump(), **chunk_changes}
    chunk["end"] = chunk["start"] + len(chunk["text"]) if "text" in chunk_changes and "end" not in chunk_changes else chunk["end"]
    chunk["chunk_id"] = chunk_id_of(
        source_id=chunk["source_id"], document_id=chunk["document_id"], chunking_scheme_id=scheme or record.chunking_scheme_id,
        start=chunk["start"], end=chunk["end"], text=chunk["text"],
    )
    return {"chunk": chunk, "chunking_scheme_id": scheme or record.chunking_scheme_id, "snapshot_id": record.snapshot_id, "retrieved_by": record.retrieved_by}


LEGACY_FORGERIES = {
    "a source id that is not derived from a reference": (dict(source_id="brief-1"), "derived from its reference"),
    "a chunk that does not start at the beginning": (dict(start=1, text="x" + SUPPLIED_TEXT), "one whole normalised chunk"),
    "the whole text placed at an offset": (dict(start=5, end=5 + len(SUPPLIED_TEXT)), "one whole normalised chunk"),
    "text that is not the document the id names": (dict(text="Some other text entirely."), "one whole normalised chunk"),
    "a document id that is not the digest of the text": (dict(document_id=digest("something else")), "one whole normalised chunk"),
    "text that was not normalised": (dict(text="one\r\ntwo", document_id=document_id_of("one\r\ntwo")), "one whole normalised chunk"),
}


@pytest.mark.parametrize("forgery", sorted(LEGACY_FORGERIES))
def test_a_v1_2_record_whose_chunk_id_was_recomputed_is_still_rejected_by_the_rules_of_a_v1_2_document(forgery):
    changes, message = LEGACY_FORGERIES[forgery]
    record = record_or_fail(legacy_supplied_record("brief-1", SUPPLIED_TEXT))
    fields = forged(record, **changes)
    with pytest.raises(ValidationError, match=message):
        EvidenceRecord(**fields)


def test_a_v1_2_record_cannot_carry_a_snapshot_and_a_knowledge_record_cannot_go_without_one():
    legacy = record_or_fail(legacy_supplied_record("brief-1", SUPPLIED_TEXT))
    with pytest.raises(ValidationError, match="snapshot"):
        EvidenceRecord(chunk=legacy.chunk, chunking_scheme_id=LEGACY_SCHEME_ID, snapshot_id=SNAPSHOT.snapshot_id)
    fields = forged(legacy, scheme="paragraph-pack-v1/max_words=12")  # a real scheme name, with no snapshot
    with pytest.raises(ValidationError, match="snapshot"):
        EvidenceRecord(**fields)


def test_an_untampered_v1_2_record_is_accepted_by_the_same_construction_path_the_forgeries_use():
    record = record_or_fail(legacy_supplied_record("brief-1", SUPPLIED_TEXT))
    assert EvidenceRecord(**forged(record)) == record


def test_a_knowledge_record_cannot_pass_as_a_v1_2_document_by_naming_the_legacy_scheme():
    record = evidence_of(SNAPSHOT, chunk_of(SNAPSHOT, "audit"))
    chunk = record.chunk
    forged = chunk_id_of(source_id=chunk.source_id, document_id=chunk.document_id, chunking_scheme_id=LEGACY_SCHEME_ID, start=chunk.start, end=chunk.end, text=chunk.text)
    relabelled = KnowledgeChunk(
        chunk_id=forged, document_id=chunk.document_id, source_id=chunk.source_id, start=chunk.start, end=chunk.end, text=chunk.text
    )
    with pytest.raises(ValidationError):
        EvidenceRecord(chunk=relabelled, chunking_scheme_id=LEGACY_SCHEME_ID)


def test_v1_2_and_knowledge_evidence_can_be_counted_together_and_a_legacy_document_is_never_derived_from_anything():
    knowledge = cited_from(SNAPSHOT, "audit", "blog")
    legacy = [record_or_fail(legacy_supplied_record("brief-1", GRID_AGREEMENT)), record_or_fail(legacy_tool_record("docs/search_documents", "doc-replay", TOOL_TEXT))]
    resolution = resolve([*knowledge, *legacy])
    assert resolution.source_count == 3 and "audit" in resolution.sources and "blog" not in resolution.sources
    assert sum(1 for source in resolution.sources if source.startswith("legacy-")) == 2
