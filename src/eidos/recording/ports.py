"""The clock and the identifier source (decisions.md D-158 item 3).

Both are **injected**: the deterministic layers read neither, and nothing outside this package draws a timestamp or an identifier. The recorder
asks a ``Clock`` for the time an event occurred and for a monotonic reading to measure a node's duration, and asks an ``IdSource`` for each
event's id. Tests supply fixed ones, so a recorded run is repeatable byte for byte.

``SystemClock`` and ``UuidEventIds`` are the real ones. This package is an adapter, not a deterministic component, so it may use them.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from eidos.contracts import EventId


class Clock(Protocol):
    def now(self) -> datetime:
        """The current time, timezone-aware UTC. It stamps an event's ``occurred_at`` and ``recorded_at``."""
        ...

    def monotonic_ns(self) -> int:
        """A monotonic reading in nanoseconds, used only to measure how long a node ran. Never used to order anything."""
        ...


class IdSource(Protocol):
    def next_event_id(self) -> EventId: ...


@dataclass(frozen=True, slots=True)
class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()


@dataclass(frozen=True, slots=True)
class UuidEventIds:
    def next_event_id(self) -> EventId:
        return EventId(uuid.uuid4())
