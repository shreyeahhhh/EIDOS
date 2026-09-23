"""Task and strategy relevance — pure, deterministic filtering of Execution Experience (decisions.md D-198;
V1.0 Step 2).

Two separate relevance questions, answered by two separate functions, never conflated:

- **Task relevance** (``task_relevance``/``relevant_experience``) asks whether a stored ``ExecutionExperience``
  is relevant to *this mission's* ``TaskGenome`` at all — a structural comparison over
  ``required_capabilities``/``risk_level``/``autonomy_level`` only, the sole fields ``TaskGenome`` offers that
  are deterministically comparable without a vector-based, model-judged or retrieval-based similarity mechanism
  (D-198 ruling 3). No scalar value of any kind is ever produced — only one of three closed, structural
  relevance levels.
- **Strategy relevance** (``experience_for``) asks, of the task-relevant records, which of *this call's own
  candidate* ``Strategy`` objects each one structurally corresponds to. ``StrategyId`` is fresh every generation
  round (D-182 — "a fresh generation round produces fresh ids for a fresh, unrelated candidate set"), so
  identity is never compared here; **shape** — the stage-by-stage capability tuples and the verification
  posture — is the only thing stable across missions.

``relevant_experience`` only ever filters by task relevance. It never ranks, never chooses a strategy, never
computes anything resembling the V1.0 selection algorithm — that is ``eidos.selectors.experience_informed``'s
own, later, separately-approved job (D-198 ruling 8), which this module knows nothing about.

Pure throughout: no I/O, no clock, no randomness, no model call, no storage dependency, no mutation of any
input. Every function reads its arguments and returns a new tuple; nothing here holds state between calls.
"""

from enum import StrEnum

from eidos.contracts import TaskGenome
from eidos.planning import Strategy

from .experience import ExecutionExperience


class TaskRelevance(StrEnum):
    """How relevant one ``ExecutionExperience``'s own recorded task characteristics are to a new ``TaskGenome``
    (D-198 ruling 3) — a structural classification, never a scalar similarity score."""

    SAME = "same"
    SIMILAR = "similar"
    IRRELEVANT = "irrelevant"


def task_relevance(experience: ExecutionExperience, task_genome: TaskGenome) -> TaskRelevance:
    """``SAME`` requires an exact match of required capabilities (as a set — duplicates on either side never
    change the comparison), risk level and autonomy level. ``SIMILAR`` keeps the risk/autonomy match exact and
    loosens only the capability comparison to a non-empty, non-total intersection. Any risk or autonomy
    mismatch is ``IRRELEVANT`` regardless of capability overlap — no cross-level transfer, ever (D-198 ruling
    3). Zero capability overlap, with risk/autonomy matching, is also ``IRRELEVANT``."""
    if experience.task_risk_level != task_genome.risk_level or experience.task_autonomy_level != task_genome.autonomy_level:
        return TaskRelevance.IRRELEVANT
    experience_capabilities = set(experience.task_required_capabilities)
    task_capabilities = set(task_genome.required_capabilities)
    if experience_capabilities == task_capabilities:
        return TaskRelevance.SAME
    if experience_capabilities & task_capabilities:
        return TaskRelevance.SIMILAR
    return TaskRelevance.IRRELEVANT


def relevant_experience(
    candidates: tuple[Strategy, ...], task_genome: TaskGenome, history: tuple[ExecutionExperience, ...]
) -> tuple[ExecutionExperience, ...]:
    """Every record in ``history`` whose ``task_relevance`` against ``task_genome`` is ``SAME`` or ``SIMILAR``,
    in ``history``'s own order — a plain filter, nothing ranked, nothing chosen. ``candidates`` is accepted for
    signature symmetry with the eventual ``Selector.select(candidates, task_genome)`` call site (V1.0 Step 4,
    not built yet) and is not itself read here: task relevance depends only on ``task_genome`` (see
    ``task_relevance``'s own docstring) — which candidates a record's own strategy shape corresponds to is a
    separate question, answered by ``experience_for``, never blended into this filter."""
    return tuple(experience for experience in history if task_relevance(experience, task_genome) is not TaskRelevance.IRRELEVANT)


def experience_for(candidate: Strategy, task_relevant: tuple[ExecutionExperience, ...]) -> tuple[ExecutionExperience, ...]:
    """Every task-relevant record whose own strategy shape structurally matches ``candidate`` exactly: the same
    stage-by-stage capability tuples, in the same order (``StrategyStage.capabilities`` is a deliberate
    multiset, not a set — two shapes differing only in order or repetition are different strategies), and the
    same verification posture. ``StrategyId`` is never compared (fresh every generation round, D-182);
    ``candidate`` itself is only ever read, never mutated, and its own identity is untouched."""
    shape = tuple(stage.capabilities for stage in candidate.stages)
    return tuple(
        experience for experience in task_relevant
        if experience.strategy_stage_shapes == shape and experience.strategy_verification == candidate.verification
    )
