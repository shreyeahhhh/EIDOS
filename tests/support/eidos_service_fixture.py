"""Fixtures for the V1.4 service tests (decisions.md D-229 to D-234): a whole service over in-memory repositories and a scripted model.

Everything is real except the model (scripted, so nothing here is a measurement) and the storage (in memory; the same contract tests run against PostgreSQL when it is selected). Nothing here
touches the network, a database or a credential.
"""

from dataclasses import dataclass, field
from uuid import UUID

from eidos.contracts import AutonomyLevel, MissionId, RiskLevel, TenantId
from eidos.service import (
    ApiCeilings,
    Composition,
    InMemoryStorage,
    MissionService,
    MissionSpec,
    ReliabilitySpec,
    RequestContext,
    Role,
    RunManager,
    RunnerConfig,
    ServiceConfig,
    SuppliedDocument,
    UserId,
    provisional_system_limits,
)

from eidos_agents_factories import ScriptedModel, make_settings
from eidos_search_fixture import cite_every_document

TENANT_A = TenantId(UUID(int=0xA0A0))
TENANT_B = TenantId(UUID(int=0xB0B0))
ALICE = UserId(UUID(int=0x11))  # a member of tenant A
BOB = UserId(UUID(int=0x22))  # a member of tenant B
CAROL = UserId(UUID(int=0x33))  # a member of both
DAVE = UserId(UUID(int=0x44))  # a member of none


def make_spec(**overrides) -> MissionSpec:
    fields = dict(
        goal="Explain how the mission is verified",
        required_capabilities=("research", "cost"),
        risk_level=RiskLevel.LOW,
        autonomy_level=AutonomyLevel.SAFE_READ_ONLY,
        allowed_actions=(),
        reliability=ReliabilitySpec(min_quality=0.0, max_risk_level=RiskLevel.MEDIUM, min_independent_evidence=2),
        supplied_documents=tuple(SuppliedDocument(ref=f"doc:{n}", content_type="text/plain", content=f"Source document {n}.") for n in (1, 2, 3)),
    )
    fields.update(overrides)
    return MissionSpec(**fields)


@dataclass
class ServiceRig:
    service: MissionService
    storage: InMemoryStorage
    runner: RunManager
    model: ScriptedModel
    composition: Composition
    config: ServiceConfig
    contexts: dict = field(default_factory=dict)

    def context(self, name: str = "alice") -> RequestContext:
        return self.contexts[name]

    def run_to_the_end(self, context: RequestContext, mission_id: MissionId, *, timeout: float = 60.0):
        self.service.start_mission(context, mission_id)
        assert self.runner.wait_idle(timeout), "the run did not finish inside the bound"
        return self.service.get_mission(context, mission_id)


def make_rig(*, respond=cite_every_document, config: ServiceConfig | None = None, runner: RunnerConfig | None = None, ceilings: ApiCeilings | None = None, knowledge=None,
             sleep=lambda seconds: None, storage: InMemoryStorage | None = None, events=None, allowed_actions=frozenset({"read_documents"})) -> ServiceRig:
    storage = storage if storage is not None else InMemoryStorage()
    for tenant in (TENANT_A, TENANT_B):
        try:
            storage.add_tenant(tenant, "tenant")
        except ValueError:
            pass
    for tenant, user, role in ((TENANT_A, ALICE, Role.OWNER), (TENANT_B, BOB, Role.MEMBER), (TENANT_A, CAROL, Role.MEMBER), (TENANT_B, CAROL, Role.MEMBER)):
        try:
            storage.add_member(tenant, user, role)
        except ValueError:  # a rig built over storage that already holds them
            pass
    config = config or ServiceConfig(
        limits=provisional_system_limits(), model_settings=make_settings(), allowed_actions=allowed_actions,
        ceilings=ceilings or ApiCeilings(), runner=runner or RunnerConfig(flush_backoff_seconds=0.0),
    )
    model = ScriptedModel(respond)
    repositories = storage.repositories()
    if events is not None:
        from dataclasses import replace

        repositories = replace(repositories, events=events)
    composition = Composition(config=config, model=model, events=repositories.events, knowledge=knowledge, sleep=sleep)
    manager = RunManager(repositories=repositories, composition=composition, config=config.runner, sleep=sleep)
    service = MissionService(repositories=repositories, runner=manager, composition=composition, config=config)
    rig = ServiceRig(service=service, storage=storage, runner=manager, model=model, composition=composition, config=config)
    rig.contexts = {
        "alice": RequestContext(user_id=ALICE, tenant_id=TENANT_A, role=Role.OWNER),
        "bob": RequestContext(user_id=BOB, tenant_id=TENANT_B, role=Role.MEMBER),
    }
    return rig
