"""The V1.4 application service (decisions.md D-229 to D-234; ``docs/13_product_backend.md``).

The layer between the HTTP boundary and the unchanged EIDOS runtime: it validates a mission specification, stores it, runs it on a bounded in-process runner through the full
``run_with_replanning`` driver, and answers every read by replaying the durable event log through the existing projections.

**It never mutates ``MissionState``.** The event log is the authority (D-157); persistence is durable storage behind ports, and ``run_status`` is an API-level lifecycle that never enters
``MissionState`` or the log. This package imports the EIDOS core and no FastAPI, no JWT library and no database driver; ``eidos.persistence`` implements its ports on PostgreSQL and
``eidos.api`` is the only HTTP boundary. Nothing in the core imports this package.
"""

from .ask import ASK_MAX_MODELS, AskedAnswer, AskRequest, AskResult
from .composition import AlwaysAdmit, Composition, InMemoryExperienceStore, KnowledgeProvision, PreparedRun, ToolProvision
from .config import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID, ApiCeilings, RunnerConfig, ServiceConfig, provisional_system_limits
from .durable import DurableEventLog, RunPersistence, WriteThroughArtifactStore
from .errors import (
    Busy,
    IdempotencyConflict,
    IntegrityFailure,
    InvalidRequest,
    InvalidSpec,
    NoEvents,
    NoTenantMembership,
    NotFinished,
    NotFound,
    NotStartable,
    PayloadTooLarge,
    ServiceError,
    StorageUnavailable,
    TenantRequired,
    TenantRunLimit,
)
from .memory import InMemoryStorage
from .ports import (
    ArtifactWrite,
    DuplicateIdempotencyKey,
    EventStore,
    Membership,
    MissionRecord,
    MissionRepository,
    Repositories,
    Role,
    RunStatus,
    SequenceConflict,
    StorageError,
    TenancyRepository,
    UserId,
    personal_workspace_id,
)
from .runner import INTERRUPTED_REASON, RunManager
from .service import MissionService, RequestContext
from .spec import MissionSpec, ReliabilitySpec, SuppliedDocument
from .user_models import ModelChoice, ModelFactory, RunModel, StartRequest, UserModels
from .views import (
    Counters,
    CreatedMission,
    EventsPage,
    EvidenceItem,
    EvidenceView,
    MissionFailure,
    MissionResult,
    MissionSummary,
    ResultArtifact,
    StartedMission,
)

__all__ = [
    "ANALYSIS_AGENT_ID", "ASK_MAX_MODELS", "INTERRUPTED_REASON", "RESEARCH_AGENT_ID", "AlwaysAdmit", "ApiCeilings", "ArtifactWrite", "AskRequest", "AskResult", "AskedAnswer", "Busy", "Composition", "Counters", "CreatedMission",
    "DuplicateIdempotencyKey", "DurableEventLog", "EventStore", "EventsPage", "EvidenceItem", "EvidenceView", "IdempotencyConflict", "InMemoryExperienceStore", "InMemoryStorage",
    "IntegrityFailure", "InvalidRequest", "InvalidSpec", "KnowledgeProvision", "Membership", "MissionFailure", "MissionRecord", "MissionRepository", "MissionResult", "MissionService",
    "MissionSpec", "MissionSummary", "ModelChoice", "ModelFactory", "NoEvents", "NoTenantMembership", "NotFinished", "NotFound", "NotStartable", "PayloadTooLarge", "PreparedRun", "ReliabilitySpec", "Repositories",
    "RequestContext", "ResultArtifact", "Role", "RunManager", "RunModel", "RunPersistence", "RunStatus", "RunnerConfig", "SequenceConflict", "ServiceConfig", "ServiceError", "StartedMission",
    "StartRequest", "StorageError", "StorageUnavailable", "SuppliedDocument", "TenancyRepository", "TenantRequired", "TenantRunLimit", "ToolProvision", "UserId", "UserModels", "WriteThroughArtifactStore", "personal_workspace_id", "provisional_system_limits",
]
