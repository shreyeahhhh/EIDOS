"""Closed value sets for EIDOS V0.1 contracts.

Every enum here is a settled decision. None may gain a member without a new
entry in decisions.md (CLAUDE.md §2: "Any change touching an invariant
requires explicit human approval and an entry in decisions.md" — these
enums encode invariants 9, 11, 13 and 14 at the type level).
"""

from enum import IntEnum, StrEnum


class RiskLevel(StrEnum):
    """decisions.md D-056: closed, ordinal, word-valued three-level scale.

    Used by TaskGenome.risk_level (assessed/intrinsic risk, D-030) and by
    ReliabilityContract.max_risk_level (tolerated risk, D-030). Not reused
    for handoff §40's action risk or §28's tool risk (D-051).
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AutonomyLevel(IntEnum):
    """handoff §29; decisions.md D-014. TaskGenome.autonomy_level's scale.

    Level 3's relationship to the other levels (ordinal point vs. a gate
    that cuts across them) is Open under D-060 and is not encoded here.
    """

    RECOMMEND_ONLY = 0
    SAFE_READ_ONLY = 1
    REVERSIBLE = 2
    HUMAN_APPROVAL_REQUIRED = 3
    AUTHORIZED_AUTONOMOUS = 4


class MissionStatus(StrEnum):
    """decisions.md D-052: exactly the four handoff-supported states.

    PLANNING and EXECUTING are deliberately absent — see D-052's rationale.
    """

    CREATED = "created"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class PlanStepKind(StrEnum):
    """decisions.md D-049, D-050, D-101: the canonical V0.1 kind set.

    AGENT is the sole capability-bearing (work) kind (D-101). The remaining
    six are control-flow kinds and never carry a capability (D-049).
    SEQUENTIAL and PARALLEL are not canonical values (D-050) — ordering and
    parallelism are expressed by PlanStep.depends_on edges instead.

    The mixed case (lowercase "agent", uppercase everything else) is
    intentional, not an oversight: it follows handoff §13's own example
    verbatim, which mixes the two the same way (D-101's rationale note).
    """

    AGENT = "agent"
    ROUTE = "ROUTE"
    VERIFY = "VERIFY"
    RETRY = "RETRY"
    REPLAN = "REPLAN"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    TERMINATE = "TERMINATE"


class MissionEventType(StrEnum):
    """decisions.md D-090: exactly the thirteen event types named in §33.

    Several of these (the A2A, MCP and RAG types) cannot occur in V0.1,
    since those subsystems do not exist yet. D-090 chose to define the
    full §33 vocabulary regardless, rather than trim it to what V0.1 can
    reach — see D-090's rationale for why this differs from D-052.
    """

    MISSION_CREATED = "MISSION_CREATED"
    PLAN_GENERATED = "PLAN_GENERATED"
    PLAN_REJECTED = "PLAN_REJECTED"
    PLAN_COMPILED = "PLAN_COMPILED"
    A2A_TASK_STARTED = "A2A_TASK_STARTED"
    A2A_TASK_COMPLETED = "A2A_TASK_COMPLETED"
    MCP_TOOL_CALLED = "MCP_TOOL_CALLED"
    RAG_SEARCH = "RAG_SEARCH"
    EVIDENCE_REJECTED = "EVIDENCE_REJECTED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    REPLAN_TRIGGERED = "REPLAN_TRIGGERED"
    MISSION_COMPLETED = "MISSION_COMPLETED"
    MISSION_FAILED = "MISSION_FAILED"
