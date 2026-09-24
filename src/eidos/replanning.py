"""``run_with_replanning`` — within-mission replanning orchestration (decisions.md D-199; V1.1 Step 4).

**A narrow sibling to ``eidos.baseline``, not a new abstraction.** ``eidos.baseline``'s own docstring already
said "a replan is a caller-supplied new plan, run by calling this again" — this module is finally that caller.
It composes only already-shipped, already-approved pieces: ``generate_candidate_strategies``/``select_strategy``
(``eidos.planning``), ``expand_strategy`` (``eidos.expansion``), ``record_attempt``/``terminal_payload_for``
(``eidos.recording``, exposed by this same step), ``project`` (``eidos.telemetry``), ``evaluate_experience``
(``eidos.memory``). It adds no new abstraction of its own beyond the one narrow decision every one of these
already-approved pieces individually left to "a future caller": *when* to run more than one attempt.

**The flow, in order**, exactly D-199's own approved design:

1. Generate the bounded candidate ``Strategy`` set exactly once, at mission start — never regenerated.
2. Select the first strategy with the caller's own configured ``Selector``.
3. Expand it into ``Plan`` v1 (``expand_strategy``'s own fresh-plan defaults: version 1, no parent, no reason).
4. ``record_attempt`` — validate, compile, bind and execute through the existing, unmodified pipeline.
5. Classify the outcome (``terminal_payload_for``, reused from ``eidos.recording``, never reimplemented).
6. Build this attempt's own honest ``ExecutionExperience`` and append it to the ``ExperienceStore`` —
   **before** any further selection, so an experience-informed selector (unmodified) can already see it.
7. If the outcome is not replan-eligible (success, or a `PLAN_REJECTED`/`RUN_REJECTED`/`HALTED`/awaiting-remote
   outcome D-199 marks permanently terminal for that attempt), record the real terminal event and stop.
8. Otherwise, if a candidate remains and the mission's own configured ``max_replans`` bound is not yet
   exhausted, select again over what remains (the just-failed candidate excluded by identity), record
   ``REPLAN_TRIGGERED`` (before the next ``PLAN_GENERATED``, D-199), expand ``Plan`` vN+1 with real lineage,
   and repeat from step 4. Otherwise record the last attempt's own real terminal event and stop.

**Why an attempt's own honest experience needs one small, well-scoped step beyond ``project`` alone.**
``project(records, plan_id=...)`` (V1.1 Step 2) correctly scopes an attempt's own steps and execution-fact
counters to *that* plan — but its own terminal-outcome fields (``mission_status``/``run_outcome``/``verified``/
``failure_cause``) can only ever reflect a *real, recorded* terminal payload tagged with that plan_id. A
replan-eligible attempt never gets one recorded for it (D-199 ruling 4: that is exactly what keeps the mission
non-terminal so the next attempt can proceed on the same log) — so, left unpatched, its own scoped projection
would honestly but unhelpfully report ``MissionStatus.CREATED``/no outcome, losing the very fact
an experience-informed selector most needs to learn from. ``terminal_payload_for(report)`` already computed the
real classification (reused, not duplicated) — ``_outcome_fields`` below only ever *reads* the four scalar
fields already sitting on that one already-computed value, and the projection is re-validated with exactly those
four replaced (``TelemetryRecord.model_validate``). Never ``model_copy``/``model_construct``: they skip the
contract's own validators, and ``eidos.state``'s own guard forbids them anywhere in ``src/eidos``.

**Fresh work-step ids across plan versions are ``expand_strategy``'s job, not this module's** (D-200, D-147): a
replanned plan's work steps are ``v{version}_stage…``, so the artifact store's write-once rule never refuses a
replan for reusing an earlier attempt's step id, and this module needs no fresh store and no artifact-key scheme.

**Zero changes to**: the ``Selector`` Protocol or any of its three implementations; ``ExperienceStore``/
any experience-informed selector implementation, ``relevant_experience``, or ``experience_for``; ``expand_
strategy`` beyond the Step 1 lineage parameters and D-200's version-namespaced ids; ``execution_record``/``project`` beyond the
Step 2 scoping parameter already delivered; the validation pipeline, the compiler, either runtime executor, the
remote-execution boundary, or the reducer beyond Step 3's own ``ReplanTriggeredPayload`` case. A fresh
``Recorder`` per attempt is required, not merely convenient — see ``record_attempt``'s own docstring for why.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from pydantic import Field, model_validator

from eidos.agents import WorkAgent
from eidos.baseline import ExecutorFactory
from eidos.capabilities import CapabilityRegistry
from eidos.contracts import AgentId, EidosModel, MissionState, MissionStatus, Plan
from eidos.expansion import PlanIdSource, expand_strategy
from eidos.memory import ExecutionExperience, ExperienceStore, evaluate_experience
from eidos.planning import (
    CandidateGenerator,
    Selector,
    SelectionOutcome,
    StrategyIdSource,
    generate_candidate_strategies,
    select_strategy,
)
from eidos.recording import Clock, IdSource, Recorder, record_attempt, terminal_payload_for
from eidos.runtime import AdmissionGuard, RunOutcome, Verifier
from eidos.state import (
    EventLog,
    IntakeResult,
    MissionCompletedPayload,
    MissionCreatedPayload,
    MissionFailedPayload,
    MissionFailureCause,
    MissionPausedPayload,
    ReplanTriggeredPayload,
)
from eidos.telemetry import TelemetryRecord, project
from eidos.validation import SystemLimits

_ELIGIBLE_CAUSES = frozenset({
    MissionFailureCause.EXECUTION_FAILED,
    MissionFailureCause.NO_RESULT,
    MissionFailureCause.VERIFICATION_FAILED,
    MissionFailureCause.VERIFICATION_INCONCLUSIVE,
})


def _is_replan_eligible(payload) -> bool:
    """D-199 ruling 1, exactly: a closed set, never touched by candidate generation or selection. A successful,
    verified completion is, as always, terminal with no replan question to ask; ``PLAN_REJECTED``/
    ``RUN_REJECTED`` are mission-level defects a different candidate cannot fix; an admission-guard halt stays
    terminal for that attempt exactly as D-176 already shipped it — never automatically retried; an awaiting
    remote pause is untouched, this mechanism only ever applies to the synchronous ``record_attempt`` path."""
    if isinstance(payload, MissionCompletedPayload):
        return not payload.verified  # FINISHED + verified=False is eligible; verified=True never is
    if isinstance(payload, MissionFailedPayload):
        return payload.cause in _ELIGIBLE_CAUSES
    return False  # MissionPausedPayload: an admission-guard halt or an awaiting remote pause, neither ever eligible


def _outcome_fields(payload) -> dict:
    """The four ``TelemetryRecord`` fields a real, plan-tagged terminal payload alone would have produced —
    read directly off ``payload`` (already computed by ``terminal_payload_for``, never re-derived from
    ``RunResult`` here) so an attempt's own experience is honest even when no terminal payload is ever actually
    recorded for it (a replan-eligible attempt, D-199 ruling 4)."""
    if isinstance(payload, MissionCompletedPayload):
        return {"mission_status": MissionStatus.COMPLETED, "run_outcome": RunOutcome.FINISHED, "verified": payload.verified, "failure_cause": None}
    if isinstance(payload, MissionPausedPayload):
        run_outcome = RunOutcome.HALTED if payload.halt is not None else RunOutcome.AWAITING
        return {"mission_status": MissionStatus.PAUSED, "run_outcome": run_outcome, "verified": None, "failure_cause": None}
    assert isinstance(payload, MissionFailedPayload), type(payload)
    never_ran = payload.cause in (MissionFailureCause.PLAN_REJECTED, MissionFailureCause.RUN_REJECTED)
    return {"mission_status": MissionStatus.FAILED, "run_outcome": None if never_ran else RunOutcome.FAILED, "verified": None, "failure_cause": payload.cause}


def _replan_cause_and_reason(payload) -> tuple[MissionFailureCause, str]:
    """The one ``(cause, reason)`` pair used both for ``ReplanTriggeredPayload`` and for the next plan's own
    deterministic ``replan_reason`` string — computed once, not twice, so the two can never silently disagree.

    A genuine gap in the existing six-member ``MissionFailureCause`` taxonomy, found by inspection, not
    assumed: none of them was ever written to mean "finished, but nothing verified it" — D-199's own eligible
    ``FINISHED``+``verified=False`` outcome is reachable only when a candidate's own ``VerificationPosture`` is
    ``NONE`` (never produced by ``RuleBasedCandidateGenerator`` for a non-empty genome, but not structurally
    forbidden by the ``CandidateGenerator`` Protocol either). Per the owner's own "do not invent a new failure
    taxonomy" instruction, this reuses ``VERIFICATION_INCONCLUSIVE`` — the closest existing member in meaning
    ("we cannot establish that this succeeded") — rather than adding a seventh cause. The
    owner accepted this mapping (D-201 item 1): no seventh cause, no optional cause."""
    if isinstance(payload, MissionFailedPayload):
        return payload.cause, payload.reason
    assert isinstance(payload, MissionCompletedPayload) and not payload.verified, payload
    return MissionFailureCause.VERIFICATION_INCONCLUSIVE, "finished without a successful VERIFY (verified is false)"


def _effective_max_replans(state: MissionState, limits: SystemLimits) -> int:
    """D-065's own already-established rule for every mission budget, applied to ``max_replans`` — never a new
    precedence rule invented for this one dimension: the contract may only tighten the system ceiling, never
    loosen it, and the ceiling alone applies when the contract omits it. ``limits.max_replans`` is always a real
    int (``SystemLimits`` has no optional fields, D-103) — no numeric default is ever invented here."""
    contract_value = state.reliability_contract.max_replans
    if contract_value is None:
        return limits.max_replans
    return min(limits.max_replans, contract_value)


class ReplanRejectionCode(StrEnum):
    """Why a mission was refused before anything ran (D-201 item 2)."""

    NO_SELECTABLE_STRATEGY = "no_selectable_strategy"  # no first strategy could be selected, so there is nothing to run


class ReplanRejection(EidosModel):
    """A mission refused before execution, returned instead of a ``ReplanRun`` (the same union-return convention as
    ``ReplayRejection`` and ``ExperienceLoadRejection``). Nothing was selected, no ``Plan`` was generated, no attempt
    ran, no event was recorded and no ``ExecutionExperience`` was appended. It carries no ``MissionFailureCause``: the
    mission never existed as far as the log is concerned, so no cause of a *failed mission* applies (D-201).

    ``outcome`` is the existing selection vocabulary (``SelectionOutcome``) saying why the first selection produced
    nothing — never ``SELECTED`` — and ``reason`` is that selection's own stated reason."""

    code: ReplanRejectionCode
    outcome: SelectionOutcome
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_the_outcome_is_a_refusal(self) -> "ReplanRejection":
        if self.outcome is SelectionOutcome.SELECTED:
            raise ValueError("a refused selection is never SELECTED")
        return self


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplanRun:
    """Everything one within-mission replanning run produced. ``plans``/``experiences`` are in attempt order,
    one entry per attempt (including the final one) — never padded, never combined into a score. ``telemetry``
    is the final attempt's own honest projection; ``log`` is the one continuous ``EventLog`` every attempt was
    recorded against."""

    log: EventLog
    telemetry: TelemetryRecord
    plans: tuple[Plan, ...]
    experiences: tuple[ExecutionExperience, ...]
    replans_used: int
    refused: tuple[IntakeResult, ...]
    discrepancies: tuple[str, ...]


def run_with_replanning(
    *,
    state: MissionState,
    limits: SystemLimits,
    registry: CapabilityRegistry,
    agents: Mapping[AgentId, WorkAgent],
    verifier: Verifier,
    admission_guard_factory: Callable[[], AdmissionGuard],
    executor_factory: ExecutorFactory,
    clock: Clock,
    ids: IdSource,
    strategy_ids: StrategyIdSource,
    plan_ids: PlanIdSource,
    candidate_generator: CandidateGenerator,
    max_candidates: int,
    selector: Selector,
    store: ExperienceStore,
    log: EventLog | None = None,
) -> ReplanRun | ReplanRejection:
    """Run ``state``'s own task genome to a conclusion, trying more than one candidate strategy in turn when an
    attempt's own outcome is replan-eligible (D-199) and the mission's own configured budget allows it.

    ``admission_guard_factory`` is called fresh for every attempt (mirrors ``ExecutorFactory``'s own existing
    factory shape) — never one guard instance reused across attempts, so a guard that itself holds any
    per-attempt state can never leak between them. ``selector`` is the caller's own already-configured
    ``Selector``, called again, unmodified, for every attempt — never a new one, never a different kind.

    Returns a ``ReplanRejection`` — recording nothing — when no first strategy can be selected (D-201 item 2);
    otherwise a ``ReplanRun``. This function raises nothing for a domain outcome.
    """
    log = log if log is not None else EventLog()
    genome = state.task_genome

    generation = generate_candidate_strategies(
        candidate_generator, genome, mission_id=state.mission_id, reliability_contract=state.reliability_contract,
        limits=limits, max_candidates=max_candidates, ids=strategy_ids,
    )
    remaining = list(generation.candidates)
    max_replans = _effective_max_replans(state, limits)

    # Refused before anything is recorded: a mission with no selectable first strategy has no plan to run, so it
    # leaves no event on the log at all and appends no experience (D-201 item 2).
    first = select_strategy(selector, tuple(remaining), genome)
    if first.outcome is not SelectionOutcome.SELECTED:
        return ReplanRejection(code=ReplanRejectionCode.NO_SELECTABLE_STRATEGY, outcome=first.outcome, reason=first.reason)
    selected = first.selected
    remaining = [c for c in remaining if c.strategy_id != selected.strategy_id]
    plan = expand_strategy(selected, ids=plan_ids)  # v1: fresh-plan defaults (version=1, no parent, no reason)

    creation = Recorder(log=log, clock=clock, ids=ids, tenant_id=state.tenant_id, mission_id=state.mission_id)
    creation.record(
        MissionCreatedPayload(task_genome=state.task_genome, reliability_contract=state.reliability_contract, execution_id=state.execution_id)
    )
    refused: list[IntakeResult] = list(creation.refused)
    discrepancies: list[str] = list(creation.discrepancies)

    plans: list[Plan] = []
    experiences: list[ExecutionExperience] = []
    replans_used = 0
    telemetry: TelemetryRecord | None = None

    while True:
        recorder, report = record_attempt(
            state=state, plan=plan, limits=limits, registry=registry, agents=agents, verifier=verifier,
            admission_guard=admission_guard_factory(), executor_factory=executor_factory,
            clock=clock, ids=ids, log=log,
        )
        refused += recorder.refused
        discrepancies += recorder.discrepancies

        payload = terminal_payload_for(report)
        scoped = project(log.records, plan_id=plan.plan_id)
        assert isinstance(scoped, TelemetryRecord), scoped
        telemetry = TelemetryRecord.model_validate({**scoped.model_dump(), **_outcome_fields(payload)})

        experience = evaluate_experience(selected, genome, telemetry, recorded_at=clock.now())
        store.append(experience)
        plans.append(plan)
        experiences.append(experience)

        next_selected = None
        if _is_replan_eligible(payload) and remaining and replans_used < max_replans:
            next_selection = select_strategy(selector, tuple(remaining), genome)
            if next_selection.outcome is SelectionOutcome.SELECTED:
                next_selected = next_selection.selected

        if next_selected is None:
            recorder.record(payload)  # the real, final terminal event for the mission
            break

        remaining = [c for c in remaining if c.strategy_id != next_selected.strategy_id]
        replan_cause, replan_reason = _replan_cause_and_reason(payload)
        next_plan = expand_strategy(
            next_selected, ids=plan_ids, version=plan.version + 1, parent_plan_id=plan.plan_id,
            replan_reason=f"{replan_cause.value}: {replan_reason}",
        )

        replan_recorder = Recorder(log=log, clock=clock, ids=ids, tenant_id=state.tenant_id, mission_id=state.mission_id)
        replan_recorder.record(ReplanTriggeredPayload(failed_plan_id=plan.plan_id, cause=replan_cause, reason=replan_reason, next_plan_id=next_plan.plan_id))
        refused += replan_recorder.refused
        discrepancies += replan_recorder.discrepancies

        replans_used += 1
        selected, plan = next_selected, next_plan

    return ReplanRun(
        log=log, telemetry=telemetry, plans=tuple(plans), experiences=tuple(experiences),
        replans_used=replans_used, refused=tuple(refused), discrepancies=tuple(discrepancies),
    )
