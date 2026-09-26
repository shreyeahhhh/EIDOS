"""The knowledge/evidence layer (decisions.md D-208 to D-222): the pure structures.

    snapshot = build_snapshot(documents, ChunkingScheme(max_words=...))      # a KnowledgeSnapshot, or the first IngestionRefusal
    independent_source_count(cited_document_refs, snapshot.derivation_map)   # how many independent sources were cited
    evidence_from_snapshot(snapshot, chunk_id, query_id=...)                 # an EvidenceRecord, or an EvidenceRefusal
    resolve_independence(cited_refs, records, snapshot.derivation_map)       # the independent sources behind a set of cited evidence
    LexicalKnowledgePort(snapshot, kb_id=...).retrieve(RetrievalRequest(...)) # a RetrievalResult, or a RetrievalFailure

Contracts, identity, normalisation, chunking, the snapshot, the independence count, and (Step 3) evidence records with their set-based resolution and the mapping of
existing V1.2 documents into the same identity; and (Step 4) the retrieval contracts with their deterministic ``query_id``, the ``KnowledgePort`` protocol and the one retriever,
the exact in-process lexical one, in the standard library alone. Pure: no I/O, no clock, no randomness, no model call and no hidden state, and nothing here names a vector store, an embedding
model or a third-party engine. Other retrievers arrive in later steps (D-222).
"""

from .chunking import ChunkingScheme, chunk_document, chunk_spans
from .contracts import (
    Derivation,
    DocumentRef,
    IngestionRefusal,
    IngestionRefusalCode,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSnapshot,
)
from .evidence import (
    LEGACY_SCHEME_ID,
    EvidenceRecord,
    EvidenceRefusal,
    EvidenceRefusalCode,
    IndependenceResolution,
    evidence_from_snapshot,
    legacy_supplied_record,
    legacy_tool_record,
    merge_evidence,
    resolve_independence,
)
from .identity import chunk_id_of, document_id_of, evidence_ref_of, is_source_id, normalise_text, snapshot_id_of
from .independence import independent_source_count, independent_sources
from .lexical import LEXICAL_SCHEME_ID, LEXICAL_SCORE_KIND, LexicalKnowledgePort
from .retrieval import (
    KB_ID_PATTERN,
    KnowledgePort,
    RetrievalFailure,
    RetrievalFailureKind,
    RetrievalRequest,
    RetrievalResult,
    RetrievedChunk,
    canonical_query_text,
    query_id_of,
    result_problem,
)
from .snapshot import build_snapshot

__all__ = [
    "KB_ID_PATTERN",
    "LEGACY_SCHEME_ID",
    "LEXICAL_SCHEME_ID",
    "LEXICAL_SCORE_KIND",
    "ChunkingScheme",
    "Derivation",
    "DocumentRef",
    "EvidenceRecord",
    "EvidenceRefusal",
    "EvidenceRefusalCode",
    "IndependenceResolution",
    "IngestionRefusal",
    "IngestionRefusalCode",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgePort",
    "KnowledgeSnapshot",
    "LexicalKnowledgePort",
    "RetrievalFailure",
    "RetrievalFailureKind",
    "RetrievalRequest",
    "RetrievalResult",
    "RetrievedChunk",
    "build_snapshot",
    "canonical_query_text",
    "chunk_document",
    "chunk_id_of",
    "chunk_spans",
    "document_id_of",
    "evidence_from_snapshot",
    "evidence_ref_of",
    "independent_source_count",
    "independent_sources",
    "is_source_id",
    "legacy_supplied_record",
    "legacy_tool_record",
    "merge_evidence",
    "normalise_text",
    "query_id_of",
    "result_problem",
    "resolve_independence",
    "snapshot_id_of",
]
