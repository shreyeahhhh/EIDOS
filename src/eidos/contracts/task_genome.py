"""TaskGenome — handoff §6.

decisions.md: D-013 (disjoint from ReliabilityContract; references it
rather than copying its thresholds), D-014 (autonomy_level uses handoff
§29's 0-4 scale), D-019/D-033/D-079 (tenant_id, root-only, single-tenant
default), D-031 (no evidence_requirements field in V0.1), D-045 (the
contract reference is required), D-056 (RiskLevel scale), D-068 (mission-
owned but does NOT carry mission_id — ownership is by containment in
MissionState), D-077 (required/optional split), D-080 (CapabilityId,
ActionId), D-089 (references the contract by reliability_contract_id, not
by embedding it), D-094 (allowed_actions are opaque strings), D-099
(information_dependencies are opaque strings, optional).

goal's non-empty constraint is a domain-level minimum approved alongside
this implementation slice, not a handoff-stated rule.
"""

from pydantic import Field

from ._base import EidosModel
from .enums import AutonomyLevel, RiskLevel
from .identifiers import (
    ActionId,
    CapabilityId,
    DEFAULT_TENANT_ID,
    ReliabilityContractId,
    TenantId,
)


class TaskGenome(EidosModel):
    tenant_id: TenantId = Field(default=DEFAULT_TENANT_ID)

    goal: str = Field(min_length=1)
    required_capabilities: tuple[CapabilityId, ...]
    information_dependencies: tuple[str, ...] = ()
    risk_level: RiskLevel
    autonomy_level: AutonomyLevel
    allowed_actions: tuple[ActionId, ...]

    reliability_contract_id: ReliabilityContractId
