"""Small corpora and helpers for the knowledge-layer tests (V1.3 Steps 2 and 3). Not the benchmark fixture (D-213), which is authored at Step 5."""

import hashlib

from eidos.knowledge import ChunkingScheme, DocumentRef, EvidenceRecord, KnowledgeChunk, KnowledgeDocument, KnowledgeSnapshot, document_id_of, evidence_from_snapshot

SCHEME = ChunkingScheme(max_words=12)

OPS_MANUAL = (
    "Before the station is restarted after a storm shutdown, the duty engineer completes the written inspection checklist.\n\n"
    "The tidal barrier sensors must report normal readings, and the result is recorded in the operations log."
)
SAFETY_AUDIT = "The audit found that no turbine may be released to the network until the shift supervisor has signed off both steps."
GRID_AGREEMENT = "The grid operator must be notified thirty minutes before reconnection."
BLOG_POST = "A blog writes that engineers inspect the plant and note the sensor readings before letting turbines run again."


def ref_of(source_id: str, text: str) -> DocumentRef:
    return DocumentRef(source_id=source_id, document_id=document_id_of(text))


def doc(source_id: str, text: str, *derived_from: DocumentRef) -> KnowledgeDocument:
    return KnowledgeDocument(source_id=source_id, text=text, derived_from=tuple(derived_from))


def small_corpus() -> tuple[KnowledgeDocument, ...]:
    """Four sources, a byte-identical mirror under a fifth, and one declared derivation."""
    return (
        doc("ops", OPS_MANUAL),
        doc("audit", SAFETY_AUDIT),
        doc("grid", GRID_AGREEMENT),
        doc("blog", BLOG_POST, ref_of("audit", SAFETY_AUDIT)),
        doc("mirror", OPS_MANUAL),
    )


def query_id(name: str) -> str:
    """A well-formed query id for a test: any SHA-256 digest will do. What a query id is derived from belongs to the retrieval contracts of a later step."""
    return hashlib.sha256(name.encode("utf-8")).hexdigest()


def chunk_of(snapshot: KnowledgeSnapshot, source_id: str, index: int = 0) -> KnowledgeChunk:
    """The ``index``-th chunk (in canonical order) of a source in ``snapshot``."""
    return [chunk for chunk in snapshot.chunks if chunk.source_id == source_id][index]


def evidence_of(snapshot: KnowledgeSnapshot, chunk: KnowledgeChunk, query: str = "q1") -> EvidenceRecord:
    """The evidence for ``chunk`` retrieved by the query named ``query``."""
    record = evidence_from_snapshot(snapshot, chunk.chunk_id, query_id=query_id(query))
    assert isinstance(record, EvidenceRecord), record
    return record
