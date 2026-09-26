"""Semantic retrieval behind ``KnowledgePort``: the pure half (decisions.md D-208, D-214, D-215, D-219, D-220, D-222, D-226; V1.3 Step 5).

``SemanticKnowledgePort`` ranks the chunks of one pinned snapshot by exact cosine similarity between a query's vector and each chunk's vector. It does not embed anything itself: it asks an
``Embedder``, which is a protocol, so the retrieval logic (the mismatch checks, the cosine, the ordering, the ties, ``top_k``, the byte bound and the mapping of every failure to a typed
retrieval outcome) lives here, in the main runtime, and is tested without any model. What embeds is behind the boundary: the isolated process of ``semantic_process`` and the program of ``semantic_worker``.

What is pinned and what is refused. The model is pinned by its revision and its digests, never by name (``PINNED_MODEL``); a scheme id names the model, its revision, the dimension and the window, so a
different model is a different scheme and a different ``query_id``. The window is a hard bound: a text over ``max_pieces`` word pieces is *refused*, never truncated. A chunk over it makes the
index unbuildable (``open`` returns a typed ``unavailable`` failure naming the chunk); a query over it is refused as a ``request_mismatch``. Nothing an embedder returns is trusted: a wrong count, a wrong
dimension, a non-finite or degenerate vector, and a vector for a text that was over the window are all ``malformed_result``.

Similarity is exact: ``math.fsum`` for the dot product and the squared norms and one division, clamped to [-1, 1], never rounded, never approximate. Hits are ordered by score descending and then ``chunk_id``
ascending. Every chunk is a candidate, so a query always gets ``min(top_k, chunks)`` hits (unlike a lexical retriever). Given identical vectors the ranking is identical; whether an embedder gives identical vectors
is its own, stated property (D-220), and nothing here claims more.

Pure: no I/O, no clock, no randomness, no process and no library. The port is built once and never changed, so it is safe to call from any number of threads provided its embedder is.
"""

import math
import re
from collections.abc import Sequence
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from pydantic import Field, model_validator

from eidos.contracts import EidosModel

from .contracts import KnowledgeSnapshot
from .identity import SCHEME_ID_PATTERN, SHA256_HEX
from .retrieval import KB_ID_PATTERN, RetrievalFailure, RetrievalFailureKind, RetrievalRequest, RetrievalResult, RetrievedChunk

SEMANTIC_SCORE_KIND = "semantic-cosine-v1"

# The pinned model (D-226 ruling 4): the cached revision and digests the project recorded. ``directory_sha256`` is the SHA-256 of "<path>\n<file sha256>\n" for every file of the snapshot directory,
# paths relative and with "/", in sorted order; the worker recomputes it and refuses any difference.
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
MODEL_WEIGHTS_SHA256 = "eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b"
MODEL_DIRECTORY_SHA256 = "e99a362c5cdf060fe3dec4f42b61f3f847d80ce8881a8c716b3468bdf7ef03dc"
MODEL_DIMENSION = 384
MODEL_MAX_PIECES = 128  # word pieces including the two special tokens, the model's window (D-215)

MODEL_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,95}$"
VECTOR_NORM_FLOOR = 1e-100  # a vector whose length lies outside [floor, ceiling] cannot be ranked without underflow or overflow, and is refused
VECTOR_NORM_CEILING = 1e100

_SCHEME_ID = re.compile(SCHEME_ID_PATTERN)
_KB_ID = re.compile(KB_ID_PATTERN)


def semantic_scheme_id(identity: "SemanticModelIdentity") -> str:
    """The retrieval scheme id of a model: it names the score, the model, the first eight digits of its revision, the dimension and the window."""
    return f"{SEMANTIC_SCORE_KIND}/model={identity.model.rpartition('/')[2]}/rev={identity.revision[:8]}/dim={identity.dimension}/pieces={identity.max_pieces}"


class SemanticModelIdentity(EidosModel):
    """Which model embeds, exactly: its name, its revision and its digests, the dimension of its vectors and the window it can read."""

    model: str = Field(pattern=MODEL_NAME_PATTERN)
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    weights_sha256: str = Field(pattern=SHA256_HEX)
    directory_sha256: str = Field(pattern=SHA256_HEX)
    dimension: int = Field(ge=1)
    max_pieces: int = Field(ge=3)

    @model_validator(mode="after")
    def _check_the_scheme_id_it_names_is_well_formed(self) -> "SemanticModelIdentity":
        if _SCHEME_ID.fullmatch(semantic_scheme_id(self)) is None:
            raise ValueError("the scheme id a model identity names must have the shape of a scheme id")
        return self


PINNED_MODEL = SemanticModelIdentity(
    model=MODEL_NAME,
    revision=MODEL_REVISION,
    weights_sha256=MODEL_WEIGHTS_SHA256,
    directory_sha256=MODEL_DIRECTORY_SHA256,
    dimension=MODEL_DIMENSION,
    max_pieces=MODEL_MAX_PIECES,
)


class EmbeddedText(EidosModel):
    """What an embedder made of one text: how many word pieces it is, and its vector, or ``None`` if it was over the window and was refused."""

    pieces: int = Field(ge=1)
    vector: tuple[float, ...] | None = None


class EmbedderFailureKind(StrEnum):
    UNAVAILABLE = "unavailable"  # the embedder cannot start or is not running: no interpreter, no model, a library missing, a previous failure
    TIMEOUT = "timeout"  # it did not answer in time
    CRASHED = "crashed"  # it ended without answering
    MALFORMED_REPLY = "malformed_reply"  # it answered in a shape the protocol does not allow
    IDENTITY_MISMATCH = "identity_mismatch"  # the model it loaded is not the pinned one
    REQUEST_REFUSED = "request_refused"  # it refused the request itself (too many texts, a text too long)


class EmbedderFailure(EidosModel):
    """An embedding that could not be made. Returned, never raised."""

    kind: EmbedderFailureKind
    message: str = Field(min_length=1)


class Embedder(Protocol):
    """Makes vectors from texts. Synchronous, thread-safe and total: a failure is returned, never raised. ``identity`` says which model, and it does not change."""

    @property
    def identity(self) -> SemanticModelIdentity: ...

    def embed(self, texts: Sequence[str]) -> tuple[EmbeddedText, ...] | EmbedderFailure: ...


_FAILURE_KIND = MappingProxyType(
    {
        EmbedderFailureKind.UNAVAILABLE: RetrievalFailureKind.UNAVAILABLE,
        EmbedderFailureKind.TIMEOUT: RetrievalFailureKind.UNAVAILABLE,
        EmbedderFailureKind.CRASHED: RetrievalFailureKind.UNAVAILABLE,
        EmbedderFailureKind.IDENTITY_MISMATCH: RetrievalFailureKind.UNAVAILABLE,
        EmbedderFailureKind.MALFORMED_REPLY: RetrievalFailureKind.MALFORMED_RESULT,
        EmbedderFailureKind.REQUEST_REFUSED: RetrievalFailureKind.REQUEST_MISMATCH,
    }
)


def _failure_of(failure: EmbedderFailure) -> RetrievalFailure:
    return RetrievalFailure(kind=_FAILURE_KIND[failure.kind], message=f"the embedder failed ({failure.kind.value}): {failure.message}")


def vector_norm(vector: Sequence[float]) -> float:
    return math.sqrt(math.fsum(x * x for x in vector))


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """The cosine of the angle between two vectors of one length and non-zero norm: exact in the sense that every sum is ``math.fsum``, then clamped to [-1, 1] against the last-place error of one division."""
    if len(a) != len(b):
        raise ValueError("cosine similarity compares vectors of one length")
    norms = vector_norm(a) * vector_norm(b)
    if norms == 0.0 or not math.isfinite(norms):
        raise ValueError("cosine similarity needs vectors of finite, non-zero length")
    return max(-1.0, min(1.0, math.fsum(x * y for x, y in zip(a, b)) / norms))


def _vector_problem(item: EmbeddedText, identity: SemanticModelIdentity) -> str | None:
    """What is wrong with an embedder's answer for one text that it says it embedded, or ``None``."""
    if item.pieces > identity.max_pieces:
        return f"a text of {item.pieces} word pieces was embedded, over the window of {identity.max_pieces}"
    vector = item.vector
    if vector is None:
        return "a text within the window came back with no vector"
    if len(vector) != identity.dimension:
        return f"a vector has {len(vector)} components, and the model's dimension is {identity.dimension}"
    if not all(math.isfinite(x) for x in vector):
        return "a vector has a component that is not a finite number"
    if not VECTOR_NORM_FLOOR <= vector_norm(vector) <= VECTOR_NORM_CEILING:
        return "a vector has no usable length"
    return None


class SemanticKnowledgePort:
    """A ``KnowledgePort`` over one snapshot whose chunks were embedded once, when the port was opened. Made only by ``open``: a port that exists can serve."""

    def __init__(self, *, kb_id: str, snapshot: KnowledgeSnapshot, embedder: Embedder, vectors: tuple[tuple[float, ...], ...]):
        self._kb_id = kb_id
        self._snapshot_id = snapshot.snapshot_id
        self._chunks = snapshot.chunks
        self._embedder = embedder
        self._identity = embedder.identity
        self._scheme_id = semantic_scheme_id(self._identity)
        self._vectors = vectors

    @classmethod
    def open(cls, snapshot: KnowledgeSnapshot, *, kb_id: str, embedder: Embedder, batch_size: int = 16) -> "SemanticKnowledgePort | RetrievalFailure":
        """Embed every chunk of ``snapshot``, in canonical order, ``batch_size`` texts to a request. The port, or the first thing that made an index impossible: a failure of the embedder, an answer that is
        not what an embedder may answer, or the first chunk (in canonical order) over the model's window."""
        if _KB_ID.fullmatch(kb_id) is None:
            raise ValueError("a knowledge base id has the shape of a source id")
        if batch_size < 1:
            raise ValueError("a batch holds at least one text")
        identity = embedder.identity
        chunks, vectors = snapshot.chunks, []
        for offset in range(0, len(chunks), batch_size):
            group = chunks[offset : offset + batch_size]
            answer = embedder.embed([chunk.text for chunk in group])
            if isinstance(answer, EmbedderFailure):
                return _failure_of(answer)
            if not isinstance(answer, tuple) or len(answer) != len(group) or not all(isinstance(item, EmbeddedText) for item in answer):
                return RetrievalFailure(kind=RetrievalFailureKind.MALFORMED_RESULT, message="the embedder did not answer with one embedded text for each text asked")
            for chunk, item in zip(group, answer):
                if item.pieces > identity.max_pieces and item.vector is None:
                    return RetrievalFailure(
                        kind=RetrievalFailureKind.UNAVAILABLE,
                        message=f"chunk {chunk.chunk_id[:12]} has {item.pieces} word pieces, over the model's window of {identity.max_pieces}: it is refused, never truncated",
                    )
                problem = _vector_problem(item, identity)
                if problem is not None:
                    return RetrievalFailure(kind=RetrievalFailureKind.MALFORMED_RESULT, message=f"chunk {chunk.chunk_id[:12]}: {problem}")
                vectors.append(item.vector)
        return cls(kb_id=kb_id, snapshot=snapshot, embedder=embedder, vectors=tuple(vectors))

    @property
    def kb_id(self) -> str:
        return self._kb_id

    @property
    def snapshot_id(self) -> str:
        return self._snapshot_id

    @property
    def scheme_id(self) -> str:
        return self._scheme_id

    @property
    def identity(self) -> SemanticModelIdentity:
        return self._identity

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult | RetrievalFailure:
        for name, served in (("kb_id", self._kb_id), ("snapshot_id", self._snapshot_id), ("scheme_id", self._scheme_id)):
            asked = getattr(request, name)
            if asked != served:
                return RetrievalFailure(kind=RetrievalFailureKind.REQUEST_MISMATCH, message=f"this port serves {name} {served!r}, and the request names {asked!r}")
        answer = self._embedder.embed([request.text])
        if isinstance(answer, EmbedderFailure):
            return _failure_of(answer)
        if not isinstance(answer, tuple) or len(answer) != 1 or not isinstance(answer[0], EmbeddedText):
            return RetrievalFailure(kind=RetrievalFailureKind.MALFORMED_RESULT, message="the embedder did not answer with one embedded text for the query")
        query = answer[0]
        if query.pieces > self._identity.max_pieces and query.vector is None:
            return RetrievalFailure(
                kind=RetrievalFailureKind.REQUEST_MISMATCH,
                message=f"the query has {query.pieces} word pieces, over the model's window of {self._identity.max_pieces}: it is refused, never truncated",
            )
        problem = _vector_problem(query, self._identity)
        if problem is not None:
            return RetrievalFailure(kind=RetrievalFailureKind.MALFORMED_RESULT, message=f"the query: {problem}")
        scored = sorted(
            ((cosine_similarity(query.vector, vector), chunk) for chunk, vector in zip(self._chunks, self._vectors)),
            key=lambda item: (-item[0], item[1].chunk_id),
        )
        chosen = scored[: request.top_k]
        size = sum(len(chunk.text.encode("utf-8")) for _, chunk in chosen)
        if size > request.max_result_bytes:
            return RetrievalFailure(
                kind=RetrievalFailureKind.RESULT_TOO_LARGE, message=f"the {len(chosen)} best hits hold {size} bytes of text, over the bound of {request.max_result_bytes}"
            )
        return RetrievalResult(
            query_id=request.query_id,
            kb_id=self._kb_id,
            snapshot_id=self._snapshot_id,
            scheme_id=self._scheme_id,
            score_kind=SEMANTIC_SCORE_KIND,
            hits=tuple(RetrievedChunk(rank=rank, chunk=chunk, score=score) for rank, (score, chunk) in enumerate(chosen, start=1)),
        )
