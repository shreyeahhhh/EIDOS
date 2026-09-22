"""Two pure pieces of the ``AgentTask`` contract (decisions.md D-166, D-176; V0.6 Step 2).

Neither is wired into the reducer yet — there is no ``A2A_TASK_STARTED``/``A2A_TASK_COMPLETED`` payload and no reducer branch for either (those are
a later V0.6 step). This module is the typed infrastructure those branches will call.

``node_status_for`` is the explicit, separate mapping D-166 calls for: what a *terminal* ``AgentTaskStatus`` means for the plan node the task
serves. It is deliberately not folded into the wire-reporting side — the remote's exact status is kept faithfully (``AgentTaskStatus`` itself,
D-166), and this function is the one place EIDOS's own opinion about each value lives, the same two-tier pattern already used for
``ModelFailureKind -> WorkResult.status`` (``eidos.agents.base.ask_model``) and ``VerificationVerdict -> NodeStatus``
(``eidos.recording.adapters``).

``fold_agent_task`` is the D-176 primitive: given the current ``agent_tasks`` tuple and an incoming ``AgentTask``, find the existing entry with the
same ``a2a_task_id`` and replace it, or append if none exists. ``MissionState.agent_tasks`` stays an immutable tuple (D-082, untouched); only the
rule that transforms it from one state to the next is new. Ambiguity is refused, never guessed at: if the tuple already holds more than one entry
sharing that ``a2a_task_id`` — a state nothing today constructs, but nothing forbids either — the fold raises rather than silently picking one.
"""

from eidos.contracts import AgentTask, AgentTaskStatus, ArtifactRef
from eidos.runtime import NodeStatus

# The four wire-terminal states, plus EIDOS-observed TIMED_OUT, that mean "the task will report no more" — five kinds of "did not succeed", and
# COMPLETED, which alone may still be a success. INPUT_REQUIRED and AUTH_REQUIRED are protocol-terminal for V0.6's purposes: nothing here builds an
# interactive or authenticated flow to answer them, so a task that reaches either goes no further (a scope limit, stated plainly, not a defect).
_NOT_SUCCEEDED = frozenset({
    AgentTaskStatus.FAILED,
    AgentTaskStatus.CANCELED,
    AgentTaskStatus.REJECTED,
    AgentTaskStatus.TIMED_OUT,
    AgentTaskStatus.INPUT_REQUIRED,
    AgentTaskStatus.AUTH_REQUIRED,
})


def node_status_for(status: AgentTaskStatus, *, artifact: ArtifactRef | None) -> NodeStatus | None:
    """The node status a terminal ``AgentTaskStatus`` maps to (D-166), or ``None`` if ``status`` is not yet terminal — the node stays ``AWAITING``.

    ``COMPLETED`` is ``SUCCEEDED`` only if a usable artifact came with it; a completed task with nothing usable is ``NO_RESULT``, not a failure of
    execution (the protocol itself allows a task to conclude with "a direct response message" and no artifact). Every other terminal status is
    ``FAILED`` — no new ``MissionFailureCause`` is needed anywhere downstream; the existing ``EXECUTION_FAILED`` catch-all already fits, exactly as
    it does for a local port fault.
    """
    if status is AgentTaskStatus.COMPLETED:
        return NodeStatus.SUCCEEDED if artifact is not None else NodeStatus.NO_RESULT
    if status in _NOT_SUCCEEDED:
        return NodeStatus.FAILED
    return None  # SUBMITTED, WORKING, UNSPECIFIED: the task has not concluded


class AmbiguousAgentTaskCorrelation(ValueError):
    """More than one existing ``AgentTask`` already shares the ``a2a_task_id`` being folded; the fold refuses to guess which one to replace."""


def fold_agent_task(agent_tasks: tuple[AgentTask, ...], incoming: AgentTask) -> tuple[AgentTask, ...]:
    """Find the ``AgentTask`` whose ``a2a_task_id`` matches ``incoming``'s and replace it; append ``incoming`` if none matches.

    ``incoming.a2a_task_id`` must be set — correlation is undefined without it, and this raises ``ValueError`` if it is absent. Order is otherwise
    preserved: a replacement lands at the position of the entry it replaces, and an append lands last. The input tuple is never mutated; a new one
    is always returned, even a no-op-looking replace (a fresh, equal-by-value ``AgentTask`` is still a different object).
    """
    if incoming.a2a_task_id is None:
        raise ValueError("fold_agent_task requires incoming.a2a_task_id to be set: correlation is undefined without it")
    matches = [index for index, task in enumerate(agent_tasks) if task.a2a_task_id == incoming.a2a_task_id]
    if len(matches) > 1:
        raise AmbiguousAgentTaskCorrelation(
            f"{len(matches)} existing AgentTask entries already share a2a_task_id {str(incoming.a2a_task_id)!r}; refusing to guess which one to replace"
        )
    if not matches:
        return agent_tasks + (incoming,)
    index = matches[0]
    return agent_tasks[:index] + (incoming,) + agent_tasks[index + 1 :]
