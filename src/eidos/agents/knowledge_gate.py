"""The knowledge gate: an agent's one way to knowledge (decisions.md D-208, D-216, D-217, D-224, D-225, D-228; V1.3 Step 7).

An agent that wants knowledge calls ``KnowledgeAccess.retrieve(context, query)`` and gets back one typed ``KnowledgeGateOutcome``. ``KnowledgeGate`` is the implementation, beside
``ToolGate``, and it is the only thing that ever reaches a ``KnowledgePort``:

1. **The bounds are the knowledge base's, not the agent's.** The request is built from the ``KnowledgeBaseDescriptor`` (the knowledge base, its pinned snapshot, its retrieval scheme,
   ``top_k`` and the byte bound, D-216), so an agent cannot state a bound, raise one, or name another snapshot or scheme. The query is the text it is given, canonicalised.
2. **A duplicate is served, not asked.** The same query (the same ``query_id``) again in one execution, whichever plan attempt or node makes it, is answered from the stored answer: the
   port is not called, the ledger does not change and no artifact is written. A failed retrieval is never stored, so a repeat asks the port again.
3. **An answer is checked, never trusted.** A port that raises, answers in a shape it did not promise, or answers a different request (``result_problem``) is a typed failure.
4. **Evidence enters deterministically.** Each hit becomes an ``EvidenceRecord`` of the pinned snapshot (a chunk the snapshot does not hold is refused), recorded in the ``EvidenceLedger``,
   and its text is stored once as a supplied artifact under its **evidence reference**, exactly as ``ToolGate`` stores a tool document, so a model can cite ``[[evidence:...]]`` and the
   existing citation and verification contracts resolve it unchanged. The ledger is the authority for provenance and independence; the artifact is what a model reads and a citation
   points at. The same chunk retrieved by two queries is one record (it keeps both query ids) and one artifact; a different text under a held reference is refused and nothing is stored.

The gate never raises for a retrieval outcome (an empty query is a programming error and raises). Retrieval is not budgeted and has no denial: with the goal as the only query and
duplicates served, one execution asks the port at most once, so the bounds above are all it needs (D-228 reading 6; the admission part of D-222 point 5 stays Open). One lock covers a
retrieval from the check for a stored answer to the storing of its evidence, so two nodes on worker threads never ask twice or store twice. This module names no retriever, no embedder,
no model and no process: whatever is injected as the port is all it knows, and it depends on ``eidos.knowledge`` only through the names listed in the import below, from the package root.
"""

import threading
from enum import StrEnum
from typing import Protocol

from pydantic import Field, model_validator

from eidos.contracts import ArtifactRef, EidosModel, ExecutionId
from eidos.knowledge import (
    KB_ID_PATTERN,
    EvidenceRecord,
    EvidenceRefusal,
    KnowledgePort,
    KnowledgeSnapshot,
    RetrievalFailure,
    RetrievalFailureKind,
    RetrievalRequest,
    RetrievalResult,
    canonical_query_text,
    evidence_from_snapshot,
    merge_evidence,
    result_problem,
)
from eidos.runtime import ExecutionContext

from .artifacts import Artifact, ArtifactConflict, ArtifactStore
from .evidence_ledger import EvidenceLedger

EVIDENCE_CONTENT_TYPE = "text/plain"


class KnowledgeBaseDescriptor(EidosModel):
    """One knowledge base as the gate serves it: its id, its pinned snapshot, the retrieval scheme it is asked under and its two bounds (D-216, D-225 reading 4)."""

    kb_id: str = Field(pattern=KB_ID_PATTERN)
    snapshot: KnowledgeSnapshot
    scheme_id: str
    top_k: int = Field(ge=1)
    max_result_bytes: int = Field(ge=1)

    @model_validator(mode="after")
    def _check_a_request_can_be_made_from_it(self) -> "KnowledgeBaseDescriptor":
        RetrievalRequest(  # raises if the scheme id or the knowledge base id has not the shape a request needs
            kb_id=self.kb_id, snapshot_id=self.snapshot.snapshot_id, scheme_id=self.scheme_id, text="probe", top_k=self.top_k, max_result_bytes=self.max_result_bytes
        )
        return self


class KnowledgeGateKind(StrEnum):
    RETRIEVED = "retrieved"  # the port was asked
    SERVED = "served"  # a duplicate, answered from the stored answer: the port was not asked


class KnowledgeGateOutcome(EidosModel):
    """Everything one call to the gate came to. ``result`` is what was answered (an answer, which may hold no hits, or a typed failure); ``refs`` are the evidence references the answer
    became, one per hit and in rank order: each is a supplied artifact of the execution and a record in the ledger."""

    kind: KnowledgeGateKind
    query_id: str
    result: RetrievalResult | RetrievalFailure
    refs: tuple[ArtifactRef, ...] = ()

    @model_validator(mode="after")
    def _check_the_references_belong_to_the_answer(self) -> "KnowledgeGateOutcome":
        if isinstance(self.result, RetrievalFailure):
            if self.refs or self.kind is KnowledgeGateKind.SERVED:
                raise ValueError("a failure has no evidence and is never served from storage")
            return self
        if [str(ref) for ref in self.refs] != [hit.evidence_ref for hit in self.result.hits]:
            raise ValueError("the references name the hits of the answer, one each and in rank order")
        return self

    @property
    def failed(self) -> bool:
        return isinstance(self.result, RetrievalFailure)

    @property
    def did_not_complete(self) -> bool:
        """Whether the retrieval itself did not happen: the knowledge base could not be reached. Every other failure, and an empty answer, is a retrieval that completed."""
        return isinstance(self.result, RetrievalFailure) and self.result.kind is RetrievalFailureKind.UNAVAILABLE

    @property
    def explanation(self) -> str:
        """Why there is no evidence, in words; only meaningful when ``refs`` is empty."""
        if isinstance(self.result, RetrievalFailure):
            return f"the knowledge retrieval failed ({self.result.kind.value}): {self.result.message}"
        return "the knowledge base returned no evidence"


class KnowledgeAccess(Protocol):
    """What an agent calls. Synchronous, thread-safe and total: every outcome is a returned ``KnowledgeGateOutcome``."""

    def retrieve(self, context: ExecutionContext, query: str) -> KnowledgeGateOutcome: ...


def _failure(kind: RetrievalFailureKind, message: str) -> RetrievalFailure:
    return RetrievalFailure(kind=kind, message=message)


class KnowledgeGate:
    def __init__(self, *, descriptor: KnowledgeBaseDescriptor, port: KnowledgePort, ledger: EvidenceLedger, store: ArtifactStore):
        self._descriptor, self._port, self._ledger, self._store = descriptor, port, ledger, store
        self._lock = threading.Lock()
        self._answers: dict[tuple[ExecutionId, str], tuple[RetrievalResult, tuple[ArtifactRef, ...]]] = {}

    @property
    def descriptor(self) -> KnowledgeBaseDescriptor:
        return self._descriptor

    def retrieve(self, context: ExecutionContext, query: str) -> KnowledgeGateOutcome:
        text = canonical_query_text(query)
        if not text:
            raise ValueError("a knowledge query is not empty: an agent with no query makes no retrieval")
        descriptor = self._descriptor
        request = RetrievalRequest(
            kb_id=descriptor.kb_id,
            snapshot_id=descriptor.snapshot.snapshot_id,
            scheme_id=descriptor.scheme_id,
            text=text,
            top_k=descriptor.top_k,
            max_result_bytes=descriptor.max_result_bytes,
        )
        query_id = request.query_id
        key = (context.execution_id, query_id)
        with self._lock:
            stored = self._answers.get(key)
            if stored is not None:
                result, refs = stored
                return KnowledgeGateOutcome(kind=KnowledgeGateKind.SERVED, query_id=query_id, result=result, refs=refs)
            answer = self._ask(request)
            if isinstance(answer, RetrievalFailure):
                return KnowledgeGateOutcome(kind=KnowledgeGateKind.RETRIEVED, query_id=query_id, result=answer)
            admitted = self._admit(context.execution_id, request, answer)
            if isinstance(admitted, RetrievalFailure):
                return KnowledgeGateOutcome(kind=KnowledgeGateKind.RETRIEVED, query_id=query_id, result=admitted)
            self._answers[key] = (answer, admitted)
            return KnowledgeGateOutcome(kind=KnowledgeGateKind.RETRIEVED, query_id=query_id, result=answer, refs=admitted)

    # --- the port --------------------------------------------------------------------------------------------------------------

    def _ask(self, request: RetrievalRequest) -> RetrievalResult | RetrievalFailure:
        try:
            answer = self._port.retrieve(request)
        except Exception as error:  # noqa: BLE001 - a port is total; one that raises is a fault, recorded as a typed failure
            return _failure(RetrievalFailureKind.UNAVAILABLE, f"the knowledge port raised {type(error).__name__}")
        if isinstance(answer, RetrievalFailure):
            return answer
        if not isinstance(answer, RetrievalResult):
            return _failure(RetrievalFailureKind.MALFORMED_RESULT, "the knowledge port returned neither an answer nor a failure")
        problem = result_problem(request, answer)
        if problem is not None:
            return _failure(RetrievalFailureKind.MALFORMED_RESULT, problem)
        return answer

    # --- evidence --------------------------------------------------------------------------------------------------------------

    def _admit(self, execution_id: ExecutionId, request: RetrievalRequest, answer: RetrievalResult) -> tuple[ArtifactRef, ...] | RetrievalFailure:
        """Turn an answer into ledger records and artifacts, or refuse all of it: nothing is recorded or stored unless every hit can be."""
        snapshot = self._descriptor.snapshot
        records: list[EvidenceRecord] = []
        for hit in answer.hits:
            record = evidence_from_snapshot(snapshot, hit.chunk.chunk_id, query_id=request.query_id)
            if isinstance(record, EvidenceRefusal):
                return _failure(RetrievalFailureKind.MALFORMED_RESULT, f"the answer names a chunk the snapshot does not hold: {record.message}")
            held = self._ledger.get(execution_id, record.evidence_ref)
            if held is not None:
                merged = merge_evidence(held, record)
                if isinstance(merged, EvidenceRefusal):
                    return _failure(RetrievalFailureKind.MALFORMED_RESULT, f"the ledger refuses the evidence of {record.evidence_ref}: {merged.message}")
            existing = self._store.get(execution_id, ArtifactRef(record.evidence_ref))
            if existing is not None and existing.content != hit.chunk.text:
                return _failure(RetrievalFailureKind.MALFORMED_RESULT, f"the reference {record.evidence_ref} is already taken in this execution by other content")
            records.append(record)
        refs: list[ArtifactRef] = []
        for record in records:
            ref = ArtifactRef(record.evidence_ref)
            recorded = self._ledger.record(execution_id, record)
            if isinstance(recorded, EvidenceRefusal):
                return _failure(RetrievalFailureKind.MALFORMED_RESULT, f"the ledger refuses the evidence of {record.evidence_ref}: {recorded.message}")
            if self._store.get(execution_id, ref) is None:
                try:
                    self._store.put_supplied(execution_id, Artifact(ref=ref, content_type=EVIDENCE_CONTENT_TYPE, content=record.chunk.text))
                except ArtifactConflict:
                    return _failure(RetrievalFailureKind.MALFORMED_RESULT, f"the reference {record.evidence_ref} is already taken in this execution")
            refs.append(ref)
        return tuple(refs)
