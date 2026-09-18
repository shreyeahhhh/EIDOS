"""Closed value sets (decisions.md D-014, D-049, D-050, D-052, D-056, D-090, D-101)."""

from eidos.contracts import (
    AutonomyLevel,
    MissionEventType,
    MissionStatus,
    PlanStepKind,
    RiskLevel,
)


def test_risk_level_is_exactly_low_medium_high():
    assert {member.value for member in RiskLevel} == {"low", "medium", "high"}


def test_autonomy_level_is_exactly_the_five_29_levels():
    assert {member.value for member in AutonomyLevel} == {0, 1, 2, 3, 4}
    assert AutonomyLevel.RECOMMEND_ONLY == 0
    assert AutonomyLevel.SAFE_READ_ONLY == 1
    assert AutonomyLevel.REVERSIBLE == 2
    assert AutonomyLevel.HUMAN_APPROVAL_REQUIRED == 3
    assert AutonomyLevel.AUTHORIZED_AUTONOMOUS == 4


def test_mission_status_is_exactly_the_four_handoff_supported_states():
    assert {member.value for member in MissionStatus} == {
        "created",
        "completed",
        "failed",
        "paused",
    }
    # decisions.md D-052: PLANNING and EXECUTING are deliberately absent.
    assert not hasattr(MissionStatus, "PLANNING")
    assert not hasattr(MissionStatus, "EXECUTING")


def test_plan_step_kind_is_exactly_the_canonical_v01_set():
    assert {member.value for member in PlanStepKind} == {
        "agent",
        "ROUTE",
        "VERIFY",
        "RETRY",
        "REPLAN",
        "HUMAN_APPROVAL",
        "TERMINATE",
    }
    # decisions.md D-050: SEQUENTIAL and PARALLEL are not canonical values.
    assert not hasattr(PlanStepKind, "SEQUENTIAL")
    assert not hasattr(PlanStepKind, "PARALLEL")


def test_plan_step_kind_agent_is_lowercase_and_control_kinds_are_uppercase():
    # decisions.md D-101: the mixed case is intentional, following handoff
    # §13's own example verbatim.
    assert PlanStepKind.AGENT.value == "agent"
    for control_kind in (
        PlanStepKind.ROUTE,
        PlanStepKind.VERIFY,
        PlanStepKind.RETRY,
        PlanStepKind.REPLAN,
        PlanStepKind.HUMAN_APPROVAL,
        PlanStepKind.TERMINATE,
    ):
        assert control_kind.value == control_kind.value.upper()


def test_mission_event_type_is_exactly_the_thirteen_33_types():
    assert {member.value for member in MissionEventType} == {
        "MISSION_CREATED",
        "PLAN_GENERATED",
        "PLAN_REJECTED",
        "PLAN_COMPILED",
        "A2A_TASK_STARTED",
        "A2A_TASK_COMPLETED",
        "MCP_TOOL_CALLED",
        "RAG_SEARCH",
        "EVIDENCE_REJECTED",
        "VERIFICATION_FAILED",
        "REPLAN_TRIGGERED",
        "MISSION_COMPLETED",
        "MISSION_FAILED",
    }
    assert len(MissionEventType) == 13
