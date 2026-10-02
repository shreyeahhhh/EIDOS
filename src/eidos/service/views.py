"""What the service answers with, and the pure functions that derive it from a replayed log (decisions.md D-234; ``docs/13`` section 7).

**Every derived answer is computed from the recorded events by the existing projections** (``replay``, ``execution_record``, ``audit_evidence``); nothing is read from a stored status and
nothing is written. The response models reuse EIDOS's own (``ExecutionRecord``, ``EventRecord``, ``EvidenceAudit``, ``VerificationFacts``) and add only what the API needs around them. There is
no confidence and no score anywhere in them: verification computes none (invariant 13; D-015, D-121, D-159), and a ``PASS`` is not a claim that the reliability contract is satisfied (D-146).

**The whole-execution view for evidence.** ``execution_record`` with no plan is the *last plan's* steps. A retrieval fact lives on the node of the attempt that made it, and a replan attempt's
Research node is served the same answer by the ``KnowledgeGate`` and records no retrieval of its own (D-228 reading 5), so an audit over the last plan alone would call that attempt's citations
unresolved although they were retrieved. ``whole_execution_record`` therefore lays every plan's steps, in plan order, into one ``ExecutionRecord`` (through the record's own strict JSON form, so it
is validated, never constructed around its validators) and ``audit_evidence`` reads that.
"""

import json
from uuid import UUID

from eidos.agents import ArtifactStore, parse_tool_document_ref
from eidos.contracts import (
    ArtifactRef,
    EidosModel,
    MissionId,
    MissionStatus,
    PlanStepKind,
    TenantId,
)
from eidos.contracts._validators import UtcDateTime
from eidos.runtime import NodeStatus
from eidos.state import (
    CitationKind,
    EventRecord,
    EvidenceAudit,
    ExecutionRecord,
    MissionFailureCause,
    ReplayRejection,
    VerificationFacts,
    audit_evidence,
    execution_record,
    replay,
)

from .errors import IntegrityFailure
from .ports import MissionRecord, RunStatus


class CreatedMission(EidosModel):
    mission_id: MissionId
    run_status: RunStatus
    created_at: UtcDateTime


class StartedMission(EidosModel):
    mission_id: MissionId
    run_status: RunStatus


class Counters(EidosModel):
    agent_calls_used: int
    tool_calls_used: int
    retries_used: int
    replans_used: int
    tokens_used: int  # provider-reported tokens only: a lower bound, never an estimate
    execution_time_used_ms: int  # accumulated accounted node time, not wall-clock duration


class MissionSummary(EidosModel):
    """The run's API-level status, and, once events exist, what the folded log says the mission is. ``mission_status`` is absent while no event exists."""

    mission_id: MissionId
    tenant_id: TenantId
    created_by: UUID
    created_at: UtcDateTime
    goal: str
    run_status: RunStatus
    run_status_reason: str | None = None
    mission_status: MissionStatus | None = None
    status_reason: str | None = None
    failure_cause: MissionFailureCause | None = None
    verified: bool | None = None
    plan_version: int | None = None
    counters: Counters | None = None
    last_sequence: int


class EventsPage(EidosModel):
    events: tuple[EventRecord, ...]
    last_sequence: int  # the mission's durable last sequence, so a poller knows whether more exist
    next_after: int  # pass this as ``after`` to continue


class ResultArtifact(EidosModel):
    ref: ArtifactRef
    content_type: str
    content: str
    source_refs: tuple[ArtifactRef, ...]


class MissionFailure(EidosModel):
    cause: MissionFailureCause
    reason: str | None = None


class MissionResult(EidosModel):
    mission_status: MissionStatus
    verified: bool | None = None  # only a completed mission says
    verdict: VerificationFacts | None = None  # the verifier's verdict and reason, word for word
    artifacts: tuple[ResultArtifact, ...]
    failure: MissionFailure | None = None


class EvidenceItem(EidosModel):
    ref: ArtifactRef
    content_type: str
    content: str


class EvidenceView(EidosModel):
    audit: EvidenceAudit
    evidence: tuple[EvidenceItem, ...]


def replayed_state(records: tuple[EventRecord, ...]):
    """The folded ``MissionState`` of a stored log, or an ``IntegrityFailure``: a stored log that does not replay is a fault of the store, never a mission outcome."""
    replayed = replay(records)
    if replayed.rejection is not None:
        raise IntegrityFailure(f"the stored log does not replay: {replayed.rejection.code.value}")
    return replayed.state


def execution_of(records: tuple[EventRecord, ...]) -> ExecutionRecord:
    projected = execution_record(records)
    if isinstance(projected, ReplayRejection):
        raise IntegrityFailure(f"the stored log does not replay: {projected.code.value}")
    return projected


def whole_execution_record(records: tuple[EventRecord, ...]) -> ExecutionRecord:
    """Every plan's steps, in plan order, in one validated ``ExecutionRecord`` (see the module docstring). A mission with one plan is returned as is."""
    last = execution_of(records)
    plans = replayed_state(records).plans
    if len(plans) <= 1:
        return last
    steps: list[dict] = []
    for plan in plans:
        scoped = execution_record(records, plan_id=plan.plan_id)
        if isinstance(scoped, ReplayRejection):
            raise IntegrityFailure(f"the stored log does not replay: {scoped.code.value}")
        steps.extend(json.loads(step.model_dump_json()) for step in scoped.steps)
    document = json.loads(last.model_dump_json())
    document["steps"] = steps
    return ExecutionRecord.model_validate_json(json.dumps(document))


def summary_of(mission: MissionRecord, records: tuple[EventRecord, ...]) -> MissionSummary:
    common = dict(
        mission_id=mission.mission_id, tenant_id=mission.tenant_id, created_by=mission.created_by, created_at=mission.created_at, goal=mission.spec.goal,
        run_status=mission.run_status, run_status_reason=mission.run_status_reason, last_sequence=len(records),
    )
    if not records:
        return MissionSummary(**common)
    record = execution_of(records)
    return MissionSummary(
        **common,
        mission_status=record.mission_status, status_reason=record.status_reason, failure_cause=record.failure_cause, verified=record.verified,
        plan_version=record.plan_version,
        counters=Counters(
            agent_calls_used=record.agent_calls_used, tool_calls_used=record.tool_calls_used, retries_used=record.retries_used, replans_used=record.replans_used,
            tokens_used=record.tokens_used, execution_time_used_ms=record.execution_time_used_ms,
        ),
    )


def result_of(records: tuple[EventRecord, ...], artifacts: ArtifactStore) -> MissionResult | None:
    """The result of a mission that has a terminal event, or ``None`` if it has not.

    The artifacts are the primary artifacts of the succeeded work steps that no other work step depends on in the last plan: its sinks, which the ``VERIFY`` step reads.
    """
    record = execution_of(records)
    if record.mission_status is MissionStatus.CREATED:
        return None
    work = [step for step in record.steps if step.kind is PlanStepKind.AGENT]
    depended_on = {dependency for step in work for dependency in step.depends_on}
    produced = []
    for step in work:
        if step.step_id in depended_on or step.result is None or step.result.status is not NodeStatus.SUCCEEDED or step.result.artifact is None:
            continue
        artifact = artifacts.get(record.execution_id, step.result.artifact)
        if artifact is not None:
            produced.append(ResultArtifact(ref=artifact.ref, content_type=artifact.content_type, content=artifact.content, source_refs=artifact.source_refs))
    verdict = next((step.verification for step in reversed(record.steps) if step.verification is not None), None)
    failure = MissionFailure(cause=record.failure_cause, reason=record.failure_reason) if record.failure_cause is not None else None
    return MissionResult(mission_status=record.mission_status, verified=record.verified, verdict=verdict, artifacts=tuple(produced), failure=failure)


def evidence_of(records: tuple[EventRecord, ...], artifacts: ArtifactStore) -> EvidenceView:
    record = whole_execution_record(records)
    audit = audit_evidence(record)
    seen: dict[ArtifactRef, None] = {}
    for trace in audit.traces:
        # Retrieved evidence (D-228), and — D-238 — the text of a web page a tool fetched that an answer cited, so a reader can see what was read. The audit is unchanged: a fetched page is still
        # ``not_evidence`` there (it was not retrieved from a knowledge base); only its text is shown. A supplied document can never take a ``tool:`` reference (spec.RESERVED_REF_PREFIXES).
        if trace.kind is CitationKind.RESOLVED or (trace.kind is CitationKind.NOT_EVIDENCE and parse_tool_document_ref(trace.ref) is not None):
            seen.setdefault(trace.ref, None)
    items = []
    for ref in seen:
        artifact = artifacts.get(record.execution_id, ref)
        if artifact is not None:
            items.append(EvidenceItem(ref=artifact.ref, content_type=artifact.content_type, content=artifact.content))
    return EvidenceView(audit=audit, evidence=tuple(items))

