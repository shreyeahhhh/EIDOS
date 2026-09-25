"""The knowledge contracts and their self-validation (decisions.md D-209, D-211, D-212, D-221; V1.3 Step 2)."""

import random

import pytest
from pydantic import ValidationError

from eidos.knowledge import (
    ChunkingScheme,
    Derivation,
    DocumentRef,
    IngestionRefusal,
    IngestionRefusalCode,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSnapshot,
    build_snapshot,
    chunk_id_of,
    evidence_ref_of,
    snapshot_id_of,
)
from eidos.knowledge.contracts import derivation_problem
from eidos_knowledge_factories import doc, ref_of

HEX_A, HEX_B = "a" * 64, "b" * 64


# --- DocumentRef and KnowledgeDocument -------------------------------------------------------------------------------------------


def test_a_document_ref_needs_a_valid_source_and_a_sha256_document_id():
    assert DocumentRef(source_id="ops", document_id=HEX_A).source_id == "ops"
    for kwargs in (
        dict(source_id="", document_id=HEX_A), dict(source_id="a b", document_id=HEX_A), dict(source_id="a\n", document_id=HEX_A),
        dict(source_id="ops", document_id="A" * 64), dict(source_id="ops", document_id="a" * 63), dict(source_id="ops", document_id="a" * 64 + "\n"),
    ):
        with pytest.raises(ValidationError):
            DocumentRef(**kwargs)


def test_a_manifest_entry_is_lenient_so_that_ingestion_and_not_construction_refuses_it():
    entry = KnowledgeDocument(source_id="not a valid id", text="")
    assert entry.derived_from == ()
    assert isinstance(build_snapshot((entry,), ChunkingScheme(max_words=3)), IngestionRefusal)


def test_a_manifest_entry_must_still_state_a_source_and_text():
    with pytest.raises(ValidationError):
        KnowledgeDocument(text="x")
    with pytest.raises(ValidationError):
        KnowledgeDocument(source_id="ops")


def test_contracts_are_frozen_closed_and_strict():
    reference = DocumentRef(source_id="ops", document_id=HEX_A)
    with pytest.raises(ValidationError):
        reference.source_id = "other"
    with pytest.raises(ValidationError):
        DocumentRef(source_id="ops", document_id=HEX_A, extra="x")
    with pytest.raises(ValidationError):
        KnowledgeDocument(source_id="ops", text=5)
    with pytest.raises(ValidationError):
        KnowledgeDocument(source_id="ops", text="x", derived_from=[reference])  # a tuple, not a list
    assert hash(reference) == hash(DocumentRef(source_id="ops", document_id=HEX_A))


# --- KnowledgeChunk --------------------------------------------------------------------------------------------------------------


def chunk(**changes):
    values = dict(chunk_id=HEX_A, document_id=HEX_B, source_id="ops", start=0, end=5, text="hello")
    values.update(changes)
    return KnowledgeChunk(**values)


def test_a_chunk_is_exactly_the_span_of_its_text():
    assert chunk().text == "hello"
    for changes in (dict(end=4), dict(end=6), dict(start=5), dict(start=6, end=5), dict(text=""), dict(start=-1), dict(end=0, start=0, text="")):
        with pytest.raises(ValidationError):
            chunk(**changes)


def test_a_chunk_names_valid_ids_and_a_valid_source():
    for changes in (dict(chunk_id="x"), dict(document_id="B" * 64), dict(source_id="a b"), dict(source_id="")):
        with pytest.raises(ValidationError):
            chunk(**changes)


def test_a_chunk_knows_its_document_and_its_evidence_reference():
    built = chunk(chunk_id="0123456789abcdef" + "0" * 48)
    assert built.document_ref == DocumentRef(source_id="ops", document_id=HEX_B)
    assert built.evidence_ref == "evidence:0123456789abcdef" == evidence_ref_of(built.chunk_id)


# --- Derivation ------------------------------------------------------------------------------------------------------------------


def test_a_document_cannot_be_declared_derived_from_itself():
    reference = DocumentRef(source_id="ops", document_id=HEX_A)
    with pytest.raises(ValidationError):
        Derivation(document=reference, origin=reference)
    Derivation(document=reference, origin=DocumentRef(source_id="mirror", document_id=HEX_A))  # the same content under another source is a different document
    Derivation(document=reference, origin=DocumentRef(source_id="ops", document_id=HEX_B))


# --- derivation_problem ----------------------------------------------------------------------------------------------------------

R = [DocumentRef(source_id=f"s{n}", document_id=f"{n:x}" * 64) for n in range(1, 7)]
S1, S2, S3, S4, S5, S6 = R


def problem(documents, edges):
    found = derivation_problem(documents, edges)
    return None if found is None else found[0]


@pytest.mark.parametrize("edges", [
    [],
    [(S2, S1)],
    [(S2, S1), (S3, S2), (S4, S3)],
    [(S2, S1), (S3, S1), (S4, S2), (S4, S3)],
    [(S3, S1), (S3, S2)],
    [(S2, S1), (S2, S1)],
])
def test_declarations_with_no_cycle_and_only_known_documents_are_fine(edges):
    assert problem(R, edges) is None


def test_a_self_derivation_is_the_first_thing_reported():
    assert problem(R, [(S1, S1)]) is IngestionRefusalCode.SELF_DERIVATION
    assert problem(R, [(S2, S1), (S3, S3)]) is IngestionRefusalCode.SELF_DERIVATION
    assert problem(R, [(S1, S1), (S2, DocumentRef(source_id="zz", document_id="e" * 64))]) is IngestionRefusalCode.SELF_DERIVATION


def test_an_endpoint_that_is_not_a_document_is_reported_before_any_cycle():
    stranger = DocumentRef(source_id="stranger", document_id="e" * 64)
    assert problem(R, [(S2, stranger)]) is IngestionRefusalCode.UNKNOWN_DERIVATION_TARGET
    assert problem(R, [(stranger, S2)]) is IngestionRefusalCode.UNKNOWN_DERIVATION_TARGET
    assert problem(R, [(S1, S2), (S2, S1), (S3, stranger)]) is IngestionRefusalCode.UNKNOWN_DERIVATION_TARGET


@pytest.mark.parametrize("edges", [
    [(S1, S2), (S2, S1)],
    [(S1, S2), (S2, S3), (S3, S1)],
    [(S1, S2), (S2, S3), (S3, S4), (S4, S2)],
    [(S5, S1), (S1, S2), (S2, S1)],
    [(S3, S4), (S4, S3), (S1, S2)],
])
def test_a_cycle_of_any_length_anywhere_in_the_declarations_is_found(edges):
    assert problem(R, edges) is IngestionRefusalCode.DERIVATION_CYCLE


def test_a_message_names_the_offending_document_and_the_result_does_not_depend_on_the_order_given():
    edges = [(S1, S2), (S2, S3), (S3, S1), (S5, S4)]
    baseline = derivation_problem(R, edges)
    assert baseline[0] is IngestionRefusalCode.DERIVATION_CYCLE and baseline[1].startswith("the derived_from declarations contain a cycle")
    assert "s1/" in baseline[1]  # of the documents that cannot be resolved, the first in canonical order is named
    rng = random.Random(7)
    for _ in range(25):
        shuffled = edges[:]
        rng.shuffle(shuffled)
        documents = R[:]
        rng.shuffle(documents)
        assert derivation_problem(documents, shuffled) == baseline
    assert "s1/" in derivation_problem(R, [(S1, S1)])[1]


# --- KnowledgeSnapshot -----------------------------------------------------------------------------------------------------------


def valid_snapshot(*extra_documents):
    snapshot = build_snapshot(
        (doc("ops", "one two three four five six"), doc("audit", "alpha beta gamma delta"), *extra_documents), ChunkingScheme(max_words=3)
    )
    assert isinstance(snapshot, KnowledgeSnapshot)
    return snapshot


def rebuild(snapshot, **changes):
    values = dict(
        snapshot_id=snapshot.snapshot_id, chunking_scheme_id=snapshot.chunking_scheme_id, chunks=snapshot.chunks, derivations=snapshot.derivations
    )
    values.update(changes)
    return KnowledgeSnapshot(**values)


def test_a_snapshot_that_is_what_it_says_is_accepted():
    snapshot = valid_snapshot()
    assert rebuild(snapshot) == snapshot
    assert len(snapshot.chunks) == 4
    assert snapshot.documents == tuple(sorted(snapshot.documents, key=lambda r: (r.source_id, r.document_id)))
    assert {r.source_id for r in snapshot.documents} == {"ops", "audit"}


def test_a_snapshot_needs_at_least_one_chunk():
    snapshot = valid_snapshot()
    with pytest.raises(ValidationError, match="at least 1"):
        rebuild(snapshot, chunks=())


def test_a_chunk_whose_id_is_not_the_id_of_its_parts_is_refused():
    snapshot = valid_snapshot()
    first = snapshot.chunks[0]
    forged = KnowledgeChunk(**{**first.model_dump(), "chunk_id": chunk_id_of(
        source_id="ops", document_id=first.document_id, chunking_scheme_id="another-scheme", start=first.start, end=first.end, text=first.text
    )})
    with pytest.raises(ValidationError, match="chunk id"):
        rebuild(snapshot, chunks=(forged, *snapshot.chunks[1:]))


def test_changing_a_chunks_text_without_changing_its_id_is_refused():
    snapshot = valid_snapshot()
    first = snapshot.chunks[0]
    text = "X" * len(first.text)
    tampered = KnowledgeChunk(**{**first.model_dump(), "text": text})
    with pytest.raises(ValidationError, match="chunk id"):
        rebuild(snapshot, chunks=(tampered, *snapshot.chunks[1:]))


def test_chunks_must_be_in_canonical_order_and_listed_once():
    snapshot = valid_snapshot()
    with pytest.raises(ValidationError, match="canonical order"):
        rebuild(snapshot, chunks=tuple(reversed(snapshot.chunks)))
    with pytest.raises(ValidationError, match="canonical order"):
        rebuild(snapshot, chunks=(snapshot.chunks[0], snapshot.chunks[0], *snapshot.chunks[1:]))


def test_chunks_of_one_document_may_not_overlap():
    snapshot = valid_snapshot()
    ops = [c for c in snapshot.chunks if c.source_id == "ops"]
    scheme = snapshot.chunking_scheme_id
    overlapping = KnowledgeChunk(
        chunk_id=chunk_id_of(source_id="ops", document_id=ops[0].document_id, chunking_scheme_id=scheme, start=ops[0].end - 2, end=ops[0].end + 3, text="abcde"),
        document_id=ops[0].document_id, source_id="ops", start=ops[0].end - 2, end=ops[0].end + 3, text="abcde",
    )
    others = [c for c in snapshot.chunks if c not in ops]
    ordered = tuple(sorted([*ops, overlapping], key=lambda c: (c.source_id, c.document_id, c.start)))
    with pytest.raises(ValidationError, match="overlap"):
        rebuild(snapshot, chunks=(*others, *ordered))


def test_chunks_that_touch_are_not_overlapping_but_chunks_that_share_a_position_are():
    scheme = "paragraph-pack-v1/max_words=12"

    def make(start, text):
        end = start + len(text)
        chunk_id = chunk_id_of(source_id="ops", document_id=HEX_B, chunking_scheme_id=scheme, start=start, end=end, text=text)
        return KnowledgeChunk(chunk_id=chunk_id, document_id=HEX_B, source_id="ops", start=start, end=end, text=text)

    def assemble(*chunks):
        snapshot_id = snapshot_id_of(chunking_scheme_id=scheme, documents=[("ops", HEX_B)], derivations=[])
        return KnowledgeSnapshot(snapshot_id=snapshot_id, chunking_scheme_id=scheme, chunks=chunks)

    assert len(assemble(make(0, "aaaaa"), make(5, "bbbbb")).chunks) == 2
    with pytest.raises(ValidationError, match="overlap"):
        assemble(make(0, "aaaaa"), make(4, "bbbbb"))


def test_two_chunks_may_not_share_an_evidence_reference(monkeypatch):
    snapshot = build_snapshot((doc("ops", " ".join(f"w{n}" for n in range(60))),), ChunkingScheme(max_words=1))
    assert isinstance(snapshot, KnowledgeSnapshot) and len(snapshot.chunks) == 60
    monkeypatch.setattr("eidos.knowledge.identity.EVIDENCE_REF_HEX_LENGTH", 1)  # sixty chunks cannot have sixteen distinct one-digit references
    with pytest.raises(ValidationError, match="evidence reference"):
        rebuild(snapshot)


def test_the_snapshot_id_must_be_the_id_of_its_documents_derivations_and_scheme():
    snapshot = valid_snapshot()
    with pytest.raises(ValidationError, match="snapshot id"):
        rebuild(snapshot, snapshot_id=HEX_A)
    with pytest.raises(ValidationError, match="chunk id"):  # the scheme is part of every chunk's id, so a different one fails there first
        rebuild(snapshot, chunking_scheme_id="paragraph-pack-v1/max_words=4")


def test_derivations_must_be_canonical_between_known_documents_and_acyclic():
    snapshot = valid_snapshot()
    ops, audit = snapshot.documents[1], snapshot.documents[0]
    assert (ops.source_id, audit.source_id) == ("ops", "audit")
    good = Derivation(document=ops, origin=audit)
    edge_id = snapshot_id_of(
        chunking_scheme_id=snapshot.chunking_scheme_id,
        documents=[(r.source_id, r.document_id) for r in snapshot.documents],
        derivations=[(ops.source_id, ops.document_id, audit.source_id, audit.document_id)],
    )
    assert rebuild(snapshot, snapshot_id=edge_id, derivations=(good,)).derivation_map == {ops: frozenset({audit})}
    stranger = DocumentRef(source_id="stranger", document_id="e" * 64)
    with pytest.raises(ValidationError, match="not in the corpus"):
        rebuild(snapshot, derivations=(Derivation(document=ops, origin=stranger),))
    with pytest.raises(ValidationError, match="canonical order"):
        rebuild(snapshot, derivations=(good, good))
    with pytest.raises(ValidationError, match="cycle"):
        rebuild(snapshot, derivations=tuple(sorted(
            (Derivation(document=ops, origin=audit), Derivation(document=audit, origin=ops)),
            key=lambda d: (d.document.source_id, d.document.document_id, d.origin.source_id, d.origin.document_id),
        )))


def test_the_derivation_map_is_read_only_and_the_documents_are_the_chunked_ones():
    snapshot = build_snapshot(
        (doc("audit", "alpha beta"), doc("blog", "gamma delta", ref_of("audit", "alpha beta"))), ChunkingScheme(max_words=5)
    )
    assert isinstance(snapshot, KnowledgeSnapshot)
    mapping = snapshot.derivation_map
    assert mapping == {ref_of("blog", "gamma delta"): frozenset({ref_of("audit", "alpha beta")})}
    with pytest.raises(TypeError):
        mapping[ref_of("audit", "alpha beta")] = frozenset()
    assert snapshot.documents == tuple(sorted(
        (ref_of("audit", "alpha beta"), ref_of("blog", "gamma delta")), key=lambda r: (r.source_id, r.document_id)
    ))


def test_a_snapshot_survives_a_json_round_trip_unchanged():
    snapshot = valid_snapshot()
    assert KnowledgeSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot


def test_no_refusal_is_an_exception_and_every_code_has_a_distinct_value():
    assert len({c.value for c in IngestionRefusalCode}) == len(list(IngestionRefusalCode)) == 9
    refusal = IngestionRefusal(code=IngestionRefusalCode.EMPTY_CORPUS, message="x")
    assert refusal.code is IngestionRefusalCode.EMPTY_CORPUS
    with pytest.raises(ValidationError):
        IngestionRefusal(code=IngestionRefusalCode.EMPTY_CORPUS, message="")


# --- documents of one source are ordered by their document id --------------------------------------------------------------------


def test_the_document_named_in_a_cycle_message_is_the_first_in_canonical_order_even_within_one_source():
    for size in range(3, 9):
        refs = [DocumentRef(source_id="same", document_id=f"{n:x}" * 64) for n in range(1, size + 1)]
        edges = [(refs[n], refs[(n + 1) % size]) for n in range(size)]
        found = derivation_problem(list(reversed(refs)), list(reversed(edges)))
        assert found[0] is IngestionRefusalCode.DERIVATION_CYCLE
        assert "same/" + "1" * 12 in found[1], (size, found[1])


def test_a_snapshots_documents_are_listed_by_source_and_then_by_document_id():
    texts = [f"document number {n} has its own words" for n in range(8)]
    snapshot = build_snapshot(tuple(doc("one", text) for text in texts), ChunkingScheme(max_words=12))
    assert isinstance(snapshot, KnowledgeSnapshot)
    ids = [ref.document_id for ref in snapshot.documents]
    assert len(ids) == 8 and ids == sorted(ids)
    assert [ref.source_id for ref in snapshot.documents] == ["one"] * 8


def test_derivations_of_one_document_from_several_origins_of_one_source_are_listed_by_origin_id():
    origins = [f"origin document {n} with its own words" for n in range(6)]
    documents = (*(doc("orig", text) for text in origins), doc("derived", "a derived document", *(ref_of("orig", text) for text in origins)))
    snapshot = build_snapshot(documents, ChunkingScheme(max_words=12))
    assert isinstance(snapshot, KnowledgeSnapshot)
    assert len(snapshot.derivations) == 6
    origin_ids = [d.origin.document_id for d in snapshot.derivations]
    assert origin_ids == sorted(origin_ids)
