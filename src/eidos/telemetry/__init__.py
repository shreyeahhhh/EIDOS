"""eidos.telemetry — a deterministic, multi-execution projection over already-recorded facts (decisions.md D-159,
D-196; V0.9 Steps 2 and 4).

A core layer, joining ``eidos.contracts``, ``eidos.runtime`` and ``eidos.state``: deterministic, no I/O, no clock,
no hidden state, no model/vendor/tool name. It is the layer ``eidos.state.execution_record``'s own docstring
already named and deferred — "not the telemetry platform (V0.9)" — built now as exactly what that line promised:
a further pure projection over the same facts, never a second authoritative store.

    from eidos.telemetry import TelemetryRecord, project

``project(records)`` composes the existing ``execution_record`` rather than re-folding events, and adds only
facts already derivable from it: per-status node counts, the count of remote-task submissions recorded, a mission
wall-clock span, the accumulated node-execution time (``execution_time_used_ms`` — distinct from the wall-clock
span, never combined with it, D-158 item 4), and which gate a rejected plan was refused at
(``plan_rejected_at``, V0.9 Step 4). It takes an in-memory ``Iterable[EventRecord]`` and returns a value or a
typed ``ReplayRejection`` — nothing here reads a file. If a durable-storage loader is ever needed, it is a
separate, outer adapter, not part of this package.

Not here yet, on purpose: a model identifier on any recorded fact, any ``strategy_id`` (no execution today is
produced from a `Strategy`), any quality/confidence/rate/score, any new `MissionEvent` type, any durable
telemetry store, and the future benchmark or Strategy Memory (`eidos.evaluation`/`eidos.memory`, later, separate
milestones).
"""

from .project import TelemetryRecord, project

__all__ = ["TelemetryRecord", "project"]
