"""V0.6 Step 6 — the recording adapter: bridge one externally received A2A push-notification delivery into a
caller-owned ``EventLog`` (decisions.md D-172, D-174, D-177).

**The one hop Step 5 deliberately left to the caller.** ``eidos.a2a.webhook.notification_to_proposal`` already turns
a raw delivery into an ``EventProposal`` or a typed reason there is none, and touches ``MissionState`` nowhere — its
own docstring says the caller "still carries the returned ``EventProposal`` to the existing ``EventLog.accept``...
exactly as any other event." ``record_a2a_notification`` is exactly that hop, named and tested on its own, and
nothing more: it does not create a log, does not hold or own one, never calls ``accept_resumed``, never resumes or
re-runs anything. ``log: EventLog`` is a parameter on every call, not a constructor field this module keeps — the
caller's ownership of it is never in question.

**Two taxonomies, carried through untouched, never collapsed into a third.** A delivery that never became a
proposal at all — did not parse (``WebhookOutcome.MALFORMED``, "malformed external event"), named a task this
mission never started (``WebhookOutcome.UNKNOWN_TASK``, "invalid correlation" — there is no ``plan_id``/``step_id``
to build a proposal with), or legitimately concludes nothing (``WebhookOutcome.OBSERVED``, D-174) — is answered by
``webhook`` alone; ``intake`` stays ``None``. A delivery that DID become a proposal (``WebhookOutcome.PROPOSED``) is
carried, unmodified, to the caller's own ``log.accept`` — the *existing* mechanism (item 8: nothing here duplicates
its duplicate check, its terminal check or its D-172 repeat guard) — and ``intake.outcome`` says what that made of
it: ``DUPLICATE``/``REPEATED_AGENT_TASK_EVENT`` ("duplicate lifecycle event"), ``INVALID_FOR_STATE`` ("invalid event
proposal"), ``POST_TERMINAL``/``OUT_OF_ORDER``/``STALE`` ("invalid state transition"), or ``APPLIED`` ("successful
recording"). Nothing here invents a new outcome vocabulary on top of ``WebhookOutcome`` and ``ReduceOutcome``; both
already say everything D-172/D-176/D-177 need said.

**Never ``accept_resumed`` (D-177).** A concluding delivery is always offered to the *ordinary* ``accept`` — D-176's
own exemption is what lets a ``paused`` mission still take it, and ``status`` stays ``paused`` through it
unconditionally. Resuming the mission afterwards is a distinct, explicit decision only the caller makes (D-170);
this module cannot make it for them and does not try to.

**Why this lives in ``eidos.recording``, not ``eidos.a2a``.** ``eidos.a2a`` speaks only outward, to the remote
system and to an ``EventProposal`` — Step 5's own boundary (item 11) forbids it reaching into ``eidos.state``'s
*mutating* surface. ``eidos.recording`` is the package that already turns something into recorded events
(``record_baseline``, D-158); this is its second, narrower entry point, turning one external delivery into a
recorded event instead of one local pass. Because ``eidos.a2a`` needs the optional ``a2a`` extra (D-171, ``httpx``),
this module is deliberately **not** re-exported from ``eidos/recording/__init__.py`` — importing ``eidos.recording``
itself must stay free of that dependency (its own guard test says so). A caller that uses A2A already depends on
``eidos.a2a`` directly (for the client and the work agent) and imports this module explicitly:
``from eidos.recording.a2a import record_a2a_notification``.
"""

from dataclasses import dataclass

from eidos.a2a import WebhookOutcome, WebhookResult, notification_to_proposal
from eidos.agents import ArtifactStore
from eidos.contracts import EventId, ExecutionId, MissionId, TenantId
from eidos.contracts._validators import UtcDateTime
from eidos.state import EventLog, IntakeResult


@dataclass(frozen=True, slots=True)
class A2ARecordingResult:
    """What happened when one delivery was offered to a caller-owned ``EventLog``.

    ``intake`` is ``None`` exactly when ``webhook.outcome`` is not ``PROPOSED`` — nothing reached the log at all.
    Otherwise ``intake`` is the log's own answer (``IntakeResult``), including a refusal.
    """

    webhook: WebhookResult
    intake: IntakeResult | None = None

    @property
    def recorded(self) -> bool:
        """``True`` only for a proposal the log actually applied — never for ``OBSERVED``/``MALFORMED``/``UNKNOWN_TASK``
        (nothing was offered) and never for a proposal the log refused (duplicate, invalid, or post-terminal)."""
        return self.intake is not None and self.intake.applied


def record_a2a_notification(
    log: EventLog,
    raw: bytes | str,
    *,
    store: ArtifactStore,
    execution_id: ExecutionId,
    tenant_id: TenantId,
    mission_id: MissionId,
    event_id: EventId,
    occurred_at: UtcDateTime,
    recorded_at: UtcDateTime,
) -> A2ARecordingResult:
    """Parse and correlate ``raw`` against ``log``'s own ``agent_tasks``, and, only if that yields a proposal, offer
    it to ``log.accept`` — the same ``log`` the caller passed in, borrowed for the duration of this call and never
    replaced, wrapped or held onto afterwards."""
    agent_tasks = log.state.agent_tasks if log.state is not None else ()
    webhook = notification_to_proposal(
        raw,
        agent_tasks=agent_tasks,
        store=store,
        execution_id=execution_id,
        tenant_id=tenant_id,
        mission_id=mission_id,
        event_id=event_id,
        occurred_at=occurred_at,
        recorded_at=recorded_at,
    )
    if webhook.outcome is not WebhookOutcome.PROPOSED:
        return A2ARecordingResult(webhook=webhook)
    return A2ARecordingResult(webhook=webhook, intake=log.accept(webhook.proposal))


__all__ = ["A2ARecordingResult", "record_a2a_notification"]
