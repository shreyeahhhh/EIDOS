"""Building a snapshot from declared documents (decisions.md D-211, D-212, D-220, D-221).

The result is a snapshot or the first refusal in a fixed order: a corpus with no document; then, document by document in the order given, an invalid source id,
text that cannot be encoded, a document with no words, a duplicate; then the derivation declarations; then an evidence reference two chunks share. A snapshot
does not depend on the order the documents were given in.
"""

from collections.abc import Iterable

from .chunking import ChunkingScheme, chunk_document
from .contracts import (
    Derivation,
    DocumentRef,
    IngestionRefusal,
    IngestionRefusalCode,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSnapshot,
    chunk_sort_key,
    derivation_problem,
    derivation_sort_key,
)
from .identity import document_id_of, is_source_id, snapshot_id_of


def _refuse(code: IngestionRefusalCode, message: str) -> IngestionRefusal:
    return IngestionRefusal(code=code, message=message)


def build_snapshot(documents: Iterable[KnowledgeDocument], scheme: ChunkingScheme) -> KnowledgeSnapshot | IngestionRefusal:
    entries = tuple(documents)
    if not entries:
        return _refuse(IngestionRefusalCode.EMPTY_CORPUS, "a snapshot needs at least one document")
    refs: dict[DocumentRef, tuple[DocumentRef, ...]] = {}
    chunks: list[KnowledgeChunk] = []
    for position, entry in enumerate(entries):
        if not is_source_id(entry.source_id):
            return _refuse(
                IngestionRefusalCode.INVALID_SOURCE_ID,
                f"document {position} does not name a valid declared source_id ({entry.source_id!r}); no default is invented",
            )
        try:
            ref = DocumentRef(source_id=entry.source_id, document_id=document_id_of(entry.text))
        except UnicodeEncodeError:
            return _refuse(IngestionRefusalCode.INVALID_TEXT, f"document {position} of source {entry.source_id!r} is not text that can be encoded as UTF-8")
        found = chunk_document(source_id=entry.source_id, text=entry.text, scheme=scheme)
        if not found:
            return _refuse(IngestionRefusalCode.EMPTY_DOCUMENT, f"document {position} of source {entry.source_id!r} has no words")
        if ref in refs:
            return _refuse(
                IngestionRefusalCode.DUPLICATE_DOCUMENT,
                f"document {position} repeats a document already declared under source {entry.source_id!r}",
            )
        refs[ref] = entry.derived_from
        chunks.extend(found)
    problem = derivation_problem(list(refs), [(document, origin) for document, origins in refs.items() for origin in origins])
    if problem is not None:
        return _refuse(problem[0], problem[1])
    evidence_refs: set[str] = set()
    for chunk in chunks:
        if chunk.evidence_ref in evidence_refs:
            return _refuse(IngestionRefusalCode.EVIDENCE_REF_COLLISION, f"two chunks share the evidence reference {chunk.evidence_ref!r}")
        evidence_refs.add(chunk.evidence_ref)
    ordered_chunks = tuple(sorted(chunks, key=chunk_sort_key))
    derivations = tuple(
        sorted(
            {Derivation(document=document, origin=origin) for document, origins in refs.items() for origin in origins},
            key=derivation_sort_key,
        )
    )
    return KnowledgeSnapshot(
        snapshot_id=snapshot_id_of(
            chunking_scheme_id=scheme.scheme_id,
            documents=[(ref.source_id, ref.document_id) for ref in refs],
            derivations=[(d.document.source_id, d.document.document_id, d.origin.source_id, d.origin.document_id) for d in derivations],
        ),
        chunking_scheme_id=scheme.scheme_id,
        chunks=ordered_chunks,
        derivations=derivations,
    )
