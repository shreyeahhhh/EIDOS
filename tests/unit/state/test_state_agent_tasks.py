"""``eidos.state.agent_tasks``: the AgentTask status mapping (D-166) and the D-176 fold primitive (V0.6 Step 2).

Neither is wired into the reducer yet — there is no ``A2A_TASK_STARTED``/``A2A_TASK_COMPLETED`` payload and no reducer branch for either. These
tests pin the two pieces of typed infrastructure standalone: what a terminal ``AgentTaskStatus`` means for a node, and how ``agent_tasks`` folds
one incoming fact without ever becoming a keyed structure or silently resolving an ambiguity.
"""

from uuid import uuid4

import pytest

from eidos.contracts import A2ATaskId, AgentId, AgentTask, AgentTaskStatus, ArtifactRef, PlanId, StepId
from eidos.runtime import NodeStatus
from eidos.state import AmbiguousAgentTaskCorrelation, fold_agent_task, node_status_for

from eidos_state_factories import RESEARCH_AGENT, at

TERMINAL_NOT_SUCCEEDED = (
    AgentTaskStatus.FAILED,
    AgentTaskStatus.CANCELED,
    AgentTaskStatus.REJECTED,
    AgentTaskStatus.TIMED_OUT,
    AgentTaskStatus.INPUT_REQUIRED,
    AgentTaskStatus.AUTH_REQUIRED,
)
NOT_YET_TERMINAL = (AgentTaskStatus.SUBMITTED, AgentTaskStatus.WORKING, AgentTaskStatus.UNSPECIFIED)


def task(*, status: AgentTaskStatus, a2a_task_id: str | None = "remote-task-1", agent_id: AgentId | None = None) -> AgentTask:
    return AgentTask(
        agent_id=agent_id or RESEARCH_AGENT,
        status=status,
        a2a_task_id=A2ATaskId(a2a_task_id) if a2a_task_id is not None else None,
    )


# --- node_status_for (D-166) -------------------------------------------------------------------------------------------------------


def test_every_status_falls_into_exactly_one_of_the_three_buckets():
    # A total-function check: every AgentTaskStatus member is accounted for by node_status_for, in exactly one of "succeeded", "failed" or
    # "not yet terminal" — none is silently unmapped.
    seen = set()
    for status in AgentTaskStatus:
        result = node_status_for(status, artifact=None)
        seen.add(status)
        if status in NOT_YET_TERMINAL:
            assert result is None
        else:
            assert result is NodeStatus.FAILED or (status is AgentTaskStatus.COMPLETED and result is NodeStatus.NO_RESULT)
    assert seen == set(AgentTaskStatus)


def test_completed_with_a_usable_artifact_is_succeeded():
    assert node_status_for(AgentTaskStatus.COMPLETED, artifact=ArtifactRef("artifact:gather")) is NodeStatus.SUCCEEDED


def test_completed_with_no_artifact_is_no_result_not_a_failure():
    # decisions.md D-166: the protocol allows a task to conclude with a direct response message and no artifact; that is not a failure of
    # execution.
    assert node_status_for(AgentTaskStatus.COMPLETED, artifact=None) is NodeStatus.NO_RESULT


@pytest.mark.parametrize("status", TERMINAL_NOT_SUCCEEDED, ids=lambda s: s.value)
def test_every_other_terminal_status_is_failed_whether_or_not_an_artifact_is_offered(status):
    # A stray artifact never turns a FAILED/CANCELED/REJECTED/TIMED_OUT/INPUT_REQUIRED/AUTH_REQUIRED report into a success.
    assert node_status_for(status, artifact=None) is NodeStatus.FAILED
    assert node_status_for(status, artifact=ArtifactRef("artifact:gather")) is NodeStatus.FAILED


@pytest.mark.parametrize("status", NOT_YET_TERMINAL, ids=lambda s: s.value)
def test_a_status_that_has_not_concluded_maps_to_nothing_the_node_stays_awaiting(status):
    assert node_status_for(status, artifact=None) is None
    assert node_status_for(status, artifact=ArtifactRef("artifact:gather")) is None


# --- fold_agent_task (D-176) -------------------------------------------------------------------------------------------------------


def test_folding_into_an_empty_collection_appends_the_one_entry():
    incoming = task(status=AgentTaskStatus.SUBMITTED)
    result = fold_agent_task((), incoming)
    assert result == (incoming,)


def test_a_task_id_not_yet_present_is_appended_and_existing_entries_are_untouched_and_reordered_not():
    first = task(status=AgentTaskStatus.SUBMITTED, a2a_task_id="task-1")
    second = task(status=AgentTaskStatus.SUBMITTED, a2a_task_id="task-2")
    result = fold_agent_task((first,), second)
    assert result == (first, second)  # appended last; the existing entry keeps its position


def test_a_matching_task_id_is_replaced_in_place_at_its_original_position():
    before = task(status=AgentTaskStatus.SUBMITTED, a2a_task_id="task-2")
    others = (
        task(status=AgentTaskStatus.SUBMITTED, a2a_task_id="task-1"),
        before,
        task(status=AgentTaskStatus.SUBMITTED, a2a_task_id="task-3"),
    )
    after = task(status=AgentTaskStatus.COMPLETED, a2a_task_id="task-2")
    result = fold_agent_task(others, after)
    assert result == (others[0], after, others[2])  # task-1 and task-3 keep their exact position and value
    assert result[1] is after and result[1] != before


def test_the_input_tuple_is_never_mutated_and_the_result_is_a_new_tuple():
    original = (task(status=AgentTaskStatus.SUBMITTED, a2a_task_id="task-1"),)
    replacement = task(status=AgentTaskStatus.WORKING, a2a_task_id="task-1")
    result = fold_agent_task(original, replacement)
    assert original == (task(status=AgentTaskStatus.SUBMITTED, a2a_task_id="task-1"),)  # the caller's tuple is exactly as it was
    assert result is not original
    assert len(result) == len(original) == 1


def test_replacing_with_an_equal_looking_value_still_returns_a_freshly_built_tuple():
    entry = task(status=AgentTaskStatus.SUBMITTED, a2a_task_id="task-1")
    same_again = task(status=AgentTaskStatus.SUBMITTED, a2a_task_id="task-1")  # equal by value, a distinct object
    result = fold_agent_task((entry,), same_again)
    assert result == (entry,) and result[0] == same_again


def test_an_incoming_task_with_no_a2a_task_id_is_refused_correlation_is_undefined_without_it():
    with pytest.raises(ValueError, match="a2a_task_id"):
        fold_agent_task((), task(status=AgentTaskStatus.SUBMITTED, a2a_task_id=None))


def test_two_existing_entries_already_sharing_a_task_id_is_refused_not_guessed_at():
    # Nothing today constructs this (agent_tasks is never populated outside these tests), but nothing forbids it either (D-082 leaves
    # agent_tasks an unkeyed collection); the fold must not silently pick one.
    duplicated = (
        task(status=AgentTaskStatus.SUBMITTED, a2a_task_id="task-1", agent_id=AgentId(uuid4())),
        task(status=AgentTaskStatus.WORKING, a2a_task_id="task-1", agent_id=AgentId(uuid4())),
    )
    with pytest.raises(AmbiguousAgentTaskCorrelation, match="task-1"):
        fold_agent_task(duplicated, task(status=AgentTaskStatus.COMPLETED, a2a_task_id="task-1"))


def test_ambiguous_correlation_is_a_value_error_matching_the_projects_own_exception_convention():
    # eidos.agents.artifacts.ArtifactConflict and eidos.compiler.plan's DuplicateStepIdError follow the same shape: a small, named
    # ValueError subclass, never a bare exception.
    assert issubclass(AmbiguousAgentTaskCorrelation, ValueError)


def test_folding_preserves_the_correlation_by_a2a_task_id_alone_agent_id_and_plan_step_are_not_part_of_the_key():
    original = AgentTask(
        agent_id=RESEARCH_AGENT, status=AgentTaskStatus.SUBMITTED, a2a_task_id=A2ATaskId("task-1"),
        plan_id=PlanId(uuid4()), step_id=StepId("gather"), started_at=at(0),
    )
    completed = AgentTask(agent_id=RESEARCH_AGENT, status=AgentTaskStatus.COMPLETED, a2a_task_id=A2ATaskId("task-1"))
    result = fold_agent_task((original,), completed)
    assert result == (completed,)  # the replacement wins outright; the fold does not merge fields from the entry it replaces
