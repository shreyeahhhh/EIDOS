"""The application service: the use cases behind the API (decisions.md D-230 to D-234; ``docs/13`` sections 5 to 8).

``MissionService`` is the only thing the HTTP layer calls. It reads by replay and writes by starting a run: **it never mutates ``MissionState``, holds none, and constructs none.** Every method
takes a ``RequestContext`` (the authenticated user, the resolved tenant and the role) and every repository call carries the tenant, so a resource of another tenant is indistinguishable from
one that does not exist (D-233). A storage fault becomes ``StorageUnavailable`` and a stored log that does not replay becomes ``IntegrityFailure``; neither is ever a mission outcome.
"""

from dataclasses import dataclass
from uuid import UUID, uuid4

from pydantic import ValidationError

from eidos.contracts import ExecutionId, MissionId, ReliabilityContractId, TenantId
from eidos.recording import Clock, SystemClock
from eidos.state import ExecutionRecord

from .composition import Composition
from .config import ServiceConfig
from .errors import (
    IdempotencyConflict,
    InvalidRequest,
    InvalidSpec,
    NoEvents,
    NoTenantMembership,
    NotFinished,
    NotFound,
    StorageUnavailable,
    TenantRequired,
)
from .ports import DuplicateIdempotencyKey, MissionRecord, Repositories, Role, RunStatus, StorageError, UserId
from .runner import RunManager
from .spec import MissionSpec, contract_and_genome, documents_of, spec_digest, validate_spec, without_documents
from .views import (
    CreatedMission,
    EventsPage,
    EvidenceView,
    MissionResult,
    MissionSummary,
    StartedMission,
    evidence_of,
    execution_of,
    result_of,
    summary_of,
)


PERSONAL_WORKSPACE_NAME = "Personal workspace"


@dataclass(frozen=True, slots=True)
class RequestContext:
    user_id: UserId
    tenant_id: TenantId
    role: Role


class MissionService:
    def __init__(self, *, repositories: Repositories, runner: RunManager, composition: Composition, config: ServiceConfig, clock: Clock | None = None) -> None:
        self._repositories, self._runner, self._composition, self._config = repositories, runner, composition, config
        self._clock = clock if clock is not None else SystemClock()

    def startup(self) -> int:
        """Recover runs a previous process left active (they become ``interrupted``; no event is written). Call once before serving."""
        return self._runner.recover()

    def shutdown(self) -> None:
        self._runner.shutdown()

    # --- identity ------------------------------------------------------------------------------------------------------------------

    def resolve_context(self, user_id: UserId, requested_tenant: str | None) -> RequestContext:
        try:
            memberships = self._repositories.tenancy.memberships_of(user_id)
        except StorageError as error:
            raise StorageUnavailable(str(error)) from error
        if not memberships and self._config.auto_provision_workspaces:  # D-237: only a user with no tenant at all; anyone who already has one keeps exactly those
            try:
                memberships = self._repositories.tenancy.provision_personal_workspace(user_id, PERSONAL_WORKSPACE_NAME)
            except StorageError as error:
                raise StorageUnavailable(str(error)) from error
        if not memberships:
            raise NoTenantMembership("this user belongs to no tenant")
        if requested_tenant is not None:
            try:
                wanted = TenantId(UUID(requested_tenant))
            except ValueError:
                raise NotFound("no such tenant") from None
            chosen = next((m for m in memberships if m.tenant_id == wanted), None)
            if chosen is None:
                raise NotFound("no such tenant")  # never says whether the tenant exists
        elif len(memberships) == 1:
            chosen = memberships[0]
        else:
            raise TenantRequired("this user belongs to several tenants: name one in X-Tenant-Id")
        return RequestContext(user_id=user_id, tenant_id=chosen.tenant_id, role=chosen.role)

    # --- create --------------------------------------------------------------------------------------------------------------------

    def create_mission(self, context: RequestContext, spec: MissionSpec, idempotency_key: str | None = None) -> tuple[CreatedMission, bool]:
        """Validate and store a mission; no event is written. Returns the mission and whether it was newly created (a repeated idempotency key returns the existing one)."""
        if idempotency_key is not None and not 1 <= len(idempotency_key) <= 128:
            raise InvalidRequest("the Idempotency-Key is 1 to 128 characters")
        validate_spec(
            spec, ceilings=self._config.ceilings, allowed_actions=self._config.allowed_actions, capabilities=self._composition.capabilities, limits=self._config.limits
        )
        digest = spec_digest(spec)
        if idempotency_key is not None:
            existing = self._find_key(context.tenant_id, idempotency_key)
            if existing is not None:
                return self._repeat(existing, digest), False
        now = self._clock.now()
        mission_id, execution_id, contract_id = MissionId(uuid4()), ExecutionId(uuid4()), ReliabilityContractId(uuid4())
        try:
            contract_and_genome(spec, tenant_id=context.tenant_id, contract_id=contract_id)  # the existing contracts have the last word on a spec
            record = MissionRecord(
                mission_id=mission_id, tenant_id=context.tenant_id, execution_id=execution_id, contract_id=contract_id, created_by=context.user_id, created_at=now,
                spec=without_documents(spec), spec_sha256=digest, idempotency_key=idempotency_key, run_status=RunStatus.CREATED, run_updated_at=now,
            )
        except ValidationError as error:
            raise InvalidSpec("the mission specification is not acceptable", details=tuple({"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in error.errors())) from error
        try:
            self._repositories.missions.create(record, documents_of(spec))
        except DuplicateIdempotencyKey:
            existing = self._find_key(context.tenant_id, idempotency_key)
            if existing is None:
                raise
            return self._repeat(existing, digest), False
        except StorageError as error:
            raise StorageUnavailable(str(error)) from error
        return CreatedMission(mission_id=mission_id, run_status=RunStatus.CREATED, created_at=now), True

    def _find_key(self, tenant_id: TenantId, key: str) -> MissionRecord | None:
        try:
            return self._repositories.missions.find_by_idempotency_key(tenant_id, key)
        except StorageError as error:
            raise StorageUnavailable(str(error)) from error

    @staticmethod
    def _repeat(existing: MissionRecord, digest: str) -> CreatedMission:
        if existing.spec_sha256 != digest:
            raise IdempotencyConflict("this Idempotency-Key was used for a different request")
        return CreatedMission(mission_id=existing.mission_id, run_status=existing.run_status, created_at=existing.created_at)

    # --- start ---------------------------------------------------------------------------------------------------------------------

    def start_mission(self, context: RequestContext, mission_id: MissionId) -> StartedMission:
        self._mission(context, mission_id)
        self._runner.start(context.tenant_id, mission_id)
        return StartedMission(mission_id=mission_id, run_status=RunStatus.QUEUED)

    # --- reads ---------------------------------------------------------------------------------------------------------------------

    def get_mission(self, context: RequestContext, mission_id: MissionId) -> MissionSummary:
        mission = self._mission(context, mission_id)
        return summary_of(mission, self._records(context, mission_id))

    def execution(self, context: RequestContext, mission_id: MissionId) -> ExecutionRecord:
        self._mission(context, mission_id)
        records = self._records(context, mission_id)
        if not records:
            raise NoEvents("the mission has no recorded event yet")
        return execution_of(records)

    def events(self, context: RequestContext, mission_id: MissionId, *, after: int = 0, limit: int | None = None) -> EventsPage:
        mission = self._mission(context, mission_id)
        ceilings = self._config.ceilings
        limit = ceilings.events_page_default if limit is None else limit
        if after < 0 or not 1 <= limit <= ceilings.events_page_max:
            raise InvalidRequest(f"after is at least 0 and limit is 1 to {ceilings.events_page_max}")
        try:
            page = self._repositories.events.read(context.tenant_id, mission_id, after=after, limit=limit)
        except StorageError as error:
            raise StorageUnavailable(str(error)) from error
        next_after = page[-1].event.sequence if page else after
        return EventsPage(events=page, last_sequence=max(mission.last_sequence, next_after), next_after=next_after)

    def result(self, context: RequestContext, mission_id: MissionId) -> MissionResult:
        mission = self._mission(context, mission_id)
        records = self._records(context, mission_id)
        produced = result_of(records, self._artifacts(context, mission)) if records else None
        if produced is None:
            raise NotFinished("the mission has no terminal event yet")
        return produced

    def evidence(self, context: RequestContext, mission_id: MissionId) -> EvidenceView:
        mission = self._mission(context, mission_id)
        records = self._records(context, mission_id)
        if not records:
            raise NoEvents("the mission has no recorded event yet")
        return evidence_of(records, self._artifacts(context, mission))

    # --- helpers -------------------------------------------------------------------------------------------------------------------

    def _mission(self, context: RequestContext, mission_id: MissionId) -> MissionRecord:
        try:
            mission = self._repositories.missions.get(context.tenant_id, mission_id)
        except StorageError as error:
            raise StorageUnavailable(str(error)) from error
        if mission is None:
            raise NotFound("no such mission")
        return mission

    def _records(self, context: RequestContext, mission_id: MissionId):
        try:
            return self._repositories.events.read(context.tenant_id, mission_id)
        except StorageError as error:
            raise StorageUnavailable(str(error)) from error

    def _artifacts(self, context: RequestContext, mission: MissionRecord):
        return self._repositories.artifacts(context.tenant_id)

