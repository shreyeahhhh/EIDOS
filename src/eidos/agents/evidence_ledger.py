"""The evidence ledger and the resolver for existing V1.2 documents (decisions.md D-208, D-209, D-210, D-222; V1.3 Step 3).

``EvidenceLedger`` holds the evidence retrieved during an execution, in memory and behind one lock, apart from the artifact store: a retrieved chunk is not a
supplied artifact (D-207 reading 1). Evidence has one record per evidence reference. Recording the same chunk again keeps that record and adds the retrieving
query's id to it; a different chunk under the same reference, or the same chunk from a different snapshot, is refused, and nothing is merged.

``resolve_supplied_evidence`` maps existing V1.2 documents, a caller-supplied artifact or a tool document, into the knowledge identity (D-210). It reads the
artifact store and writes nothing: no artifact, reference or recorded fact is touched, and the verifier is not involved.

Independence is resolved over a set of cited evidence (``EvidenceLedger.resolve_independence``): whether a document counts depends on what else is cited, so no
key-by-key lookup can express it. The declared derivations are an explicit argument, so leaving them out is never a silent default.

Import boundary (D-222): this is the one agents module that depends on ``eidos.knowledge``, and only on the names listed in the import below, taken from the
package root. ``eidos.knowledge`` never imports this package.
"""

import threading
from collections.abc import Iterable, Mapping

from pydantic import model_validator

from eidos.contracts import ArtifactRef, EidosModel, ExecutionId
from eidos.knowledge import (
    DocumentRef,
    EvidenceRecord,
    EvidenceRefusal,
    EvidenceRefusalCode,
    IndependenceResolution,
    legacy_supplied_record,
    legacy_tool_record,
    merge_evidence,
    resolve_independence,
)

from .artifacts import ArtifactStore
from .tool_gate import parse_tool_document_ref


class EvidenceLedger:
    """The evidence of each execution. Thread-safe; every method is scoped by ``execution_id`` and nothing is shared between executions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._held: dict[tuple[ExecutionId, str], EvidenceRecord] = {}

    def record(self, execution_id: ExecutionId, evidence: EvidenceRecord) -> EvidenceRecord | EvidenceRefusal:
        """Record ``evidence``: the ledger's record for its reference afterwards, or the refusal. A refusal changes nothing."""
        key = (execution_id, evidence.evidence_ref)
        with self._lock:
            held = self._held.get(key)
            if held is None:
                self._held[key] = evidence
                return evidence
            merged = merge_evidence(held, evidence)
            if isinstance(merged, EvidenceRecord):
                self._held[key] = merged
            return merged

    def get(self, execution_id: ExecutionId, evidence_ref: str) -> EvidenceRecord | None:
        with self._lock:
            return self._held.get((execution_id, evidence_ref))

    def records(self, execution_id: ExecutionId) -> tuple[EvidenceRecord, ...]:
        """Every record of this execution, ordered by evidence reference so the order never depends on insertion."""
        with self._lock:
            mine = (record for (owner, _), record in self._held.items() if owner == execution_id)
            return tuple(sorted(mine, key=lambda record: record.evidence_ref))

    def resolve_independence(
        self, execution_id: ExecutionId, cited: Iterable[str], *, derived_from: Mapping[DocumentRef, Iterable[DocumentRef]]
    ) -> IndependenceResolution:
        """The independent sources behind the cited evidence references of this execution. A reference the ledger does not hold is reported, never counted."""
        return resolve_independence(cited, self.records(execution_id), derived_from)


class ArtifactEvidence(EidosModel):
    """What one artifact reference resolved to: its evidence, or the reason it is not evidence. Exactly one of the two."""

    artifact_ref: ArtifactRef
    evidence: EvidenceRecord | None = None
    refusal: EvidenceRefusal | None = None

    @model_validator(mode="after")
    def _check_exactly_one_outcome(self) -> "ArtifactEvidence":
        if (self.evidence is None) == (self.refusal is None):
            raise ValueError("an artifact reference resolves to evidence or to a refusal, never both and never neither")
        return self


def resolve_supplied_evidence(store: ArtifactStore, execution_id: ExecutionId, refs: Iterable[ArtifactRef]) -> tuple[ArtifactEvidence, ...]:
    """Map V1.2 supplied artifacts into the knowledge identity, one result per distinct reference, ordered by reference (D-210).

    A reference of the form ``tool_document_ref`` makes is a tool document, and its identity is the tool and the provider's document id; any other supplied
    reference is a caller document, and its identity is that reference. Either way the document id is the digest of the normalised content. A reference that
    is not a supplied artifact of the execution, such as one a step produced, is refused with ``NOT_SUPPLIED``.
    """
    supplied = {artifact.ref: artifact for artifact in store.supplied(execution_id)}
    results: list[ArtifactEvidence] = []
    for ref in sorted(set(refs)):
        artifact = supplied.get(ref)
        if artifact is None:
            refusal = EvidenceRefusal(code=EvidenceRefusalCode.NOT_SUPPLIED, message=f"{str(ref)!r} is not a supplied artifact of this execution")
            results.append(ArtifactEvidence(artifact_ref=ref, refusal=refusal))
            continue
        tool_ref = parse_tool_document_ref(ref)
        outcome = legacy_supplied_record(str(ref), artifact.content) if tool_ref is None else legacy_tool_record(tool_ref[0], tool_ref[2], artifact.content)
        if isinstance(outcome, EvidenceRefusal):
            results.append(ArtifactEvidence(artifact_ref=ref, refusal=outcome))
        else:
            results.append(ArtifactEvidence(artifact_ref=ref, evidence=outcome))
    return tuple(results)
