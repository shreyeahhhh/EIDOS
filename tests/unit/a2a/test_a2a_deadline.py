"""``check_deadline`` (decisions.md D-166, D-173 item 2): a pure question, never a poll — the second, separate
timeout concept, computed from recorded timestamps and never the recorder's monotonic clock."""

from datetime import timedelta
from uuid import UUID

import pytest

from eidos.a2a.deadline import check_deadline
from eidos.contracts import AgentId, AgentTask, AgentTaskStatus, PlanId, StepId
from eidos.state import A2ATaskCompletedPayload

from eidos_state_factories import at

AGENT = AgentId(UUID(int=5))
PLAN = PlanId(UUID(int=4))
STEP = StepId("gather")


def outstanding(**overrides) -> AgentTask:
    fields = dict(agent_id=AGENT, status=AgentTaskStatus.SUBMITTED, a2a_task_id="t1", plan_id=PLAN, step_id=STEP, started_at=at(0))
    fields.update(overrides)
    return AgentTask(**fields)


def test_none_when_not_yet_due():
    task = outstanding()
    assert check_deadline(task, now=at(0) + timedelta(seconds=59), timeout_seconds=60) is None


def test_a_typed_timed_out_completion_once_the_deadline_has_passed():
    task = outstanding()
    payload = check_deadline(task, now=at(0) + timedelta(seconds=61), timeout_seconds=60)
    assert isinstance(payload, A2ATaskCompletedPayload)
    assert payload.outcome is AgentTaskStatus.TIMED_OUT
    assert payload.plan_id == PLAN and payload.step_id == STEP and payload.a2a_task_id == "t1"
    assert payload.artifact is None
    assert "60" in payload.reason


def test_exactly_at_the_deadline_has_already_timed_out():
    """``timeout_seconds`` is a budget, not a strictly-greater-than threshold: a task given 60 seconds that has
    used exactly 60 has used its whole budget, the same inclusive convention a deadline check reads either way —
    chosen here, tested explicitly so the boundary is pinned rather than left to fall out of ``<`` by accident."""
    task = outstanding()
    payload = check_deadline(task, now=at(0) + timedelta(seconds=60), timeout_seconds=60)
    assert payload is not None and payload.outcome is AgentTaskStatus.TIMED_OUT


@pytest.mark.parametrize("status", [AgentTaskStatus.COMPLETED, AgentTaskStatus.FAILED, AgentTaskStatus.CANCELED, AgentTaskStatus.REJECTED, AgentTaskStatus.TIMED_OUT])
def test_none_for_a_task_that_has_already_concluded(status):
    task = outstanding(status=status)
    assert check_deadline(task, now=at(0) + timedelta(days=1), timeout_seconds=60) is None


def test_none_without_a_started_at_to_measure_from():
    task = outstanding(started_at=None)
    assert check_deadline(task, now=at(0) + timedelta(days=1), timeout_seconds=60) is None


def test_none_without_plan_id_or_step_id_to_correlate_the_conclusion_to():
    assert check_deadline(outstanding(plan_id=None), now=at(0) + timedelta(days=1), timeout_seconds=60) is None
    assert check_deadline(outstanding(step_id=None), now=at(0) + timedelta(days=1), timeout_seconds=60) is None


def test_none_without_an_a2a_task_id():
    assert check_deadline(outstanding(a2a_task_id=None), now=at(0) + timedelta(days=1), timeout_seconds=60) is None


def test_never_touches_a_clock_itself_now_is_entirely_the_callers():
    """A pure function: the same inputs give the same answer, called any number of times, with no side effect."""
    task = outstanding()
    first = check_deadline(task, now=at(0) + timedelta(seconds=61), timeout_seconds=60)
    second = check_deadline(task, now=at(0) + timedelta(seconds=61), timeout_seconds=60)
    assert first == second
