"""The knowledge/evidence layer (decisions.md D-208 to D-222): the pure structures.

    snapshot = build_snapshot(documents, ChunkingScheme(max_words=...))      # a KnowledgeSnapshot, or the first IngestionRefusal
    independent_source_count(cited_document_refs, snapshot.derivation_map)   # how many independent sources were cited

Contracts, identity, normalisation, chunking, the snapshot and the independence count. Pure: no I/O, no clock, no randomness, no model call and no hidden
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
from .identity import chunk_id_of, document_id_of, evidence_ref_of, is_source_id, normalise_text, snapshot_id_of
from .independence import independent_source_count, independent_sources
from .snapshot import build_snapshot

__all__ = [
    "ChunkingScheme",
    "Derivation",
    "DocumentRef",
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
    "evidence_ref_of",
    "independent_source_count",
    "independent_sources",
    "is_source_id",
    "normalise_text",
    "snapshot_id_of",
]
