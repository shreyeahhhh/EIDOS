"""eidos.memory — Execution Experience and Strategy Memory (decisions.md D-198; V1.0 Step 1).

A core layer, joining ``eidos.contracts``, ``eidos.runtime``, ``eidos.state``, ``eidos.telemetry`` and
``eidos.planning``: deterministic, no I/O, no clock, no hidden state, no model/vendor name. Only ``store.py``
(V1.0 Step 3, not built yet) is permitted file I/O — ``experience.py`` and ``relevance.py`` (V1.0 Step 2, not
built yet) stay exactly as pure as every other core layer in this project.

    from eidos.memory import ExecutionExperience, evaluate_experience

V1.0 Step 1 only: ``ExecutionExperience`` (the immutable, factual record of one completed mission) and
``evaluate_experience`` (the pure function that builds one from a ``Strategy``, a ``TaskGenome`` and an
already-projected ``TelemetryRecord``). No quality/confidence score, no strategy signature, no persistent
``strategy_id`` on any existing contract, no storage, no relevance/retrieval logic, no selector — each is a
later, separately-approved step (D-198).
"""

from .experience import ExecutionExperience, evaluate_experience

__all__ = ["ExecutionExperience", "evaluate_experience"]
