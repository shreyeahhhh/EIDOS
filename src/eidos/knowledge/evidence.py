"""Evidence records and set-based independence resolution (decisions.md D-209, D-210, D-212, D-221; V1.3 Step 3): pure and deterministic.

An ``EvidenceRecord`` is a knowledge chunk that was retrieved for a query, kept with the ids that trace it back: the chunk, its document and its source (Step 2
identity), the chunking scheme and snapshot it came from, and the ids of the queries that retrieved it. It checks itself on construction: the chunk id must be exactly
what the identity function gives, so a record cannot claim an identity its parts do not have.

Existing V1.2 documents (a caller-supplied artifact, a tool document) are mapped into the same identity without touching what was recorded (D-210): the source id is
derived from the artifact's reference identity, the document id from its normalised content, and the whole document is one chunk under ``LEGACY_SCHEME_ID``.

Independence is resolved over a *set* of cited evidence, never key by key: whether one document counts depends on which other documents are cited (D-223, reading 12).
Nothing here reads a clock, a random source, the hash seed or the order things arrive in.
"""

import hashlib
import json
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from eidos.contracts import EidosModel

from .contracts import DocumentRef, KnowledgeChunk, KnowledgeSnapshot, ref_sort_key
from .identity import SCHEME_ID_PATTERN, SHA256_HEX, chunk_id_of, document_id_of, normalise_text
from .independence import independent_sources

LEGACY_SCHEME_ID = "legacy-artifact-v1"
LEGACY_SOURCE_PREFIX = "legacy-"
LEGACY_SOURCE_VERSION = "legacy-source-v1"
LEGACY_SOURCE_HEX_LENGTH = 32

QueryId = Annotated[str, Field(pattern=SHA256_HEX)]


class EvidenceRefusalCode(StrEnum):
    UNKNOWN_CHUNK = "unknown_chunk"  # a chunk id the snapshot does not hold
    EMPTY_DOCUMENT = "empty_document"  # a V1.2 document with no content
    NOT_SUPPLIED = "not_supplied"  # a reference that is not a supplied artifact of the execution
    EVIDENCE_REF_COLLISION = "evidence_ref_collision"  # a different chunk already holds this evidence reference
    SNAPSHOT_CONFLICT = "snapshot_conflict"  # the same chunk, already held from a different snapshot


class EvidenceRefusal(EidosModel):
    """Evidence that could not be recorded or resolved. Returned, never raised: nothing is defaulted and nothing is dropped."""

    code: EvidenceRefusalCode
    message: str = Field(min_length=1)


def _refuse(code: EvidenceRefusalCode, message: str) -> EvidenceRefusal:
    return EvidenceRefusal(code=code, message=message)


class EvidenceRecord(EidosModel):
    """A chunk that was retrieved, with the ids that trace it. ``retrieved_by`` holds the ids of the queries that retrieved it: sorted, each once.

    ``snapshot_id`` names the snapshot a knowledge chunk came from; a V1.2 document (``LEGACY_SCHEME_ID``) has none.
    """

    chunk: KnowledgeChunk
    chunking_scheme_id: str = Field(pattern=SCHEME_ID_PATTERN)
    snapshot_id: str | None = Field(default=None, pattern=SHA256_HEX)
    retrieved_by: tuple[QueryId, ...] = ()

    @model_validator(mode="after")
    def _check_the_record_is_what_it_says(self) -> "EvidenceRecord":
        chunk = self.chunk
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
        if list(self.retrieved_by) != sorted(set(self.retrieved_by)):
            raise ValueError("retrieved_by lists each query id once, in order")
        if (self.snapshot_id is None) != (self.chunking_scheme_id == LEGACY_SCHEME_ID):
            raise ValueError("a knowledge chunk names its snapshot and a V1.2 document has none")
        if self.chunking_scheme_id == LEGACY_SCHEME_ID:
            if not chunk.source_id.startswith(LEGACY_SOURCE_PREFIX):
                raise ValueError("a V1.2 document's source id is derived from its reference")
            if chunk.start != 0 or chunk.text != normalise_text(chunk.text) or chunk.document_id != document_id_of(chunk.text):
                raise ValueError("a V1.2 document is one whole normalised chunk, and its document id is the digest of that text")
        return self

    @property
    def evidence_ref(self) -> str:
        return self.chunk.evidence_ref

    @property
    def document_ref(self) -> DocumentRef:
        return self.chunk.document_ref


class IndependenceResolution(EidosModel):
    """The independent sources behind a set of cited evidence references.

    ``evidence`` is the cited references the ledger holds and ``unresolved`` those it does not (they are reported, never counted); ``documents`` are the distinct
    documents that evidence comes from, and ``sources`` the independent declared sources of D-209 and D-221, sorted.
    """

    evidence: tuple[str, ...]
    unresolved: tuple[str, ...]
    documents: tuple[DocumentRef, ...]
    sources: tuple[str, ...]

    @property
    def source_count(self) -> int:
        return len(self.sources)


def evidence_from_snapshot(snapshot: KnowledgeSnapshot, chunk_id: str, *, query_id: str) -> EvidenceRecord | EvidenceRefusal:
    """The evidence for chunk ``chunk_id`` of ``snapshot`` retrieved by query ``query_id``, or a refusal if the snapshot holds no such chunk."""
    for chunk in snapshot.chunks:
        if chunk.chunk_id == chunk_id:
            return EvidenceRecord(chunk=chunk, chunking_scheme_id=snapshot.chunking_scheme_id, snapshot_id=snapshot.snapshot_id, retrieved_by=(query_id,))
    return _refuse(EvidenceRefusalCode.UNKNOWN_CHUNK, f"snapshot {snapshot.snapshot_id[:12]} holds no chunk {chunk_id[:12]}")


def merge_evidence(held: EvidenceRecord, incoming: EvidenceRecord) -> EvidenceRecord | EvidenceRefusal:
    """The record for one evidence reference after ``incoming`` is recorded on top of ``held``: the same chunk again keeps one record whose ``retrieved_by`` is
    the union. A different chunk under the same reference, or the same chunk from a different snapshot, is refused and nothing is merged."""
    if held.evidence_ref != incoming.evidence_ref:
        raise ValueError("only records of one evidence reference are merged")
    if held.chunk.chunk_id != incoming.chunk.chunk_id:
        return _refuse(EvidenceRefusalCode.EVIDENCE_REF_COLLISION, f"evidence reference {held.evidence_ref} is already held by a different chunk")
    if held.snapshot_id != incoming.snapshot_id:
        return _refuse(EvidenceRefusalCode.SNAPSHOT_CONFLICT, f"chunk {held.chunk.chunk_id[:12]} is already held from a different snapshot")
    return EvidenceRecord(
        chunk=held.chunk,
        chunking_scheme_id=held.chunking_scheme_id,
        snapshot_id=held.snapshot_id,
        retrieved_by=tuple(sorted(set(held.retrieved_by) | set(incoming.retrieved_by))),
    )


def resolve_independence(
    cited: Iterable[str], records: Iterable[EvidenceRecord], derived_from: Mapping[DocumentRef, Iterable[DocumentRef]]
) -> IndependenceResolution:
    """The independent sources behind the cited evidence references, over the set as a whole: the order and repetition of ``cited`` and of ``records`` change
    nothing. The counting rule is ``independent_sources`` (D-209, D-221): ``derived_from`` is the declared derivation map, explicit and direct only."""
    held: dict[str, EvidenceRecord] = {}
    for record in records:
        earlier = held.setdefault(record.evidence_ref, record)
        if earlier.chunk.chunk_id != record.chunk.chunk_id:
            raise ValueError("two different chunks share an evidence reference")
    references = sorted(set(cited))
    found = [held[reference] for reference in references if reference in held]
    documents = tuple(sorted({record.document_ref for record in found}, key=ref_sort_key))
    return IndependenceResolution(
        evidence=tuple(record.evidence_ref for record in found),
        unresolved=tuple(reference for reference in references if reference not in held),
        documents=documents,
        sources=independent_sources(documents, derived_from),
    )


def _legacy_source_id(identity: dict[str, str]) -> str:
    canonical = json.dumps({"version": LEGACY_SOURCE_VERSION, **identity}, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return LEGACY_SOURCE_PREFIX + hashlib.sha256(canonical.encode("ascii")).hexdigest()[:LEGACY_SOURCE_HEX_LENGTH]


def _legacy_record(source_id: str, text: str) -> EvidenceRecord | EvidenceRefusal:
    normalised = normalise_text(text)
    if not normalised:
        return _refuse(EvidenceRefusalCode.EMPTY_DOCUMENT, "a document with no content is not evidence")
    document_id = document_id_of(text)
    chunk = KnowledgeChunk(
        chunk_id=chunk_id_of(
            source_id=source_id, document_id=document_id, chunking_scheme_id=LEGACY_SCHEME_ID, start=0, end=len(normalised), text=normalised
        ),
        document_id=document_id,
        source_id=source_id,
        start=0,
        end=len(normalised),
        text=normalised,
    )
    return EvidenceRecord(chunk=chunk, chunking_scheme_id=LEGACY_SCHEME_ID)


def legacy_supplied_record(ref: str, text: str) -> EvidenceRecord | EvidenceRefusal:
    """The knowledge identity of a caller-supplied V1.2 artifact: its source is derived from its reference, its document from its normalised content."""
    return _legacy_record(_legacy_source_id({"kind": "supplied", "ref": ref}), text)


def legacy_tool_record(tool_id: str, document_id: str, text: str) -> EvidenceRecord | EvidenceRefusal:
    """The knowledge identity of a V1.2 tool document: its source is derived from the tool and the provider's own document id, so the same document reached
    by two queries is one source. The request digest in its reference is retrieval provenance, not identity (decisions.md D-224, an open reading)."""
    return _legacy_record(_legacy_source_id({"kind": "tool", "tool_id": tool_id, "document_id": document_id}), text)
