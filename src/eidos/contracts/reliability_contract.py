"""ReliabilityContract — handoff §30.

decisions.md: D-009 (bounds split — this model carries mission execution
budgets and the non-budget acceptance thresholds; runtime shape limits are
system-level and not here), D-016 (min_quality is a plain scalar
requirement, not an estimate), D-042 (the six-field budget group), D-056
(RiskLevel scale), D-065 (all six budgets optional; system-ceiling fallback
is a V0.2 concern, not modelled here), D-069 (no approval-clause field),
D-073 (the three non-budget fields are required), D-078 (units: integer
milliseconds, integer token counts), D-089 (contract_id, since TaskGenome
references this object by identifier).

Numeric ranges (min_quality in [0.0, 1.0]; min_independent_evidence and
every present budget field >= 0) are domain-level minimums approved
alongside this implementation slice; they are not the future quality-
scoring function (D-015, still Open) and do not assign any numerical
execution ceiling (D-046, still Open, defers actual ceiling values to V0.2).
"""

from pydantic import Field

from ._base import EidosModel
from .enums import RiskLevel
from .identifiers import DEFAULT_TENANT_ID, ReliabilityContractId, TenantId


class ReliabilityContract(EidosModel):
    tenant_id: TenantId = Field(default=DEFAULT_TENANT_ID)
    contract_id: ReliabilityContractId

    min_quality: float = Field(ge=0.0, le=1.0)
    max_risk_level: RiskLevel
    min_independent_evidence: int = Field(ge=0)

    max_retries: int | None = Field(default=None, ge=0)
    max_replans: int | None = Field(default=None, ge=0)
    max_agent_calls: int | None = Field(default=None, ge=0)
    max_tool_calls: int | None = Field(default=None, ge=0)
    max_execution_time: int | None = Field(default=None, ge=0)  # milliseconds (D-078)
    max_tokens: int | None = Field(default=None, ge=0)
