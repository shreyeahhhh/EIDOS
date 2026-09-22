"""EIDOS's own conclusion that an outstanding task has gone unheard from for too long (decisions.md D-166, D-173 item 2).

This is the **second** of D-173's three timeout concepts, and the only one ``eidos.a2a`` itself computes: not one
HTTP call's own deadline (``transport.py``'s job, item 1) and not the mission's execution budget (the reducer's job,
unchanged, item 3). It is a pure function of what the state already records — ``AgentTask.started_at``, the
``occurred_at`` of the ``A2A_TASK_STARTED`` event that created the entry (D-168) — and a caller-supplied "now" and
deadline, **never** the recorder's monotonic clock (D-173: unsafe across a possible process restart between
submission and completion) and never a silently invented default (D-135's discipline, applied here too — a caller
states its own deadline).

**Nothing here polls, sleeps or runs on its own.** D-170: V0.6 builds no background driver. A caller decides when to
ask — once, occasionally, from a health check, however it likes — and ``check_deadline`` answers for one task at a
time, as a plain, synchronous, side-effect-free question.
"""

from datetime import datetime

from eidos.contracts import AgentTask, AgentTaskStatus
from eidos.state import A2ATaskCompletedPayload

# The statuses a task can still be found in when its deadline is checked — the same set D-176's reducer exception
# reads as "genuinely outstanding" (reducer.py's `_NOT_YET_CONCLUDED_AGENT_TASK_STATUSES`); this module does not
# import the reducer (a core layer `eidos.a2a` never reaches into), so the set is restated here, not imported —
# both are read directly from D-166's own three non-concluding members, and a guard test in eidos.a2a keeps them equal.
NOT_YET_CONCLUDED = (AgentTaskStatus.SUBMITTED, AgentTaskStatus.WORKING, AgentTaskStatus.UNSPECIFIED)


def check_deadline(task: AgentTask, *, now: datetime, timeout_seconds: float) -> A2ATaskCompletedPayload | None:
    """``None`` if ``task`` is not outstanding, or has not yet exceeded ``timeout_seconds`` since it started.

    Otherwise, the ``A2A_TASK_COMPLETED`` payload that concludes it as ``TIMED_OUT`` (D-166) — the caller still
    proposes this through the ordinary event path (``EventLog.accept``/``EventProposal``), exactly like a webhook
    delivery's conversion (``webhook.py``); this function only decides *whether*, never records anything itself.
    """
    if task.status not in NOT_YET_CONCLUDED:
        return None
    if task.started_at is None or task.plan_id is None or task.step_id is None or task.a2a_task_id is None:
        return None  # nothing to compute a deadline from, or nothing to correlate the conclusion to
    elapsed = (now - task.started_at).total_seconds()
    if elapsed < timeout_seconds:
        return None
    return A2ATaskCompletedPayload(
        plan_id=task.plan_id,
        step_id=task.step_id,
        a2a_task_id=task.a2a_task_id,
        outcome=AgentTaskStatus.TIMED_OUT,
        artifact=None,
        reason=f"no terminal report within {timeout_seconds} seconds of submission ({elapsed:.1f}s elapsed)",
    )
