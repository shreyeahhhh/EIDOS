"""Fixtures for the knowledge gate and the Research integration (decisions.md D-228; V1.3 Step 7).

A small corpus and its pinned snapshot (built with the real chunker), a knowledge base descriptor over it, a scripted ``KnowledgePort`` that counts what reaches it, and a mission whose
goal is the query. The mission and its plan reuse the V1.2 search fixture's shape (gather, which researches, then analyse, then the existing verification), because nothing about the
mission changes when its Research node asks a knowledge base instead of a tool. Nothing here does I/O.
"""

import threading

from eidos.agents import KnowledgeBaseDescriptor
from eidos.knowledge import (
    LEXICAL_SCHEME_ID,
    KnowledgeChunk,
    KnowledgeSnapshot,
    RetrievalFailure,
    RetrievalRequest,
    RetrievalResult,
    RetrievedChunk,
    build_snapshot,
)

from eidos_knowledge_factories import SCHEME, small_corpus
from eidos_search_fixture import attempt_context, make_tool_mission, tool_mission_plan

KB = "facility"
GOAL = "inspection checklist before restart"
SECOND_GOAL = "grid operator notified before reconnection"
SNAPSHOT = build_snapshot(small_corpus(), SCHEME)


def descriptor_for(snapshot: KnowledgeSnapshot = SNAPSHOT, *, scheme_id: str = LEXICAL_SCHEME_ID, top_k: int = 4, max_result_bytes: int = 10**6, kb_id: str = KB) -> KnowledgeBaseDescriptor:
    return KnowledgeBaseDescriptor(kb_id=kb_id, snapshot=snapshot, scheme_id=scheme_id, top_k=top_k, max_result_bytes=max_result_bytes)


def make_rag_mission(*, goal: str = GOAL, seed: int = 1, min_independent_evidence: int = 2, max_replans: int | None = None):
    """A real, valid mission whose goal is the query. It asks nothing of any tool."""
    return make_tool_mission(seed=seed, goal=goal, min_independent_evidence=min_independent_evidence, max_replans=max_replans)


def hits_of(chunks) -> tuple[RetrievedChunk, ...]:
    return tuple(RetrievedChunk(rank=rank, chunk=chunk) for rank, chunk in enumerate(chunks, start=1))


def answer_with(request: RetrievalRequest, chunks: tuple[KnowledgeChunk, ...]) -> RetrievalResult:
    """An unscored answer to ``request`` holding ``chunks`` in the order given."""
    return RetrievalResult(query_id=request.query_id, kb_id=request.kb_id, snapshot_id=request.snapshot_id, scheme_id=request.scheme_id, hits=hits_of(chunks))


class ScriptedKnowledgePort:
    """A ``KnowledgePort`` that answers as a test scripted and records every request it is given, so a test can prove what was and was not asked.

    ``answer`` is a callable taking the request and returning a result or a failure, or a single value returned for every call (an exception instance is raised). Thread-safe.
    """

    def __init__(self, answer):
        self._answer = answer
        self._lock = threading.Lock()
        self.requests: list[RetrievalRequest] = []

    def retrieve(self, request: RetrievalRequest):
        with self._lock:
            self.requests.append(request)
        outcome = self._answer(request) if callable(self._answer) else self._answer
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    @property
    def calls(self) -> int:
        with self._lock:
            return len(self.requests)


def failing_port(kind, message: str = "scripted failure") -> ScriptedKnowledgePort:
    return ScriptedKnowledgePort(RetrievalFailure(kind=kind, message=message))


__all__ = [
    "GOAL", "KB", "SECOND_GOAL", "SNAPSHOT", "ScriptedKnowledgePort", "answer_with", "attempt_context", "descriptor_for", "failing_port", "hits_of", "make_rag_mission", "tool_mission_plan",
]
