"""eidos.memory — Execution Experience and Strategy Memory (decisions.md D-198; V1.0 Steps 1 and 2).

A core layer, joining ``eidos.contracts``, ``eidos.runtime``, ``eidos.state``, ``eidos.telemetry`` and
``eidos.planning``: deterministic, no I/O, no clock, no hidden state, no model/vendor name. Only ``store.py``
(V1.0 Step 3, not built yet) is permitted file I/O — ``experience.py`` and ``relevance.py`` stay exactly as pure
as every other core layer in this project.

    from eidos.memory import ExecutionExperience, evaluate_experience, TaskRelevance, task_relevance, relevant_experience, experience_for

V1.0 Step 1: ``ExecutionExperience`` (the immutable, factual record of one completed mission) and
``evaluate_experience`` (the pure function that builds one from a ``Strategy``, a ``TaskGenome`` and an
already-projected ``TelemetryRecord``). No quality/confidence score, no strategy signature, no persistent
``strategy_id`` on any existing contract.

V1.0 Step 2: ``TaskRelevance``/``task_relevance``/``relevant_experience`` (task-level relevance — a structural
comparison over ``required_capabilities``/``risk_level``/``autonomy_level`` only, never a vector-based or
model-judged similarity mechanism, and never staleness) and ``experience_for`` (strategy-level relevance — exact
structural shape matching, never ``StrategyId`` comparison). Neither ranks, chooses, or scores anything — that is the selector's
own, later, separately-approved job (Step 4, not built yet).

No storage, no selector — each is a later, separately-approved step (D-198).
"""

from .experience import ExecutionExperience, evaluate_experience
from .relevance import TaskRelevance, experience_for, relevant_experience, task_relevance

__all__ = [
    "ExecutionExperience",
    "TaskRelevance",
    "evaluate_experience",
    "experience_for",
    "relevant_experience",
    "task_relevance",
]
