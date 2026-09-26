"""Record one baseline pass as events (decisions.md D-152, D-158, D-160).

``record_baseline`` runs the unchanged ``run_baseline`` with three things added around it, all through injection points that already exist:
the agents and the verifier are wrapped, so each node is started and settled in the log as it happens; an observer records the plan and each
gate with real times (D-160 item 8); and after the run the events the wrappers cannot see — nodes that were never dispatched, and the mission's
terminal event — are recorded from the run's own result. The runtime, executors, compiler, agents and verifier are not touched, and the
``BaselineReport`` is the one an unrecorded run gives.

The order of a recorded pass (D-160 item 1): ``MISSION_CREATED``; ``PLAN_GENERATED``; then ``PLAN_REJECTED`` (a gate refused) or
``PLAN_COMPILED``; then for each dispatched node ``NODE_STARTED`` followed by ``NODE_SETTLED``; then a ``NODE_SETTLED`` for every node that was
never dispatched, in plan order; and exactly one of ``MISSION_COMPLETED``, ``MISSION_FAILED`` or ``MISSION_PAUSED``. That is what one pass
produces at V0.5: with no planner and no replan, the pass's end is the mission's end (D-156).

Nothing here is silent. An event the intake refuses is kept in ``refused``; a node settled live that the run then reports differently, and a
fault inside the recorder's own observer, are kept in ``discrepancies``. A caller that sees either empty knows the log is the whole story.

**V1.1 Step 4 (D-199) exposes two lower-level pieces** ``record_baseline`` was always built from, so a caller
composing more than one attempt into one continuous log (within-mission replanning) can reuse them instead of
duplicating execution semantics: ``record_attempt`` (one attempt's own dispatch, recorded live, but never the
mission's terminal event) and ``terminal_payload_for`` (the pure classification of what that terminal event
would be, given a ``BaselineReport``). ``record_baseline`` itself is unchanged in behavior — it is now a thin
composition of ``MISSION_CREATED`` + ``record_attempt`` + ``_finish`` (which itself is now just
``recorder.record(terminal_payload_for(report))``), not a rewrite.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from eidos.agents import WorkAgent
from eidos.baseline import BaselineReport, BaselineStage, ExecutorFactory, run_baseline
from eidos.capabilities import CapabilityRegistry
from eidos.contracts import AgentId, MissionState, Plan
from eidos.runtime import (
    AdmissionGuard,
    NodeStatus,
    PriorOutcomes,
    RunOutcome,
    RunRejection,
    RunResult,
    Verifier,
)
from eidos.state import (
    EventLog,
    IntakeResult,
    MissionCompletedPayload,
    MissionCreatedPayload,
    MissionFailedPayload,
    MissionFailureCause,
    MissionPausedPayload,
    NodeSettledPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    PlanRejectedPayload,
    PlanRejectionStage,
    RejectionReason,
)
from eidos.validation import SystemLimits

from .adapters import ModelCallTracker, RecordingAgent, RecordingVerifier
from .ports import Clock, IdSource
from .recorder import Recorder


@dataclass(frozen=True, slots=True, kw_only=True)
class RecordedRun:
    """What one recorded pass produced. ``refused`` and ``discrepancies`` are empty when the log is the whole story."""

    report: BaselineReport
    log: EventLog
    refused: tuple[IntakeResult, ...]
    discrepancies: tuple[str, ...]


def _reasons(report) -> tuple[RejectionReason, ...]:
    return tuple(RejectionReason(code=v.code.value, message=v.message) for v in report.violations)


class _RecorderObserver:
    """Records the plan and each gate. A fault in here is contained by the runner, so it is turned into a visible discrepancy instead."""

    def __init__(self, recorder: Recorder):
        self.recorder = recorder
        self._plan: Plan | None = None

    def plan_received(self, plan: Plan) -> None:
        try:
            self._plan = plan
            self.recorder.record(PlanGeneratedPayload(plan=plan))
        except Exception as error:  # noqa: BLE001
            self.recorder.note_discrepancy(f"the recorder's observer could not record the plan: {type(error).__name__}: {error}")

    def gate_settled(self, stage: BaselineStage, report) -> None:
        try:
            plan = self._plan
            passed = report.accepted if stage is BaselineStage.VALIDATION else report.succeeded
            if not passed:
                self.recorder.record(PlanRejectedPayload(plan_id=plan.plan_id, stage=PlanRejectionStage(stage.value), reasons=_reasons(report)))
            elif stage is BaselineStage.BINDING:  # validated, compiled and bound: ready to run
                self.recorder.record(PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version))
        except Exception as error:  # noqa: BLE001
            self.recorder.note_discrepancy(f"the recorder's observer could not record the {stage.value} gate: {type(error).__name__}: {error}")


_CAUSE = MappingProxyType({
    NodeStatus.FAILED: MissionFailureCause.EXECUTION_FAILED,
    NodeStatus.NO_RESULT: MissionFailureCause.NO_RESULT,
    NodeStatus.VERIFICATION_FAILED: MissionFailureCause.VERIFICATION_FAILED,
    NodeStatus.VERIFICATION_INCONCLUSIVE: MissionFailureCause.VERIFICATION_INCONCLUSIVE,
})


def terminal_payload_for(report: BaselineReport) -> MissionFailedPayload | MissionCompletedPayload | MissionPausedPayload:
    """What the mission's own terminal event would be for ``report`` — pure, never records anything, never reads
    a log. Exposed (V1.1 Step 4, D-199) so a caller composing more than one attempt into one continuous log
    (within-mission replanning) can classify an attempt's outcome *before* deciding whether to actually record
    it as terminal, or to record ``ReplanTriggeredPayload`` instead. Exactly the classification ``_finish``
    already made internally; nothing about it changes here."""
    plan_id = report.plan_id
    if report.stopped_at is not None:
        stage = report.stopped_at
        return MissionFailedPayload(plan_id=plan_id, cause=MissionFailureCause.PLAN_REJECTED, reason=f"the plan was refused at the {stage.value} gate")
    run = report.run
    if isinstance(run, RunRejection):
        return MissionFailedPayload(plan_id=plan_id, cause=MissionFailureCause.RUN_REJECTED, reason=f"{run.code.value}: {run.message}")
    assert isinstance(run, RunResult)
    if run.outcome is RunOutcome.HALTED:
        return MissionPausedPayload(plan_id=plan_id, halt=run.halt)
    if run.outcome is RunOutcome.FINISHED:
        return MissionCompletedPayload(plan_id=plan_id, verified=run.verified)
    # FAILED: the cause is the first node, in plan order, that did not succeed for a reason of its own (a skipped node only follows one)
    root = next((r for r in run.results if r.status in _CAUSE), None)
    cause = _CAUSE[root.status] if root is not None else MissionFailureCause.EXECUTION_FAILED
    reason = root.reason if root is not None else "the run did not succeed"
    return MissionFailedPayload(plan_id=plan_id, cause=cause, reason=reason)


def _record_settled_nodes(recorder: Recorder, report: BaselineReport) -> None:
    """``NODE_SETTLED`` for every node the run reports that was not already settled live (D-160 item 1) — real
    facts about this one attempt, recorded unconditionally, whatever the mission does next. A no-op when the
    plan or the run itself was refused before anything could dispatch (``report.run`` is not a ``RunResult``)."""
    run = report.run
    if not isinstance(run, RunResult):
        return
    plan_id = report.plan_id
    dispatched = set(run.dispatched)
    for result in run.results:
        live = recorder.live_result(result.step_id)
        if live is not None:  # already recorded, as it happened; check the run agrees
            if live != result:
                recorder.note_discrepancy(f"node {str(result.step_id)!r} was settled live as {live.status.value} but the run reports {result.status.value}")
            continue
        was_dispatched = result.step_id in dispatched
        seen = recorder.observation(result.step_id)  # only a node whose port ran was ever observed
        recorder.record(
            NodeSettledPayload(
                plan_id=plan_id,
                result=result,
                dispatched=was_dispatched,
                duration_ms=seen.duration_ms if seen is not None else None,
                model_calls=seen.model_calls if seen is not None else (),
                tool_calls=recorder.tool_calls(result.step_id),
                retrievals=recorder.retrievals(result.step_id),
                citations=recorder.citations(result.step_id),
            )
        )


def _finish(recorder: Recorder, report: BaselineReport) -> None:
    recorder.record(terminal_payload_for(report))


def record_attempt(
    *,
    state: MissionState,
    plan: Plan,
    limits: SystemLimits,
    registry: CapabilityRegistry,
    agents: Mapping[AgentId, WorkAgent],
    verifier: Verifier,
    admission_guard: AdmissionGuard,
    executor_factory: ExecutorFactory,
    clock: Clock,
    ids: IdSource,
    log: EventLog,
    prior: PriorOutcomes | None = None,
    tracker: ModelCallTracker | None = None,
) -> tuple[Recorder, BaselineReport]:
    """One attempt's own dispatch of ``plan``, recorded live against ``log`` (already holding ``MISSION_CREATED``)
    — every ``NODE_SETTLED`` this attempt produces, but *never* the mission's own terminal event; that decision
    belongs to the caller (``record_baseline``'s own ``_finish`` for the single-attempt case below; V1.1's
    within-mission replan orchestration otherwise, which may record ``ReplanTriggeredPayload`` instead of a
    terminal payload for a replan-eligible outcome, D-199). A fresh ``Recorder`` every call, deliberately: its
    own ``live_result``/``observation`` bookkeeping is keyed by bare ``StepId``, not ``(plan_id, StepId)``, so
    reusing one across two different plans that share a step id (``expand_strategy``'s ``verify`` control step
    has the same id in every plan version, D-200; a hand-authored plan may share any) would contaminate one
    attempt's own facts with another's. ``log``/``clock``/``ids`` are still the caller's own shared objects, so
    ordering and identity stay continuous across every attempt in one mission."""
    tracker = ModelCallTracker() if tracker is None else tracker
    recorder = Recorder(log=log, clock=clock, ids=ids, tenant_id=state.tenant_id, mission_id=state.mission_id)
    report = run_baseline(
        state=state,
        plan=plan,
        limits=limits,
        registry=registry,
        agents={agent_id: RecordingAgent(agent_id, agent, recorder, tracker) for agent_id, agent in agents.items()},
        verifier=RecordingVerifier(verifier, recorder),
        admission_guard=admission_guard,
        executor_factory=executor_factory,
        prior=prior,
        observer=_RecorderObserver(recorder),
    )
    _record_settled_nodes(recorder, report)
    return recorder, report


def record_baseline(
    *,
    state: MissionState,
    plan: Plan,
    limits: SystemLimits,
    registry: CapabilityRegistry,
    agents: Mapping[AgentId, WorkAgent],
    verifier: Verifier,
    admission_guard: AdmissionGuard,
    executor_factory: ExecutorFactory,
    clock: Clock,
    ids: IdSource,
    prior: PriorOutcomes | None = None,
    log: EventLog | None = None,
    tracker: ModelCallTracker | None = None,
) -> RecordedRun:
    """Run ``plan`` once, exactly as ``run_baseline`` would, and record it — ``MISSION_CREATED``, then one
    attempt (``record_attempt``), then its own terminal event (``_finish``). Pass the same ``tracker`` to the
    ``RecordingModel`` the agents use."""
    log = EventLog() if log is None else log
    creation = Recorder(log=log, clock=clock, ids=ids, tenant_id=state.tenant_id, mission_id=state.mission_id)
    creation.record(
        MissionCreatedPayload(task_genome=state.task_genome, reliability_contract=state.reliability_contract, execution_id=state.execution_id)
    )
    recorder, report = record_attempt(
        state=state, plan=plan, limits=limits, registry=registry, agents=agents, verifier=verifier,
        admission_guard=admission_guard, executor_factory=executor_factory, clock=clock, ids=ids,
        log=log, prior=prior, tracker=tracker,
    )
    _finish(recorder, report)
    return RecordedRun(
        report=report, log=log,
        refused=creation.refused + recorder.refused, discrepancies=creation.discrepancies + recorder.discrepancies,
    )
