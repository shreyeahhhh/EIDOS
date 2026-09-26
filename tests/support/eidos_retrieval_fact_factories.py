"""Test-support fixtures for retrieval and citation facts (decisions.md D-218, D-225; V1.3 Step 4).

Builders for ``RetrievalFacts`` of each outcome, a helper that settles a node with retrievals and citations in a hand-built log, and a work agent that adds retrieval facts through
the tracker the way a recording knowledge port will. Nothing here retrieves, reads a clock or touches the file system: a fact built here is a fixed test value, never a measurement.
"""

from collections.abc import Mapping

from eidos.contracts import ArtifactRef
from eidos.state import NodeSettledPayload, RetrievalFacts, RetrievalHitFacts, RetrievalOutcome

KB_ID = "facility"
SCHEME_ID = "lexical-bm25-v1/k1=1.2/b=0.75/tokens=word-v1"
SCORE_KIND = "lexical-bm25-v1"
SNAPSHOT_ID = "5" * 64


def hex64(number: int) -> str:
    """A well-formed digest (64 lowercase hex characters), distinct for each ``number``."""
    return f"{number:064x}"


def hit(rank: int = 1, *, chunk: int | None = None, document: int | None = None, source: str = "ops", score: float | None = 2.0) -> RetrievalHitFacts:
    """One hit; the chunk, document and content digest default to numbers derived from the rank, so hits differ unless told otherwise."""
    chunk = 1000 + rank if chunk is None else chunk
    return RetrievalHitFacts(
        rank=rank, chunk_id=hex64(chunk), document_id=hex64(document if document is not None else 2000 + rank), source_id=source, content_digest=hex64(3000 + chunk), score=score
    )


def scored_hits(count: int = 3) -> tuple[RetrievalHitFacts, ...]:
    """``count`` hits with strictly descending scores, so they are in a valid order."""
    return tuple(hit(rank, score=float(count - rank + 1)) for rank in range(1, count + 1))


def answer(*, query: int = 1, hits=None, top_k: int = 5, result_bytes: int | None = 900, elapsed_ms: int | None = 3, score_kind: str | None = SCORE_KIND, kb_id: str = KB_ID) -> RetrievalFacts:
    hits = scored_hits() if hits is None else tuple(hits)
    return RetrievalFacts(
        kb_id=kb_id, snapshot_id=SNAPSHOT_ID, scheme_id=SCHEME_ID, query_id=hex64(query), top_k=top_k, outcome=RetrievalOutcome.RESULT,
        score_kind=score_kind, hits=hits, result_bytes=result_bytes, elapsed_ms=elapsed_ms,
    )


def empty_answer(*, query: int = 1, top_k: int = 5) -> RetrievalFacts:
    return answer(query=query, hits=(), top_k=top_k, result_bytes=0)


def failure(outcome: RetrievalOutcome = RetrievalOutcome.UNAVAILABLE, *, query: int = 1, top_k: int = 5, elapsed_ms: int | None = 1) -> RetrievalFacts:
    return RetrievalFacts(kb_id=KB_ID, snapshot_id=SNAPSHOT_ID, scheme_id=SCHEME_ID, query_id=hex64(query), top_k=top_k, outcome=outcome, elapsed_ms=elapsed_ms)


def settle_with_retrievals(log, result, retrievals=(), citations=(), *, dispatched: bool = True, duration_ms: int | None = 1000, verification=None):
    """Settle ``result`` in a hand-built ``LogBuilder`` log, carrying ``retrievals`` and ``citations``, without touching the shared builder."""
    return log.add(NodeSettledPayload(
        plan_id=log.plan.plan_id, result=result, dispatched=dispatched, duration_ms=duration_ms if dispatched else None,
        retrievals=tuple(retrievals), citations=tuple(ArtifactRef(c) for c in citations), verification=verification,
    ))


class RetrievalFactsInjector:
    """A work agent that does exactly what the agent it wraps does, and adds ``RetrievalFacts`` to the node it is running through the tracker, the way a recording
    knowledge port will. It retrieves nothing: the facts are handed to it. ``raise_after`` makes it raise once they are added."""

    def __init__(self, inner, tracker, facts_by_step: Mapping[str, tuple[RetrievalFacts, ...]], *, raise_after: BaseException | None = None):
        self.inner, self.tracker, self.facts_by_step, self.raise_after = inner, tracker, facts_by_step, raise_after

    def run(self, context, node):
        collector = self.tracker.current_retrievals()
        if collector is not None:
            collector.extend(self.facts_by_step.get(str(node.step_id), ()))
        if self.raise_after is not None:
            raise self.raise_after
        return self.inner.run(context, node)
