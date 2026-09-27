"""Helpers shared by the storage contract tests and the service tests (V1.4-B): a stored mission record, a real valid log for it, and the commit call."""

from datetime import datetime, timezone
from uuid import uuid4

from eidos.agents import Artifact
from eidos.contracts import ArtifactRef, EventId, ExecutionId, MissionId, ReliabilityContractId
from eidos.service import MissionRecord, RunStatus
from eidos.service.spec import contract_and_genome, without_documents
from eidos.state import EventLog, EventProposal, MissionCreatedPayload, PlanGeneratedPayload, PlanRejectedPayload, PlanRejectionStage, RejectionReason

from eidos_factories import make_plan
from eidos_service_fixture import ALICE, TENANT_A, make_spec

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_record(tenant=TENANT_A, *, key=None, mission_id=None, **overrides) -> MissionRecord:
    fields = dict(
        mission_id=MissionId(mission_id or uuid4()), tenant_id=tenant, execution_id=ExecutionId(uuid4()), contract_id=ReliabilityContractId(uuid4()), created_by=ALICE, created_at=NOW,
        spec=without_documents(make_spec()), spec_sha256="a" * 64, idempotency_key=key, run_status=RunStatus.CREATED, run_updated_at=NOW,
    )
    fields.update(overrides)
    return MissionRecord(**fields)


def artifact(ref, content="text", *sources) -> Artifact:
    return Artifact(ref=ArtifactRef(ref), content_type="text/plain", content=content, source_refs=tuple(ArtifactRef(s) for s in sources))


def events_for(record: MissionRecord, count: int = 3):
    """A real, valid log of ``count`` events for this mission: created, a plan generated, that plan rejected."""
    contract, genome = contract_and_genome(record.spec, tenant_id=record.tenant_id, contract_id=record.contract_id)
    plan = make_plan(tenant_id=record.tenant_id, mission_id=record.mission_id)
    payloads = [
        MissionCreatedPayload(task_genome=genome, reliability_contract=contract, execution_id=record.execution_id),
        PlanGeneratedPayload(plan=plan),
        PlanRejectedPayload(plan_id=plan.plan_id, stage=PlanRejectionStage.VALIDATION, reasons=(RejectionReason(code="x", message="y"),)),
    ][:count]
    log = EventLog()
    for payload in payloads:
        proposal = EventProposal(event_id=EventId(uuid4()), tenant_id=record.tenant_id, mission_id=record.mission_id, occurred_at=NOW, recorded_at=NOW, payload=payload)
        assert log.accept(proposal).applied
    return log.records


def commit(repositories, record, records, *, expected=0, artifacts=()):
    return repositories.events.commit(
        tenant_id=record.tenant_id, mission_id=record.mission_id, execution_id=record.execution_id, expected_last_sequence=expected, artifacts=tuple(artifacts), events=tuple(records)
    )
