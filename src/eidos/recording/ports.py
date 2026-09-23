"""The clock and the identifier sources (decisions.md D-158 item 3; V0.9 Step 3 adds the strategy/plan id sources).

Both are **injected**: the deterministic layers read neither, and nothing outside this package draws a timestamp or an identifier. The recorder
asks a ``Clock`` for the time an event occurred and for a monotonic reading to measure a node's duration, and asks an ``IdSource`` for each
event's id. Tests supply fixed ones, so a recorded run is repeatable byte for byte.

``SystemClock`` and ``UuidEventIds`` are the real ones. This package is an adapter, not a deterministic component, so it may use them.

**``UuidStrategyIds``/``UuidPlanIds``** are the real counterparts to ``eidos.planning.pipeline.StrategyIdSource`` and
``eidos.expansion.PlanIdSource`` — the two core-layer Protocols each already, explicitly, deferred a real implementation to exactly this kind of
adapter ("a caller supplies one, exactly as a caller supplies a real ``IdSource`` to ``eidos.recording`` today," ``StrategyIdSource``'s own
docstring). No new Protocol is defined here: ``eidos.recording`` never imports ``eidos.planning``/``eidos.expansion`` (neither is in its own
approved dependency set), and does not need to — each Protocol is structurally satisfied by a plain ``next_strategy_id``/``next_plan_id`` method,
and only the id *types* (``StrategyId``, ``PlanId``), already-plain ``eidos.contracts`` types, are needed here.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from eidos.contracts import EventId, PlanId, StrategyId


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


@dataclass(frozen=True, slots=True)
class UuidStrategyIds:
    """The real ``eidos.planning.pipeline.StrategyIdSource``."""

    def next_strategy_id(self) -> StrategyId:
        return StrategyId(uuid.uuid4())


@dataclass(frozen=True, slots=True)
class UuidPlanIds:
    """The real ``eidos.expansion.PlanIdSource``."""

    def next_plan_id(self) -> PlanId:
        return PlanId(uuid.uuid4())
