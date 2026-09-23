"""eidos.memory — Execution Experience and Strategy Memory (decisions.md D-198; V1.0 Steps 1 to 3).

A core-shaped layer, joining ``eidos.contracts``, ``eidos.runtime``, ``eidos.state``, ``eidos.telemetry`` and
``eidos.planning``: deterministic, no I/O, no clock, no hidden state, no model/vendor name — except ``store.py``,
the one module in this package ever permitted file I/O. ``experience.py`` and ``relevance.py`` stay exactly as
pure as every other core layer in this project.

    from eidos.memory import (
        ExecutionExperience, evaluate_experience,
        TaskRelevance, task_relevance, relevant_experience, experience_for,
        ExperienceStore, ExperienceLoadRejection, ExperienceLoadRejectionCode, JsonlExperienceStore,
    )

V1.0 Step 1: ``ExecutionExperience`` (the immutable, factual record of one completed mission) and
``evaluate_experience`` (the pure function that builds one from a ``Strategy``, a ``TaskGenome`` and an
already-projected ``TelemetryRecord``). No quality/confidence score, no strategy signature, no persistent
``strategy_id`` on any existing contract.

V1.0 Step 2: ``TaskRelevance``/``task_relevance``/``relevant_experience`` (task-level relevance — a structural
comparison over ``required_capabilities``/``risk_level``/``autonomy_level`` only, never a vector-based or
model-judged similarity mechanism, and never staleness) and ``experience_for`` (strategy-level relevance — exact
structural shape matching, never ``StrategyId`` comparison). Neither ranks, chooses, or scores anything — that is
the selector's own, later, separately-approved job (Step 4, not built yet).

V1.0 Step 3: ``ExperienceStore`` (the injected persistence port) and ``JsonlExperienceStore`` (its one real,
local, append-only JSONL implementation — load-once, cached as an immutable tuple, never re-reading the file on
``append``). A malformed persisted line is a typed ``ExperienceLoadRejection``, never silently dropped, mirroring
``eidos.state.replay``'s own established JSONL convention (D-157) one layer over.

No selector yet — that is Step 4, a later, separately-approved step (D-198).
"""

from .experience import ExecutionExperience, evaluate_experience
from .relevance import TaskRelevance, experience_for, relevant_experience, task_relevance
from .store import (
    ExperienceLoadRejection,
    ExperienceLoadRejectionCode,
    ExperienceStore,
    JsonlExperienceStore,
    dump_experience_jsonl,
    load_experience_jsonl,
)

__all__ = [
    "ExecutionExperience",
    "ExperienceLoadRejection",
    "ExperienceLoadRejectionCode",
    "ExperienceStore",
    "JsonlExperienceStore",
    "TaskRelevance",
    "dump_experience_jsonl",
    "evaluate_experience",
    "experience_for",
    "load_experience_jsonl",
    "relevant_experience",
    "task_relevance",
]
