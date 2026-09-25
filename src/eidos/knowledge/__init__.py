"""The knowledge/evidence layer (decisions.md D-208 to D-222): the pure structures.

    snapshot = build_snapshot(documents, ChunkingScheme(max_words=...))      # a KnowledgeSnapshot, or the first IngestionRefusal
    independent_source_count(cited_document_refs, snapshot.derivation_map)   # how many independent sources were cited
    evidence_from_snapshot(snapshot, chunk_id, query_id=...)                 # an EvidenceRecord, or an EvidenceRefusal
    resolve_independence(cited_refs, records, snapshot.derivation_map)       # the independent sources behind a set of cited evidence

Contracts, identity, normalisation, chunking, the snapshot, the independence count, and (Step 3) evidence records with their set-based resolution and the mapping of
existing V1.2 documents into the same identity. Pure: no I/O, no clock, no randomness, no model call and no hidden
state, and nothing here names a retrieval engine, a vector store or an embedding model. Retrieval ports arrive in later steps (D-222).
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
from .snapshot import build_snapshot

__all__ = [
    "LEGACY_SCHEME_ID",
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
    "KnowledgeSnapshot",
    "build_snapshot",
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
    "resolve_independence",
    "snapshot_id_of",
]
