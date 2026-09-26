"""Retrieval contracts: the request, the result, the failure and the port (decisions.md D-208, D-212, D-216, D-217, D-218, D-225; V1.3 Step 4).

Pure and deterministic: nothing here reads a clock, a random source, the hash seed or the file system, and nothing here names a retrieval engine, a vector store or a
model. A ``KnowledgePort`` answers a ``RetrievalRequest`` with a ``RetrievalResult`` or a ``RetrievalFailure``; it never raises for a retrieval outcome and it never writes.

The request pins the knowledge base, the snapshot and the retrieval scheme it means and states both bounds (no defaults), so a query has one identity: ``query_id`` is a digest
of exactly those inputs and the canonical query text, and of nothing else. A result is ranked from 1 in a fixed order (score descending, then ``chunk_id`` ascending, when the
scheme provides a score), and it checks itself on construction. A hit is not evidence and not an independent source: it becomes evidence when it is cited (``EvidenceRecord``).
"""

import hashlib
import json
from enum import StrEnum
from typing import Protocol

from pydantic import Field, model_validator

from eidos.contracts import EidosModel

from .contracts import KnowledgeChunk
from .identity import SCHEME_ID_PATTERN, SHA256_HEX, SOURCE_ID_PATTERN, normalise_text

QUERY_ID_VERSION = "query-v1"
KB_ID_PATTERN = SOURCE_ID_PATTERN

# The fixed whitespace a query is stripped of: the same set the chunker reads words by, so no result depends on the interpreter's Unicode tables.
QUERY_STRIP_CHARACTERS = "".join(
    chr(code_point) for code_point in (0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x20, 0x85, 0xA0, 0x1680, *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F, 0x205F, 0x3000)
)


def canonical_query_text(text: str) -> str:
    """The one form a query is kept in: Unicode NFC, CRLF and CR read as LF, and the ends stripped of the fixed whitespace. The words inside are untouched."""
    return normalise_text(text).strip(QUERY_STRIP_CHARACTERS)


def query_id_of(*, kb_id: str, snapshot_id: str, scheme_id: str, text: str, top_k: int) -> str:
    """The SHA-256 of the canonical JSON of the query's identity. The byte bound is not part of it: it is knowledge-base configuration, not what was asked."""
    canonical = json.dumps(
        {"version": QUERY_ID_VERSION, "kb_id": kb_id, "snapshot_id": snapshot_id, "scheme_id": scheme_id, "text": text, "top_k": top_k},
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


class RetrievalRequest(EidosModel):
    """What is asked of a port. Every field is stated by the caller: there is no default bound, and ``text`` must already be in its canonical form."""

    kb_id: str = Field(pattern=KB_ID_PATTERN)
    snapshot_id: str = Field(pattern=SHA256_HEX)
    scheme_id: str = Field(pattern=SCHEME_ID_PATTERN)
    text: str = Field(min_length=1)
    top_k: int = Field(ge=1)
    max_result_bytes: int = Field(ge=1)

    @model_validator(mode="after")
    def _check_the_query_is_in_its_canonical_form(self) -> "RetrievalRequest":
        if self.text != canonical_query_text(self.text):
            raise ValueError("a query is given in its canonical form (canonical_query_text), so that one query has one identity")
        return self

    @property
    def query_id(self) -> str:
        return query_id_of(kb_id=self.kb_id, snapshot_id=self.snapshot_id, scheme_id=self.scheme_id, text=self.text, top_k=self.top_k)


class RetrievalFailureKind(StrEnum):
    """Why a port could not answer. The recorded outcome mirrors these values and a guard keeps the two in step."""

    UNAVAILABLE = "unavailable"  # the port cannot serve at all
    REQUEST_MISMATCH = "request_mismatch"  # the request names a knowledge base, snapshot or scheme the port does not serve
    RESULT_TOO_LARGE = "result_too_large"  # the hits' text exceeds the request's byte bound; it is never truncated
    MALFORMED_RESULT = "malformed_result"  # an answer that does not answer its request


class RetrievalFailure(EidosModel):
    """A retrieval that did not answer. Returned, never raised."""

    kind: RetrievalFailureKind
    message: str = Field(min_length=1)


class RetrievedChunk(EidosModel):
    """One hit: its integer rank from 1, the chunk, and a score only where the retrieval scheme provides one."""

    rank: int = Field(ge=1)
    chunk: KnowledgeChunk
    score: float | None = Field(default=None, allow_inf_nan=False)

    @property
    def evidence_ref(self) -> str:
        return self.chunk.evidence_ref

    @property
    def content_digest(self) -> str:
        return hashlib.sha256(self.chunk.text.encode("utf-8")).hexdigest()


class RetrievalResult(EidosModel):
    """An answer. ``score_kind`` says what a score is (a label, never a confidence) and is present exactly when the hits carry scores.

    Hits are ranked 1 to n in order, each chunk at most once, and, when scored, ordered by score descending and then ``chunk_id`` ascending. An empty result is a real
    result: the port ran and nothing matched.
    """

    query_id: str = Field(pattern=SHA256_HEX)
    kb_id: str = Field(pattern=KB_ID_PATTERN)
    snapshot_id: str = Field(pattern=SHA256_HEX)
    scheme_id: str = Field(pattern=SCHEME_ID_PATTERN)
    score_kind: str | None = Field(default=None, pattern=SCHEME_ID_PATTERN)
    hits: tuple[RetrievedChunk, ...] = ()

    @model_validator(mode="after")
    def _check_the_hits_are_what_a_ranked_result_is(self) -> "RetrievalResult":
        if [hit.rank for hit in self.hits] != list(range(1, len(self.hits) + 1)):
            raise ValueError("hits are ranked 1 to n, in order")
        if len({hit.chunk.chunk_id for hit in self.hits}) != len(self.hits):
            raise ValueError("a chunk is a hit at most once")
        if self.score_kind is None and any(hit.score is not None for hit in self.hits):
            raise ValueError("a score is labelled: a result with scored hits names what a score is")
        if self.score_kind is not None and any(hit.score is None for hit in self.hits):
            raise ValueError("a result that names what a score is scores every hit")
        if self.score_kind is not None:
            keys = [(-hit.score, hit.chunk.chunk_id) for hit in self.hits]
            if keys != sorted(keys) or len(set(keys)) != len(keys):
                raise ValueError("scored hits are ordered by score descending and then chunk_id ascending")
        return self

    @property
    def result_bytes(self) -> int:
        """The UTF-8 size of the hits' text: what a request's byte bound limits."""
        return sum(len(hit.chunk.text.encode("utf-8")) for hit in self.hits)


def result_problem(request: RetrievalRequest, result: RetrievalResult) -> str | None:
    """What is wrong with ``result`` as an answer to ``request``, or ``None``: the checks any caller can make without knowing how the port works."""
    if result.query_id != request.query_id:
        return "the result answers a different query"
    for name in ("kb_id", "snapshot_id", "scheme_id"):
        if getattr(result, name) != getattr(request, name):
            return f"the result names a different {name} than the request"
    if len(result.hits) > request.top_k:
        return "the result has more hits than the request's top_k"
    if result.result_bytes > request.max_result_bytes:
        return "the result is larger than the request's byte bound"
    return None


class KnowledgePort(Protocol):
    """A retriever over one pinned snapshot. Synchronous, thread-safe, total (a failure is returned, never raised) and read-only."""

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult | RetrievalFailure: ...
