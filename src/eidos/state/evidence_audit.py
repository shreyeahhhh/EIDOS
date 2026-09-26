"""The evidence audit: a derived, read-only projection of an execution record (decisions.md D-218, D-225; V1.3 Step 4; invariants 15 and 16).

``audit_evidence(record)`` walks the chain from a conclusion back to its evidence using only what the log recorded: each reference a work artifact cited (``StepRecord.citations``) is
matched against the knowledge retrievals recorded in the same execution (``StepRecord.retrievals``), and the audit says, for every citation, whether it is knowledge evidence and, if
so, which chunk, document, source, knowledge base, query, snapshot, scheme and rank it came from. It is pure: it retrieves nothing, loads nothing and asks nothing of a snapshot, an
index or a model, so it can run wherever the log can (invariant 15). It is recomputed every time and is never stored as truth.

A citation is model-asserted, so the audit reports what the record shows and no more: a reference that names no recorded hit is ``unresolved``, one that names hits for more than one chunk is
``ambiguous``, and one that is not shaped like an evidence reference (a supplied document, a tool document, another artifact) is ``not_evidence``. It does not judge whether a cited
chunk supports the claim (D-015 is Open) and it does not count independent sources: the derivations that rule needs live in the snapshot, which ``snapshot_id`` pins, so the count is
composed by a caller that holds it (``cited`` lists the distinct documents that were cited and resolved).
"""

from enum import StrEnum
from typing import NamedTuple

from pydantic import Field

from eidos.contracts import ArtifactRef, EidosModel, StepId

from .execution_record import ExecutionRecord
from .payloads import EVIDENCE_REF_HEX_LENGTH, EVIDENCE_REF_PREFIX, evidence_ref_of_chunk_id

_HEX_DIGITS = frozenset("0123456789abcdef")
_SHA256_HEX = r"^[0-9a-f]{64}$"
_SOURCE_ID = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"


class CitationKind(StrEnum):
    RESOLVED = "resolved"  # an evidence reference that names recorded hits, all of one chunk
    UNRESOLVED = "unresolved"  # shaped like an evidence reference, but no recorded retrieval carries it
    AMBIGUOUS = "ambiguous"  # recorded hits carry it for more than one chunk, or one chunk under more than one document or source
    NOT_EVIDENCE = "not_evidence"  # anything else a work artifact cited


class RetrievedBy(EidosModel):
    """One recorded hit of a cited chunk: the step that made the retrieval, the query, the snapshot and scheme it ran under, and where the chunk ranked."""

    step_id: StepId
    query_id: str = Field(pattern=_SHA256_HEX)
    snapshot_id: str = Field(pattern=_SHA256_HEX)
    scheme_id: str
    rank: int = Field(ge=1)


class CitationTrace(EidosModel):
    """One citation, traced. ``step_id`` is the step whose artifact cited ``ref``; the identity fields are present only when the citation resolved."""

    step_id: StepId
    ref: ArtifactRef
    kind: CitationKind
    kb_id: str | None = None
    chunk_id: str | None = Field(default=None, pattern=_SHA256_HEX)
    document_id: str | None = Field(default=None, pattern=_SHA256_HEX)
    source_id: str | None = Field(default=None, pattern=_SOURCE_ID)
    retrieved_by: tuple[RetrievedBy, ...] = ()  # every recorded hit of the chunk, in the order the log recorded them


class CitedDocument(EidosModel):
    source_id: str = Field(pattern=_SOURCE_ID)
    document_id: str = Field(pattern=_SHA256_HEX)


class EvidenceAudit(EidosModel):
    traces: tuple[CitationTrace, ...] = ()  # in plan order, then in the order each artifact listed its references
    cited: tuple[CitedDocument, ...] = ()  # the distinct documents behind the resolved citations, sorted by source and then document


def _is_evidence_ref(ref: str) -> bool:
    """Whether ``ref`` has the shape of an evidence reference: the prefix and sixteen lower-case hexadecimal digits."""
    digits = ref[len(EVIDENCE_REF_PREFIX) :]
    return ref.startswith(EVIDENCE_REF_PREFIX) and len(digits) == EVIDENCE_REF_HEX_LENGTH and set(digits) <= _HEX_DIGITS


class _RecordedHit(NamedTuple):
    chunk_id: str
    document_id: str
    source_id: str
    kb_id: str
    where: RetrievedBy


def audit_evidence(record: ExecutionRecord) -> EvidenceAudit:
    recorded: dict[str, list[_RecordedHit]] = {}  # evidence reference -> every recorded hit that carries it, in log order
    for step in record.steps:
        for facts in step.retrievals:
            for hit in facts.hits:  # a failure carries no hits (its own validator), so only an answer contributes any
                where = RetrievedBy(step_id=step.step_id, query_id=facts.query_id, snapshot_id=facts.snapshot_id, scheme_id=facts.scheme_id, rank=hit.rank)
                recorded.setdefault(evidence_ref_of_chunk_id(hit.chunk_id), []).append(_RecordedHit(hit.chunk_id, hit.document_id, hit.source_id, facts.kb_id, where))

    traces: list[CitationTrace] = []
    cited: set[tuple[str, str]] = set()
    for step in record.steps:
        for ref in step.citations:
            if not _is_evidence_ref(ref):
                traces.append(CitationTrace(step_id=step.step_id, ref=ref, kind=CitationKind.NOT_EVIDENCE))
                continue
            found = recorded.get(ref, [])
            if not found:
                traces.append(CitationTrace(step_id=step.step_id, ref=ref, kind=CitationKind.UNRESOLVED))
                continue
            where = tuple(hit.where for hit in found)
            identities = {(hit.chunk_id, hit.document_id, hit.source_id, hit.kb_id) for hit in found}
            if len(identities) > 1:
                traces.append(CitationTrace(step_id=step.step_id, ref=ref, kind=CitationKind.AMBIGUOUS, retrieved_by=where))
                continue
            ((chunk_id, document_id, source_id, kb_id),) = identities
            traces.append(
                CitationTrace(
                    step_id=step.step_id, ref=ref, kind=CitationKind.RESOLVED, kb_id=kb_id, chunk_id=chunk_id, document_id=document_id, source_id=source_id, retrieved_by=where
                )
            )
            cited.add((source_id, document_id))
    return EvidenceAudit(traces=tuple(traces), cited=tuple(CitedDocument(source_id=s, document_id=d) for s, d in sorted(cited)))
