"""The mission specification the API accepts, and its mapping to the existing EIDOS contracts (decisions.md D-232; invariant 3; ``docs/13`` section 4).

**A ``MissionSpec`` is explicit and structured. No component derives a ``TaskGenome`` or a ``ReliabilityContract`` from anything, and no model has any part in creating one.**
The field names are the contracts' own, so the mapping is one to one and there is no parallel product schema: a ``MissionSpec`` is a ``TaskGenome`` and a
``ReliabilityContract`` without the identifiers the server assigns (``tenant_id``, ``reliability_contract_id`` / ``contract_id``), plus optional supplied documents.
``tests/unit/service`` keeps the two field lists equal to the contracts' own, so they cannot drift.

Validation checks the server ceilings and rejects; it never clamps (D-009). The ceilings are provisional API safety ceilings and are not budget enforcement
(``config.py``).

**The ``MissionState`` carrier.** ``run_with_replanning`` reads a mission's genome, contract and identifiers from a ``MissionState``. Only the reducer constructs one (a guard
enforces it), so ``initial_state`` folds a ``MISSION_CREATED`` proposal through a throwaway ``EventLog`` and returns the state the reducer built. That state is a carrier
only: the run records its own ``MISSION_CREATED`` in the real log (D-201: before a run the mission does not exist for the log).
"""

import hashlib
import re
from collections.abc import Iterable
from datetime import datetime

from pydantic import Field

from eidos.agents import SUPPORTED_CONTENT_TYPES, Artifact
from eidos.contracts import (
    ActionId,
    ArtifactRef,
    AutonomyLevel,
    CapabilityId,
    EidosModel,
    EventId,
    ExecutionId,
    MissionId,
    MissionState,
    ReliabilityContract,
    ReliabilityContractId,
    RiskLevel,
    TaskGenome,
    TenantId,
)
from eidos.state import EventLog, EventProposal, MissionCreatedPayload
from eidos.validation import SystemLimits

from .config import ApiCeilings
from .errors import InvalidSpec

RESERVED_REF_PREFIXES = ("artifact:", "evidence:", "tool:")  # the namespaces the runtime writes its own artifacts under (a supplied ref there would collide with a step or a gate)
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/-]{0,127}$")  # a reference a model can cite as [[ref]]
_BUDGETS = ("max_retries", "max_replans", "max_agent_calls", "max_tool_calls", "max_execution_time", "max_tokens")


class SuppliedDocument(EidosModel):
    """A document the caller places before the run (D-145's supplied artifact)."""

    ref: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    content: str


class ReliabilitySpec(EidosModel):
    """The ``ReliabilityContract`` without its identifiers. ``max_execution_time`` is in milliseconds, as in the contract (D-078)."""

    min_quality: float = Field(ge=0.0, le=1.0)
    max_risk_level: RiskLevel
    min_independent_evidence: int = Field(ge=0)
    max_retries: int | None = Field(default=None, ge=0)
    max_replans: int | None = Field(default=None, ge=0)
    max_agent_calls: int | None = Field(default=None, ge=0)
    max_tool_calls: int | None = Field(default=None, ge=0)
    max_execution_time: int | None = Field(default=None, ge=0)
    max_tokens: int | None = Field(default=None, ge=0)


class MissionSpec(EidosModel):
    """The whole request to create a mission. ``tenant_id`` is not a field: a client-supplied tenant is refused as an unknown field (D-233)."""

    goal: str = Field(min_length=1)
    required_capabilities: tuple[CapabilityId, ...]
    information_dependencies: tuple[str, ...] = ()
    risk_level: RiskLevel
    autonomy_level: AutonomyLevel
    allowed_actions: tuple[ActionId, ...]
    reliability: ReliabilitySpec
    supplied_documents: tuple[SuppliedDocument, ...] = ()


def _problem(field: str, message: str) -> dict:
    return {"field": field, "message": message}


def validate_spec(spec: MissionSpec, *, ceilings: ApiCeilings, allowed_actions: frozenset[str], capabilities: Iterable[str], limits: SystemLimits) -> None:
    """Raise ``InvalidSpec`` naming every field that is over a ceiling or outside what the server serves. Never clamps."""
    problems: list[dict] = []
    known = tuple(sorted(str(name) for name in capabilities))

    if not spec.goal.strip():
        problems.append(_problem("goal", "the goal is empty"))
    if len(spec.goal) > ceilings.max_goal_chars:
        problems.append(_problem("goal", f"the goal is {len(spec.goal)} characters; the ceiling is {ceilings.max_goal_chars}"))

    capability_names = [str(name) for name in spec.required_capabilities]
    if not capability_names:
        problems.append(_problem("required_capabilities", "at least one capability is required"))
    if len(set(capability_names)) != len(capability_names):
        problems.append(_problem("required_capabilities", "a capability is listed more than once"))
    unknown = sorted({name for name in capability_names if name not in known})
    if unknown:
        problems.append(_problem("required_capabilities", f"not served here: {', '.join(unknown)}; served: {', '.join(known)}"))

    if len(spec.information_dependencies) > ceilings.max_information_dependencies:
        problems.append(_problem("information_dependencies", f"more than {ceilings.max_information_dependencies} entries"))

    actions = [str(name) for name in spec.allowed_actions]
    if len(actions) > ceilings.max_allowed_actions:
        problems.append(_problem("allowed_actions", f"more than {ceilings.max_allowed_actions} entries"))
    if len(set(actions)) != len(actions):
        problems.append(_problem("allowed_actions", "an action is listed more than once"))
    not_allowed = sorted({name for name in actions if name not in allowed_actions})
    if not_allowed:
        problems.append(_problem("allowed_actions", f"not permitted by this server: {', '.join(not_allowed)}"))

    if int(spec.autonomy_level) > ceilings.max_autonomy_level:
        problems.append(_problem("autonomy_level", f"level {int(spec.autonomy_level)} is above the ceiling {ceilings.max_autonomy_level}"))

    for name in _BUDGETS:
        value = getattr(spec.reliability, name)
        if value is not None and value > getattr(limits, name):
            problems.append(_problem(f"reliability.{name}", f"{value} is above the system ceiling {getattr(limits, name)}"))

    problems.extend(_document_problems(spec, ceilings))
    if problems:
        raise InvalidSpec("the mission specification is not acceptable", details=tuple(problems))


def _document_problems(spec: MissionSpec, ceilings: ApiCeilings) -> list[dict]:
    problems: list[dict] = []
    documents = spec.supplied_documents
    if len(documents) > ceilings.max_supplied_documents:
        problems.append(_problem("supplied_documents", f"{len(documents)} documents; the ceiling is {ceilings.max_supplied_documents}"))
    total = 0
    seen: set[str] = set()
    for index, document in enumerate(documents):
        where = f"supplied_documents[{index}]"
        size = len(document.content.encode("utf-8"))
        total += size
        if not _REF.match(document.ref):
            problems.append(_problem(where + ".ref", "a reference starts with a letter or digit and holds only letters, digits and : . _ / - (at most 128)"))
        elif document.ref.startswith(RESERVED_REF_PREFIXES):
            problems.append(_problem(where + ".ref", f"the prefixes {', '.join(RESERVED_REF_PREFIXES)} are reserved for what a run produces"))
        if document.ref in seen:
            problems.append(_problem(where + ".ref", "a reference is used more than once"))
        seen.add(document.ref)
        if document.content_type not in SUPPORTED_CONTENT_TYPES:
            problems.append(_problem(where + ".content_type", f"supported: {', '.join(SUPPORTED_CONTENT_TYPES)}"))
        if not document.content.strip():
            problems.append(_problem(where + ".content", "the document is empty"))
        if size > ceilings.max_document_bytes:
            problems.append(_problem(where + ".content", f"{size} bytes; the ceiling is {ceilings.max_document_bytes}"))
    if total > ceilings.max_total_document_bytes:
        problems.append(_problem("supplied_documents", f"{total} bytes in all; the ceiling is {ceilings.max_total_document_bytes}"))
    return problems


def spec_digest(spec: MissionSpec) -> str:
    """The digest of the whole request, documents included: what an idempotency key is compared against."""
    return hashlib.sha256(spec.model_dump_json().encode("utf-8")).hexdigest()


def without_documents(spec: MissionSpec) -> MissionSpec:
    """The spec as it is stored in ``missions.spec``: the documents are held as supplied artifacts."""
    return MissionSpec(
        goal=spec.goal, required_capabilities=spec.required_capabilities, information_dependencies=spec.information_dependencies, risk_level=spec.risk_level,
        autonomy_level=spec.autonomy_level, allowed_actions=spec.allowed_actions, reliability=spec.reliability, supplied_documents=(),
    )


def documents_of(spec: MissionSpec) -> tuple[Artifact, ...]:
    return tuple(Artifact(ref=ArtifactRef(document.ref), content_type=document.content_type, content=document.content) for document in spec.supplied_documents)


def contract_and_genome(spec: MissionSpec, *, tenant_id: TenantId, contract_id: ReliabilityContractId) -> tuple[ReliabilityContract, TaskGenome]:
    """The two existing contracts a spec maps onto, field for field. The server supplies the tenant and the contract's identifier."""
    reliability = spec.reliability
    contract = ReliabilityContract(
        tenant_id=tenant_id, contract_id=contract_id, min_quality=reliability.min_quality, max_risk_level=reliability.max_risk_level,
        min_independent_evidence=reliability.min_independent_evidence, max_retries=reliability.max_retries, max_replans=reliability.max_replans,
        max_agent_calls=reliability.max_agent_calls, max_tool_calls=reliability.max_tool_calls, max_execution_time=reliability.max_execution_time,
        max_tokens=reliability.max_tokens,
    )
    genome = TaskGenome(
        tenant_id=tenant_id, goal=spec.goal, required_capabilities=spec.required_capabilities, information_dependencies=spec.information_dependencies,
        risk_level=spec.risk_level, autonomy_level=spec.autonomy_level, allowed_actions=spec.allowed_actions, reliability_contract_id=contract_id,
    )
    return contract, genome


def initial_state(
    genome: TaskGenome, contract: ReliabilityContract, *, tenant_id: TenantId, mission_id: MissionId, execution_id: ExecutionId, at: datetime, event_id: EventId
) -> MissionState:
    """The state the reducer builds from ``MISSION_CREATED``, through a throwaway log. It is only the carrier ``run_with_replanning`` reads identity from."""
    result = EventLog().accept(
        EventProposal(
            event_id=event_id, tenant_id=tenant_id, mission_id=mission_id, occurred_at=at, recorded_at=at,
            payload=MissionCreatedPayload(task_genome=genome, reliability_contract=contract, execution_id=execution_id),
        )
    )
    if not result.applied or result.state is None:
        raise ValueError(f"the reducer refused a MISSION_CREATED built from a validated spec: {result.reason}")
    return result.state
