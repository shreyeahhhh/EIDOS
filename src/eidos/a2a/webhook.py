"""Turn one push-notification delivery into an ``EventProposal`` — a pure function, not a server (decisions.md D-172,
D-174; V0.6 Step 5 item 4).

**This is not a running HTTP listener.** No module in EIDOS stands up a server (the baseline, the runtime, the
recorder are all pure libraries a caller drives); wiring an actual socket is deployment work outside V0.6's scope,
and would be exactly the kind of "background mission driver" D-170 already ruled out. ``notification_to_proposal``
is what a caller's own HTTP handler calls with the raw POST body it received — it parses, validates, correlates and
returns either a proposal or a typed reason there is none, and **touches ``MissionState`` nowhere**: the caller still
carries the returned ``EventProposal`` to the existing ``EventLog.accept`` (D-172's own guard, the reducer, all of
it) exactly as any other event.

**Correlation is ``MissionState.agent_tasks`` — nothing new (item 3).** A webhook payload carries only a wire
``taskId``/``contextId``; EIDOS's own ``plan_id``/``step_id`` are not part of the A2A protocol at all. Rather than
keep a second, parallel correlation store, this function is handed the mission's current ``agent_tasks`` (the tuple
``eidos.state``'s reducer already folds from each ``A2A_TASK_STARTED``, D-176) and looks the incoming ``taskId`` up
there — the one correlation mechanism the contracts already define.

**Only a task's conclusion is ever proposed as an event (D-174).** A ``WORKING``/``SUBMITTED``/``UNSPECIFIED``
update, a standalone artifact update, or a plain ``message`` payload is legitimately parsed and simply produces
nothing — ``WebhookOutcome.OBSERVED``, not an error. A concluding update whose ``taskId`` correlates to nothing this
mission has recorded is ``UNKNOWN_TASK``: there is no ``plan_id``/``step_id`` to build a payload with, so none is
guessed at. A *repeated* concluding update for a task already concluded is **not** specially detected here — it is
still proposed, and the existing D-172 intake guard (``agent_task_events.py``) refuses it as ``REPEATED_AGENT_TASK_EVENT``
exactly as it would refuse any other case, so duplicate delivery (the spec's own "clients SHOULD process
idempotently") is handled by machinery this module does not need to re-implement.

The artifact, when a ``COMPLETED`` task's text is usable, is **written to the same ``ArtifactStore`` a local agent
writes to** (``record_output``'s own shape, ``artifact_ref_for``'s own naming) — so Analysis and Verification, still
local and unchanged (D-175), read a remote result exactly as they read a local one. A second write for the same step
(a duplicate delivery racing ahead of the D-172 guard) is caught as ``ArtifactConflict`` and treated as already
recorded, never a crash.
"""

from dataclasses import dataclass
from enum import StrEnum

from eidos.agents import Artifact as StoredArtifact
from eidos.agents import ArtifactConflict, ArtifactStore, artifact_ref_for
from eidos.contracts import A2ATaskId, AgentTask, AgentTaskStatus, ArtifactRef, EventId, ExecutionId, MissionId, StepId, TenantId
from eidos.contracts._validators import UtcDateTime
from eidos.state import A2ATaskCompletedPayload, EventProposal

from .convert import ConvertedArtifact, agent_task_status_of, text_artifact_of
from .wire import Artifact as WireArtifact
from .wire import StreamResponse, TaskStateWire

_NOT_CONCLUDING = (AgentTaskStatus.SUBMITTED, AgentTaskStatus.WORKING, AgentTaskStatus.UNSPECIFIED)


class WebhookOutcome(StrEnum):
    PROPOSED = "proposed"  # a usable A2A_TASK_COMPLETED proposal was built
    OBSERVED = "observed"  # parsed fine, but D-174 says this concludes nothing: no event
    MALFORMED = "malformed"  # the body did not parse as a StreamResponse
    UNKNOWN_TASK = "unknown_task"  # a concluding update for an a2a_task_id this mission never started


@dataclass(frozen=True, slots=True)
class WebhookResult:
    outcome: WebhookOutcome
    proposal: EventProposal | None = None
    reason: str | None = None


def _status_of(notification: StreamResponse) -> tuple[str, TaskStateWire, tuple[WireArtifact, ...]] | None:
    """``(task_id, state, artifacts)`` from whichever of ``task``/``status_update`` is present, or ``None`` for a
    ``message`` or a standalone ``artifact_update`` — neither carries a task status at all."""
    if notification.task is not None:
        return notification.task.id, notification.task.status.state, notification.task.artifacts
    if notification.status_update is not None:
        return notification.status_update.task_id, notification.status_update.status.state, ()
    return None


def _write_artifact(store: ArtifactStore, execution_id: ExecutionId, step_id: StepId, converted: ConvertedArtifact | None) -> ArtifactRef | None:
    if converted is None:
        return None
    ref = artifact_ref_for(step_id)
    artifact = StoredArtifact(ref=ref, content_type=converted.content_type, content=converted.content, source_refs=converted.source_refs)
    try:
        store.put_step_artifact(execution_id, step_id, artifact)
    except ArtifactConflict:
        return None  # already recorded (e.g. a duplicate delivery); no new artifact, never a crash
    return ref


def notification_to_proposal(
    raw: bytes | str,
    *,
    agent_tasks: tuple[AgentTask, ...],
    store: ArtifactStore,
    execution_id: ExecutionId,
    tenant_id: TenantId,
    mission_id: MissionId,
    event_id: EventId,
    occurred_at: UtcDateTime,
    recorded_at: UtcDateTime,
) -> WebhookResult:
    try:
        notification = StreamResponse.model_validate_json(raw)
    except Exception as error:  # noqa: BLE001 — a parse or shape fault is reported, never raised (item 4)
        return WebhookResult(outcome=WebhookOutcome.MALFORMED, reason=f"not a valid push-notification payload: {error}")

    status = _status_of(notification)
    if status is None:
        return WebhookResult(outcome=WebhookOutcome.OBSERVED, reason="carries no task status: a message or a standalone artifact update")

    task_id_raw, wire_state, wire_artifacts = status
    outcome = agent_task_status_of(wire_state)
    if outcome in _NOT_CONCLUDING:
        return WebhookResult(outcome=WebhookOutcome.OBSERVED, reason=f"{outcome.value} does not conclude the task (D-174)")

    a2a_task_id = A2ATaskId(task_id_raw)
    task = next((t for t in agent_tasks if t.a2a_task_id == a2a_task_id), None)
    if task is None or task.plan_id is None or task.step_id is None:
        return WebhookResult(
            outcome=WebhookOutcome.UNKNOWN_TASK,
            reason=f"a2a_task {a2a_task_id!r} has no recorded A2A_TASK_STARTED to correlate against",
        )

    artifact_ref = None
    reason = f"the remote task concluded: {outcome.value}"
    if outcome is AgentTaskStatus.COMPLETED:
        converted = text_artifact_of(wire_artifacts)
        artifact_ref = _write_artifact(store, execution_id, task.step_id, converted)
        reason = "the remote task completed with a usable result" if artifact_ref is not None else "the remote task completed with nothing usable"

    payload = A2ATaskCompletedPayload(
        plan_id=task.plan_id, step_id=task.step_id, a2a_task_id=a2a_task_id, outcome=outcome, artifact=artifact_ref, reason=reason
    )
    proposal = EventProposal(
        event_id=event_id, tenant_id=tenant_id, mission_id=mission_id, occurred_at=occurred_at, recorded_at=recorded_at, payload=payload
    )
    return WebhookResult(outcome=WebhookOutcome.PROPOSED, proposal=proposal)
