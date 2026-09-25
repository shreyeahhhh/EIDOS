"""Typed contracts for the knowledge layer (decisions.md D-209, D-211, D-212, D-219, D-221).

A document is identified by its source and its content, a chunk by both plus where it sits, and a snapshot by the whole declared corpus. A snapshot checks
itself on construction: every chunk id, the snapshot id and the derivation declarations must be exactly what the identity functions give.
"""

from collections.abc import Collection, Mapping
from enum import StrEnum
from types import MappingProxyType

from pydantic import Field, model_validator

from eidos.contracts import EidosModel

from .identity import SCHEME_ID_PATTERN, SHA256_HEX, SOURCE_ID_PATTERN, chunk_id_of, evidence_ref_of, snapshot_id_of


class IngestionRefusalCode(StrEnum):
    EMPTY_CORPUS = "empty_corpus"
    INVALID_SOURCE_ID = "invalid_source_id"
    INVALID_TEXT = "invalid_text"
    EMPTY_DOCUMENT = "empty_document"
    DUPLICATE_DOCUMENT = "duplicate_document"
    UNKNOWN_DERIVATION_TARGET = "unknown_derivation_target"
    SELF_DERIVATION = "self_derivation"
    DERIVATION_CYCLE = "derivation_cycle"
    EVIDENCE_REF_COLLISION = "evidence_ref_collision"


class IngestionRefusal(EidosModel):
    """A corpus that could not become a snapshot. Returned, never raised: nothing is defaulted and nothing is dropped."""

    code: IngestionRefusalCode
    message: str = Field(min_length=1)


class DocumentRef(EidosModel):
    """A document as declared: the source it belongs to and the SHA-256 of its normalised text."""

    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    document_id: str = Field(pattern=SHA256_HEX)


class KnowledgeDocument(EidosModel):
    """One manifest entry as given. Deliberately lenient: an invalid entry is refused at ingestion, not rejected here (D-211).

    ``derived_from`` names the documents this one is explicitly declared to derive from (D-221): direct relationships only.
    """

    source_id: str
    text: str
    derived_from: tuple[DocumentRef, ...] = ()


class KnowledgeChunk(EidosModel):
    """A contiguous span of a normalised document. ``start`` and ``end`` are code-point offsets into the normalised text."""

    chunk_id: str = Field(pattern=SHA256_HEX)
    document_id: str = Field(pattern=SHA256_HEX)
    source_id: str = Field(pattern=SOURCE_ID_PATTERN)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_the_span_is_the_text(self) -> "KnowledgeChunk":
        if self.end <= self.start or len(self.text) != self.end - self.start:
            raise ValueError("a chunk's text is exactly the span from start to end")
        return self

    @property
    def document_ref(self) -> DocumentRef:
        return DocumentRef(source_id=self.source_id, document_id=self.document_id)

    @property
    def evidence_ref(self) -> str:
        return evidence_ref_of(self.chunk_id)


class Derivation(EidosModel):
    """``document`` is declared to derive directly from ``origin``."""

    document: DocumentRef
    origin: DocumentRef

    @model_validator(mode="after")
    def _check_a_document_does_not_derive_from_itself(self) -> "Derivation":
        if self.document == self.origin:
            raise ValueError("a document cannot be declared derived from itself")
        return self


def ref_sort_key(ref: DocumentRef) -> tuple[str, str]:
    return ref.source_id, ref.document_id


def chunk_sort_key(chunk: KnowledgeChunk) -> tuple[str, str, int]:
    return chunk.source_id, chunk.document_id, chunk.start


def derivation_sort_key(derivation: Derivation) -> tuple[str, str, str, str]:
    return derivation.document.source_id, derivation.document.document_id, derivation.origin.source_id, derivation.origin.document_id


def _label(ref: DocumentRef) -> str:
    return f"{ref.source_id}/{ref.document_id[:12]}"


def derivation_problem(
    documents: Collection[DocumentRef], edges: Collection[tuple[DocumentRef, DocumentRef]]
) -> tuple[IngestionRefusalCode, str] | None:
    """The first thing wrong with a set of declared derivations, in a fixed order, or ``None``: a self-derivation, an endpoint that is not a document,
    then a cycle. A cycle would make a cited document's origin also derive from it, so no document of it could be counted."""
    known = set(documents)
    ordered = sorted(set(edges), key=lambda edge: (ref_sort_key(edge[0]), ref_sort_key(edge[1])))
    for document, origin in ordered:
        if document == origin:
            return IngestionRefusalCode.SELF_DERIVATION, f"document {_label(document)} is declared derived from itself"
        for endpoint in (document, origin):
            if endpoint not in known:
                return (
                    IngestionRefusalCode.UNKNOWN_DERIVATION_TARGET,
                    f"document {_label(document)} declares derived_from {_label(origin)}, and {_label(endpoint)} is not in the corpus",
                )
    unresolved = {document: 0 for document in known}
    dependents: dict[DocumentRef, list[DocumentRef]] = {document: [] for document in known}
    for document, origin in ordered:
        unresolved[document] += 1
        dependents[origin].append(document)
    ready = sorted((document for document, count in unresolved.items() if count == 0), key=ref_sort_key)
    resolved = 0
    while ready:
        current = ready.pop()
        resolved += 1
        for dependent in dependents[current]:
            unresolved[dependent] -= 1
            if unresolved[dependent] == 0:
                ready.append(dependent)
    if resolved < len(known):
        stuck = min((document for document, count in unresolved.items() if count > 0), key=ref_sort_key)
        return IngestionRefusalCode.DERIVATION_CYCLE, f"the derived_from declarations contain a cycle, and document {_label(stuck)} cannot be resolved"
    return None


class KnowledgeSnapshot(EidosModel):
    """The pinned corpus: authoritative knowledge state (D-220). Chunks in canonical order, and the declared derivations between its documents."""

    snapshot_id: str = Field(pattern=SHA256_HEX)
    chunking_scheme_id: str = Field(pattern=SCHEME_ID_PATTERN)
    chunks: tuple[KnowledgeChunk, ...] = Field(min_length=1)
    derivations: tuple[Derivation, ...] = ()

    @model_validator(mode="after")
    def _check_the_snapshot_is_what_it_says(self) -> "KnowledgeSnapshot":
        previous: KnowledgeChunk | None = None
        evidence_refs: set[str] = set()
        for chunk in self.chunks:
            if previous is not None:
                if chunk_sort_key(chunk) <= chunk_sort_key(previous):
                    raise ValueError("chunks are listed once each, in canonical order (source, document, start)")
                if chunk.document_ref == previous.document_ref and chunk.start < previous.end:
                    raise ValueError("chunks of one document do not overlap")
            expected = chunk_id_of(
                source_id=chunk.source_id,
                document_id=chunk.document_id,
                chunking_scheme_id=self.chunking_scheme_id,
                start=chunk.start,
                end=chunk.end,
                text=chunk.text,
            )
            if chunk.chunk_id != expected:
                raise ValueError("a chunk id is not the id of its source, document, scheme, span and text")
            if chunk.evidence_ref in evidence_refs:
                raise ValueError("two chunks share an evidence reference")
            evidence_refs.add(chunk.evidence_ref)
            previous = chunk
        keys = [derivation_sort_key(derivation) for derivation in self.derivations]
        if keys != sorted(set(keys)):
            raise ValueError("derivations are listed once each, in canonical order")
        problem = derivation_problem(self.documents, [(d.document, d.origin) for d in self.derivations])
        if problem is not None:
            raise ValueError(problem[1])
        if self.snapshot_id != snapshot_id_of(
            chunking_scheme_id=self.chunking_scheme_id,
            documents=[(ref.source_id, ref.document_id) for ref in self.documents],
            derivations=[(d.document.source_id, d.document.document_id, d.origin.source_id, d.origin.document_id) for d in self.derivations],
        ):
            raise ValueError("the snapshot id is not the id of its documents, derivations and scheme")
        return self

    @property
    def documents(self) -> tuple[DocumentRef, ...]:
        return tuple(sorted({chunk.document_ref for chunk in self.chunks}, key=ref_sort_key))

    @property
    def derivation_map(self) -> Mapping[DocumentRef, frozenset[DocumentRef]]:
        origins: dict[DocumentRef, set[DocumentRef]] = {}
        for derivation in self.derivations:
            origins.setdefault(derivation.document, set()).add(derivation.origin)
        return MappingProxyType({document: frozenset(found) for document, found in origins.items()})
