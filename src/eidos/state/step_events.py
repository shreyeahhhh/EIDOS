"""A step's start and its settlement are each recorded once (decisions.md D-162 item 1; invariant 8).

``MissionState`` keeps no per-node state (D-010a, D-113), so the reducer cannot tell that a step has already started or settled, and a repeated
``NODE_STARTED`` or ``NODE_SETTLED`` under a new ``event_id`` would fold its counters a second time. The owner ruled that the **intake** refuses the
repeat and that **no per-node state is added to ``MissionState``**. This module is that check, as a pure function over a set of keys: the log keeps
the set as it accepts events, and a fold from scratch keeps it as it replays, so the live log and a replay of it agree.

A step is identified by its **plan and its step id**: the same step id in another plan version is another step (D-147 governs how work step ids
are chosen across versions), so a replanned mission can run and verify again. What is refused is a second event of the *same type* for the same
step. Only the first is ever recorded; nothing is replaced and nothing is merged.
"""

from collections.abc import Iterable

from eidos.contracts import MissionEventType, PlanId, StepId

from .payloads import NodeSettledPayload, NodeStartedPayload
from .records import EventRecord

StepEventKey = tuple[MissionEventType, PlanId, StepId]


def step_event_key(record: EventRecord) -> StepEventKey | None:
    """The key of a node start or settlement, and ``None`` for every other event."""
    payload = record.payload
    if isinstance(payload, NodeStartedPayload):
        return (record.event.type, payload.plan_id, payload.step_id)
    if isinstance(payload, NodeSettledPayload):
        return (record.event.type, payload.plan_id, payload.result.step_id)
    return None


def repeated_step_event(seen: frozenset[StepEventKey], record: EventRecord) -> str | None:
    """Why ``record`` repeats a step event already recorded, or ``None`` if it does not."""
    key = step_event_key(record)
    if key is None or key not in seen:
        return None
    event_type, plan_id, step_id = key
    return f"step {str(step_id)!r} of plan {str(plan_id)!r} already has a {event_type.value} event; a step's start and its settlement are each recorded once"


def step_event_keys(records: Iterable[EventRecord]) -> frozenset[StepEventKey]:
    """The keys of every node start and settlement in ``records``."""
    return frozenset(key for key in map(step_event_key, records) if key is not None)
