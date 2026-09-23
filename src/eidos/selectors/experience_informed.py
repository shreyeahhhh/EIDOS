"""``ExperienceInformedSelector`` — a fourth ``Selector`` implementation, informed by measured execution
experience (decisions.md D-198; V1.0 Step 4).

**The first point where EIDOS's V1.0 loop becomes operational**: candidate strategies, plus relevant execution
experience, flow into a choice — never the reverse. This module never generates a candidate, never alters
feasibility, never expands a ``Strategy`` into a ``Plan``, never validates a ``Plan``, and never executes
anything. It only ever chooses among the ``candidates`` it is given, exactly like ``DeterministicSelector`` and
``ModelAssistedSelector`` before it — the ``Selector`` Protocol and ``select_strategy``'s own orchestration
boundary are completely unchanged (D-186, D-187).

**Cold start (D-198 ruling 7).** When *no* candidate has any structurally-matched, task-relevant experience at
all, this selector defers entirely to its own injected ``fallback`` — genuinely, by calling
``fallback.select(candidates, task_genome)``, never by re-deriving an equivalent answer some other way, so the
guarantee holds for whatever ``Selector`` a caller actually configures as the fallback, not only for
``DeterministicSelector`` specifically. No relevant experience is never a ``SelectorFailure``.

**Relevance is never reimplemented here.** ``eidos.memory.relevant_experience``/``experience_for`` (V1.0 Step 2)
are called exactly as built — this module adds no new comparison, no embedding, no scalar similarity score.

**The selection algorithm (D-198 ruling 8) — a lexicographic tuple, never a scalar, mirroring
``structural_cost``'s own "never weighted or combined" discipline (D-188) one layer up.** For each candidate,
using only its own structurally-matched, task-relevant records:

- **Tier 0** — at least one record with ``mission_status == COMPLETED and verified is True``. Broken, in order,
  by: more verified successes (a plain count); fewer observed non-successes; a lower **sum** (never a mean) of
  ``execution_time_used_ms`` across its own verified-success records, used only once the first two are already
  tied; the existing ``structural_cost`` as a final tie-break.
- **Tier 1** — no relevant record at all. Ranked *above* Tier 2 deliberately: absence of evidence is neutral;
  observed failure is negative evidence and should count against a candidate more than having none. Its own
  comparison value is ``structural_cost`` directly — a plain function call, never a recursive selector call.
- **Tier 2** — relevant records exist, none is a verified success. Broken only by fewer observed non-successes,
  then ``structural_cost``. Deliberately not distinguishing by ``failure_cause``: ranking one failure type
  against another would need a subjective severity judgment with no basis in directly observed facts.

No scalar candidate score, no quality/confidence value, no failure-severity weighting, no LLM judgment, no
embeddings, no reinforcement learning, no optimization framework, no strategy signature, and no ``strategy_id``
ever added to any existing contract — the Strategy<->execution linkage stays exactly where V1.0 Step 1 put it,
inside ``ExecutionExperience`` alone.

**Dependency direction**: this module may depend on ``eidos.memory`` (``ExperienceStore``, the Step 2 relevance
functions) and ``eidos.planning`` (``Selector``, ``Strategy``, ``structural_cost``) — ``eidos.memory`` itself
depends on nothing in ``eidos.selectors`` (checked by ``eidos.memory``'s own guard tests, unchanged).
"""

from dataclasses import dataclass

from eidos.contracts import MissionStatus, TaskGenome
from eidos.memory import ExecutionExperience, ExperienceStore, experience_for, relevant_experience
from eidos.planning import SelectedCandidate, Selector, SelectorChoice, Strategy, structural_cost


def _is_verified_success(experience: ExecutionExperience) -> bool:
    return experience.mission_status is MissionStatus.COMPLETED and experience.verified is True


def _tiered_key(candidate: Strategy, matched: tuple[ExecutionExperience, ...]) -> tuple:
    """The comparison value for one candidate — a fixed-shape tuple, compared lexicographically by ``min()``
    exactly as ``DeterministicSelector`` already compares ``structural_cost`` (D-188)."""
    successes = tuple(experience for experience in matched if _is_verified_success(experience))
    non_successes = tuple(experience for experience in matched if not _is_verified_success(experience))

    if successes:
        tier = 0
    elif not matched:
        tier = 1
    else:
        tier = 2

    success_count = -len(successes)  # more successes sorts earlier
    non_success_count = len(non_successes)  # fewer non-successes sorts earlier
    verified_cost = sum(experience.execution_time_used_ms for experience in successes)  # a sum, never a mean

    return (tier, success_count, non_success_count, verified_cost, structural_cost(candidate))


@dataclass(frozen=True, slots=True, kw_only=True)
class ExperienceInformedSelector:
    """A ``Selector`` (``eidos.planning.selector.Selector``) that prefers candidates with directly observed,
    verified-successful historical experience over untested or historically non-successful ones. Both ``store``
    and ``fallback`` are required — no ambient default (D-103's own "no silent defaults" discipline, matching
    ``ModelAssistedSelector``'s identical stance)."""

    store: ExperienceStore
    fallback: Selector

    def select(self, candidates: tuple[Strategy, ...], task_genome: TaskGenome) -> SelectorChoice:
        history = relevant_experience(candidates, task_genome, self.store.all())
        matched_of = {candidate.strategy_id: experience_for(candidate, history) for candidate in candidates}

        if all(not matched for matched in matched_of.values()):
            return self.fallback.select(candidates, task_genome)  # genuine cold start: defer entirely

        chosen = min(candidates, key=lambda candidate: _tiered_key(candidate, matched_of[candidate.strategy_id]))
        return SelectedCandidate(strategy_id=chosen.strategy_id)
