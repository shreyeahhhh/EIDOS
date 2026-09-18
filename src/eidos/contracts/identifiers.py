"""Opaque identifier types for EIDOS V0.1 contracts.

decisions.md D-053: identifiers are opaque values represented through
distinct per-kind types, so that (for example) a PlanId can never be passed
where a MissionId is expected. By default they are UUID-backed.

Five kinds are exempt from the UUID-backed default (docs/03_architecture.md
"Identifier exemptions from D-053's UUID rule") because they are either
authored by the planner inside the Plan DSL or assigned by an external
system that EIDOS does not control:

  StepId                    D-092 — planner-authored, unique within one Plan
  CapabilityId, ActionId    D-080 — plain names emitted in the Plan DSL
  ArtifactRef               D-098 — produced by remote agents
  A2ATaskId, A2AContextId   D-095 — assigned by the remote A2A system

decisions.md D-053 uses ``TenantId`` as UUID-backed and does not name a
dedicated wrapper for the two A2A identifiers; A2ATaskId/A2AContextId are
defined here purely for consistency with every other identifier in this
module (CLAUDE.md §8: no untyped value crosses a module boundary). Nothing
in decisions.md requires this extension, and a plain ``str`` would be an
equally faithful reading of D-095.

typing.NewType is used rather than a RootModel wrapper (decisions.md A2,
approved 2026-09-18): this gives static (mypy-level) distinction with no
runtime wrapper overhead. It does NOT give runtime distinctness — a
MissionId and a PlanId are the same UUID object at runtime, and nothing
here stops one being passed where the other is typed. Where a mismatch
would be a real bug (TaskGenome's contract reference vs. the contract it
sits beside in MissionState, a Plan's mission_id vs. its containing
MissionState), that is caught by the explicit cross-object validators on
MissionState instead — see mission_state.py.
"""

from typing import NewType
from uuid import UUID

# --- UUID-backed (decisions.md D-053 default) ---------------------------

TenantId = NewType("TenantId", UUID)
MissionId = NewType("MissionId", UUID)
ExecutionId = NewType("ExecutionId", UUID)
PlanId = NewType("PlanId", UUID)
EventId = NewType("EventId", UUID)
AgentId = NewType("AgentId", UUID)
ReliabilityContractId = NewType("ReliabilityContractId", UUID)

# --- String-backed (exempt from the UUID-backed default) ----------------

StepId = NewType("StepId", str)
CapabilityId = NewType("CapabilityId", str)
ActionId = NewType("ActionId", str)
ArtifactRef = NewType("ArtifactRef", str)
A2ATaskId = NewType("A2ATaskId", str)
A2AContextId = NewType("A2AContextId", str)

# --- Single-tenant placeholder (decisions.md D-079) ----------------------
#
# D-079: "tenant_id is always present and non-null on root models... a
# fixed default TenantId is supplied by the single-tenant context... The
# default carries no security meaning."
#
# The literal value is explicitly NOT settled by any decision — D-032
# ("The literal default value of tenant_id") remains Open and states this
# "does not block the model definitions — only the constant." The nil UUID
# is used here as an unmistakable placeholder sentinel pending D-032.
# CHANGE THIS when D-032 is resolved; do not treat this value as meaningful.

DEFAULT_TENANT_ID: TenantId = TenantId(UUID(int=0))
