"""An A2A task's start and its completion are each recorded once (decisions.md D-172; invariant 8).

``MissionState`` keeps no per-task event history (D-010a, D-113) — only the folded ``AgentTask`` itself — so the reducer cannot tell that a
given ``a2a_task_id`` already has an ``A2A_TASK_STARTED`` or an ``A2A_TASK_COMPLETED`` on record, and a repeat under a new ``event_id`` would
silently re-fold ``agent_tasks`` a second time. D-172 ruled this the same way D-162 item 1 ruled the equivalent question for local nodes: the
**intake** refuses the repeat, and **no per-task event history is added to ``MissionState``**. This module is that check, as a pure function
over a set of keys — mirroring ``step_events.py`` exactly, one layer over: the log keeps the set as it accepts events, and a fold from scratch
keeps it as it replays, so the live log and a replay of it agree.

A task is identified by its **``a2a_task_id``** alone (D-172; the remote system assigns it and it is not reused). What is refused is a second
event of the *same type* for the same task. Only the first is ever recorded; nothing is replaced and nothing is merged.
"""

from collections.abc import Iterable

from eidos.contracts import A2ATaskId, MissionEventType

from .payloads import A2ATaskCompletedPayload, A2ATaskStartedPayload
from .records import EventRecord

AgentTaskEventKey = tuple[MissionEventType, A2ATaskId]


def agent_task_event_key(record: EventRecord) -> AgentTaskEventKey | None:
    """The key of an A2A task start or completion, and ``None`` for every other event."""
    payload = record.payload
    if isinstance(payload, (A2ATaskStartedPayload, A2ATaskCompletedPayload)):
        return (record.event.type, payload.a2a_task_id)
    return None


def repeated_agent_task_event(seen: frozenset[AgentTaskEventKey], record: EventRecord) -> str | None:
    """Why ``record`` repeats an A2A task event already recorded, or ``None`` if it does not."""
    key = agent_task_event_key(record)
    if key is None or key not in seen:
        return None
    event_type, a2a_task_id = key
    return (
        f"a2a_task {str(a2a_task_id)!r} already has a {event_type.value} event; "
        "an A2A task's start and its completion are each recorded once (D-172)"
    )


def agent_task_event_keys(records: Iterable[EventRecord]) -> frozenset[AgentTaskEventKey]:
    """The keys of every A2A task start and completion in ``records``."""
    return frozenset(key for key in map(agent_task_event_key, records) if key is not None)
