"""Within-mission replanning, end to end, with real components (decisions.md D-199; V1.1 Step 4).

An integration proof, not new architecture: every stage is the real, already-shipped implementation
(``RuleBasedCandidateGenerator``, ``select_strategy`` over the caller's own real ``DeterministicSelector``/
``ExperienceInformedSelector``, ``expand_strategy``, ``record_attempt``, ``terminal_payload_for``, ``project``,
``evaluate_experience``, ``JsonlExperienceStore``) over real V0.4 agents and a scripted model (D-136). The only
things standing in for anything are the model and the recording layer's existing deterministic test doubles
(``FixedClock``), exactly as ``test_v1_adaptive_loop_integration.py`` (V1.0 Step 6) already uses them.

Found by direct inspection, not assumed, while designing this suite: a *failure* on the selector's own first
pick cannot be made by citation content alone, nor by an admission-guard halt alone. ``DeterministicSelector``
always prefers a parallel shape (fewest stages); a parallel shape's own ``VERIFY`` always sees at least as much
evidence as a linear shape's narrower final-stage view, so no citation script can make parallel fail while linear
succeeds; and an admission-guard halt (the topology-driven mechanism Benchmark 2 already uses) is explicitly
never replan-eligible (D-199 ruling 1). ``fail_first_n_calls`` (a one-shot model outage) is the one mechanism that
makes an *eligible* ``EXECUTION_FAILED`` land on parallel first and lets linear then succeed — see
``eidos_replanning_factories.fail_first_n_calls``.
"""

from dataclasses import dataclass, field

import pytest

from uuid import uuid4

from eidos.contracts import MissionEventType, MissionStatus, PlanStepKind, StrategyId
from eidos.memory import JsonlExperienceStore
from eidos.planning import (
    DeterministicSelector,
    SelectedCandidate,
    Selector,
    SelectorChoice,
    SelectorFailure,
    SelectorFailureKind,
    StrategyShape,
    StrategyStage,
    VerificationPosture,
)
from eidos.recording import UuidEventIds, record_baseline
from eidos.runtime import NodeStatus, RunOutcome, SequentialExecutor
from eidos.state import (
    EventLog,
    MissionCompletedPayload,
    MissionFailureCause,
    NodeSettledPayload,
    PlanGeneratedPayload,
    ReplanTriggeredPayload,
    execution_record,
    replay,
)
from eidos.telemetry import project

from eidos_mission_factories import make_mission
from eidos_planning_factories import GENEROUS_LIMITS
from eidos_recording_factories import FixedClock
from eidos_replanning_factories import (
    InconclusiveOnFirstVerify,
    ScriptedCalls,
    always_fails,
    build_agents,
    empty_response,
    fail_first_n_calls,
    replan,
    under_cited_first_n_calls,
    uniformly_sufficient,
)
from eidos_runtime_factories import admit_all, halt_when
from eidos_v04_registry import make_registry
from eidos_validation_factories import make_system_limits

_TWO = ("research", "cost")
_THREE = ("research", "cost", "security")


@dataclass
class SpySelector:
    """Wraps a real ``Selector`` unchanged, recording exactly what it was asked and what the store held at the
    moment of each call — the only way to observe candidate exclusion (E) and experience-before-selection
    ordering (I) directly, from outside, without modifying either the selector or the orchestrator."""

    inner: Selector
    store: JsonlExperienceStore
    calls: list = field(default_factory=list)  # one entry per call: (tuple of candidate strategy_ids, store size)

    def select(self, candidates, task_genome) -> SelectorChoice:
        self.calls.append((tuple(c.strategy_id for c in candidates), len(self.store.all())))
        return self.inner.select(candidates, task_genome)


def _store(tmp_path, name="experience.jsonl"):
    store = JsonlExperienceStore.open(tmp_path / name)
    assert isinstance(store, JsonlExperienceStore)
    return store


def _shape(plan_or_experience) -> tuple[tuple[str, ...], ...]:
    """The structural shape of whatever was executed, from the experience the run itself recorded."""
    return tuple(tuple(stage) for stage in plan_or_experience.strategy_stage_shapes)


# --- A: first strategy succeeds -> exactly one attempt, no replan -----------------------------------------------


def test_a_first_attempt_that_succeeds_is_the_only_attempt_and_never_replans(tmp_path):
    state = make_mission(capabilities=_TWO, seed=1)
    result = replan(state, selector=DeterministicSelector(), store=_store(tmp_path), respond=uniformly_sufficient)
    assert len(result.plans) == 1 and len(result.experiences) == 1
    assert result.replans_used == 0
    assert result.telemetry.mission_status is MissionStatus.COMPLETED and result.telemetry.verified is True
    assert result.plans[0].version == 1 and result.plans[0].parent_plan_id is None and result.plans[0].replan_reason is None
    assert not any(isinstance(r.payload, ReplanTriggeredPayload) for r in result.log.records)


# --- B: first fails, second succeeds -----------------------------------------------------------------------------


def test_b_first_fails_second_succeeds_two_plans_with_real_lineage_and_two_experiences(tmp_path):
    state = make_mission(capabilities=_TWO, seed=2)
    store = _store(tmp_path)
    result = replan(state, selector=DeterministicSelector(), store=store, respond=fail_first_n_calls(1))

    assert len(result.plans) == 2 and len(result.experiences) == 2
    v1, v2 = result.plans
    assert (v1.version, v1.parent_plan_id, v1.replan_reason) == (1, None, None)
    assert v2.version == 2 and v2.parent_plan_id == v1.plan_id
    assert v2.replan_reason and v2.replan_reason.startswith("execution_failed:")  # deterministic, derived from the real cause
    assert result.replans_used == 1
    assert result.telemetry.mission_status is MissionStatus.COMPLETED and result.telemetry.verified is True
    assert len(store.all()) == 2  # both attempts' experiences persisted, not only the winner's

    first, second = result.experiences
    assert (first.mission_status, first.failure_cause) == (MissionStatus.FAILED, MissionFailureCause.EXECUTION_FAILED)
    assert (second.mission_status, second.verified) == (MissionStatus.COMPLETED, True)
    assert _shape(first) != _shape(second)  # a genuinely different strategy was tried, not the same one twice


# --- C: first fails, second fails -> bounded, final outcome is the second attempt's own --------------------------


def test_c_every_candidate_failing_stops_bounded_with_the_last_attempts_own_real_outcome(tmp_path):
    state = make_mission(capabilities=_TWO, seed=3)  # exactly two candidates: linear and parallel
    result = replan(state, selector=DeterministicSelector(), store=_store(tmp_path), respond=always_fails)
    assert len(result.plans) == 2  # no third attempt: only two candidates exist
    assert result.replans_used == 1
    assert (result.telemetry.mission_status, result.telemetry.run_outcome) == (MissionStatus.FAILED, RunOutcome.FAILED)
    assert result.telemetry.failure_cause is MissionFailureCause.EXECUTION_FAILED  # the LAST attempt's own, never a synthetic cause
    assert all(e.mission_status is MissionStatus.FAILED for e in result.experiences)


# --- D: three candidates, max_replans=1 -> exactly two attempts --------------------------------------------------


def test_d_max_replans_is_respected_exactly_even_when_untried_candidates_remain(tmp_path):
    state = make_mission(capabilities=_THREE, seed=4)  # linear, parallel and staged: three candidates
    limits = make_system_limits(max_replans=1)
    result = replan(state, selector=DeterministicSelector(), store=_store(tmp_path), respond=always_fails, limits=limits)
    assert len(result.plans) == 2  # first attempt + exactly one replan, not three attempts
    assert result.replans_used == 1


def test_d_a_contract_that_tightens_max_replans_is_respected_below_the_system_ceiling(tmp_path):
    state = make_mission(capabilities=_THREE, seed=5, max_replans=0)  # the contract forbids any replan at all
    result = replan(state, selector=DeterministicSelector(), store=_store(tmp_path), respond=always_fails)
    assert len(result.plans) == 1 and result.replans_used == 0


# --- E: a failed strategy never reappears in a later selector call ---------------------------------------------


def test_e_a_previously_attempted_strategy_never_appears_in_a_later_selector_candidate_tuple(tmp_path):
    state = make_mission(capabilities=_THREE, seed=6)
    store = _store(tmp_path)
    spy = SpySelector(inner=DeterministicSelector(), store=store)
    result = replan(state, selector=spy, store=store, respond=always_fails, limits=make_system_limits(max_replans=2))
    assert len(result.plans) == 3  # all three candidates attempted, one per attempt

    seen_across_calls = [set(ids) for ids, _size in spy.calls]
    assert len(seen_across_calls) >= 2
    # every later call's candidates are strictly a subset of every earlier call's: exclusion only ever shrinks the set
    for earlier, later in zip(seen_across_calls, seen_across_calls[1:]):
        assert later < earlier, "a later selector call was offered a candidate an earlier call had already ruled out"
    # and no candidate id is ever attempted twice: each experience names a distinct strategy_id
    strategy_ids = [e.strategy_id for e in result.experiences]
    assert len(set(strategy_ids)) == len(strategy_ids)


# --- F: FINISHED + verified=False triggers a replan --------------------------------------------------------------


@dataclass(frozen=True)
class _UnverifiedThenVerifiedGenerator:
    """The one place a ``VerificationPosture.NONE`` strategy is reachable at all: ``RuleBasedCandidateGenerator``
    never produces one for a non-empty genome, but the ``CandidateGenerator`` Protocol does not forbid it."""

    def generate(self, task_genome):
        capabilities = tuple(task_genome.required_capabilities)
        return (
            StrategyShape(stages=(StrategyStage(capabilities=capabilities),), verification=VerificationPosture.NONE, rationale="test: no verification"),
            StrategyShape(
                stages=tuple(StrategyStage(capabilities=(c,)) for c in capabilities),
                verification=VerificationPosture.FINAL, rationale="test: linear, verified",
            ),
        )


def test_f_finished_but_unverified_triggers_a_replan(tmp_path):
    state = make_mission(capabilities=_TWO, seed=7)
    result = replan(
        state, selector=DeterministicSelector(), store=_store(tmp_path), respond=uniformly_sufficient,
        candidate_generator=_UnverifiedThenVerifiedGenerator(),
    )
    assert len(result.plans) == 2 and result.replans_used == 1
    first, second = result.experiences
    assert (first.mission_status, first.verified) == (MissionStatus.COMPLETED, False)  # completed, but not verified
    assert first.strategy_verification is VerificationPosture.NONE
    assert (second.mission_status, second.verified) == (MissionStatus.COMPLETED, True)
    assert result.plans[1].parent_plan_id == result.plans[0].plan_id


# --- G: an admission-guard halt never triggers a replan ---------------------------------------------------------


def test_g_an_admission_guard_halt_stays_terminal_for_that_attempt_and_never_replans(tmp_path):
    state = make_mission(capabilities=_TWO, seed=8)
    result = replan(
        state, selector=DeterministicSelector(), store=_store(tmp_path), respond=uniformly_sufficient,
        admission_guard_factory=lambda: halt_when(lambda request: request.rank_in_level >= 1, "test: no concurrent dispatch"),
    )
    assert len(result.plans) == 1 and result.replans_used == 0  # DeterministicSelector picks parallel; parallel halts; no second attempt
    assert (result.telemetry.mission_status, result.telemetry.run_outcome) == (MissionStatus.PAUSED, RunOutcome.HALTED)
    assert not any(isinstance(r.payload, ReplanTriggeredPayload) for r in result.log.records)
    # the halt is still recorded as real experience: V1.0's own core mechanism depends on exactly this fact
    assert result.experiences[0].run_outcome is RunOutcome.HALTED


# --- I: experience is visible in the store before the next selector call -----------------------------------------


def test_i_the_failed_attempts_experience_is_already_in_the_store_when_the_next_selection_is_made(tmp_path):
    # Three candidates, not two: select_strategy bypasses the Selector entirely when exactly one candidate is
    # left (D-187), so with two candidates the replan's own selection would never reach the spy at all.
    state = make_mission(capabilities=_THREE, seed=9)
    store = _store(tmp_path)
    spy = SpySelector(inner=DeterministicSelector(), store=store)
    result = replan(state, selector=spy, store=store, respond=fail_first_n_calls(1))
    assert len(result.plans) == 2
    store_sizes = [size for _ids, size in spy.calls]
    assert len(store_sizes) == 2  # both selections (3 candidates, then 2) reached the selector
    assert store_sizes[0] == 0  # the first call: nothing has run yet
    assert store_sizes[1] == 1  # the second: the just-failed attempt's own experience is already there


# --- J: event continuity — one mission, one log, every plan version, REPLAN_TRIGGERED before the next plan -------


def test_j_one_continuous_log_every_plan_version_and_replan_triggered_precedes_the_next_plan_generated(tmp_path):
    state = make_mission(capabilities=_TWO, seed=10)
    result = replan(state, selector=DeterministicSelector(), store=_store(tmp_path), respond=fail_first_n_calls(1))
    records = result.log.records

    assert {r.event.mission_id for r in records} == {state.mission_id}
    assert [r.event.sequence for r in records] == list(range(1, len(records) + 1))  # one unbroken, gapless sequence

    generated = [(i, r.payload.plan.plan_id) for i, r in enumerate(records) if isinstance(r.payload, PlanGeneratedPayload)]
    assert [plan_id for _i, plan_id in generated] == [p.plan_id for p in result.plans]  # every version represented, in order

    triggered = [(i, r.payload) for i, r in enumerate(records) if isinstance(r.payload, ReplanTriggeredPayload)]
    assert len(triggered) == 1
    trigger_index, trigger = triggered[0]
    assert trigger.failed_plan_id == result.plans[0].plan_id and trigger.next_plan_id == result.plans[1].plan_id
    second_generated_index = generated[1][0]
    assert trigger_index < second_generated_index  # REPLAN_TRIGGERED strictly before the next PLAN_GENERATED

    types = [r.event.type for r in records]
    assert types.count(MissionEventType.MISSION_CREATED) == 1  # never re-created per attempt
    terminal_types = {MissionEventType.MISSION_COMPLETED, MissionEventType.MISSION_FAILED, MissionEventType.MISSION_PAUSED}
    assert sum(1 for t in types if t in terminal_types) == 1  # exactly one terminal event, only after the last attempt
    assert types[-1] in terminal_types


# --- K: replay reproduces the live result ---------------------------------------------------------------------


def test_k_the_complete_replan_log_replays_to_the_same_state_and_derived_records_as_the_live_run(tmp_path):
    state = make_mission(capabilities=_TWO, seed=11)
    result = replan(state, selector=DeterministicSelector(), store=_store(tmp_path), respond=fail_first_n_calls(1))

    live = EventLog.restore(result.log.records)
    assert isinstance(live, EventLog), live  # a restored log, never a rejection
    replayed = replay(result.log.records)
    assert replayed.rejection is None
    assert replayed.state == live.state
    assert replayed.state.replans_used == 1
    assert replayed.state.status is MissionStatus.COMPLETED

    # the derived records, scoped per attempt, are reproducible from the log alone (no live objects needed)
    for plan in result.plans:
        first = project(result.log.records, plan_id=plan.plan_id)
        second = project(list(result.log.records), plan_id=plan.plan_id)
        assert first == second
    winner = execution_record(result.log.records)
    assert winner.plan_id == result.plans[-1].plan_id and winner.plan_version == 2


# --- experience gets the attempt's real outcome, not a placeholder CREATED ----------------------------------------


def test_an_abandoned_attempts_experience_reports_its_real_outcome_never_a_placeholder_created(tmp_path):
    state = make_mission(capabilities=_TWO, seed=12)
    result = replan(state, selector=DeterministicSelector(), store=_store(tmp_path), respond=fail_first_n_calls(1))
    abandoned = result.experiences[0]
    assert abandoned.mission_status is not MissionStatus.CREATED
    assert abandoned.run_outcome is RunOutcome.FAILED
    # ...while the log itself honestly recorded no terminal payload for that abandoned plan at all
    assert not any(
        r.event.type in {MissionEventType.MISSION_FAILED, MissionEventType.MISSION_PAUSED}
        and getattr(r.payload, "plan_id", None) == result.plans[0].plan_id
        for r in result.log.records
    )


def test_a_replan_reuses_the_callers_own_selector_unmodified_across_every_attempt(tmp_path):
    state = make_mission(capabilities=_THREE, seed=13)
    store = _store(tmp_path)
    spy = SpySelector(inner=DeterministicSelector(), store=store)
    replan(state, selector=spy, store=store, respond=always_fails, limits=make_system_limits(max_replans=2))
    assert len(spy.calls) >= 2  # called again for a replan, the very same object each time


# --- D-200 / D-147: a replan after work steps already stored artifacts -----------------------------------------
#
# The case D-147's write-once guard would have refused had `expand_strategy` reused version 1's step ids for
# version 2: attempt 1's work genuinely ran and stored `artifact:stage…`; the replan must run *fresh* work under
# `v2_stage…` ids instead of being refused (`step_id_reused`) before any model call.


def _work_results(result, plan):
    """Every work-node settlement recorded for ``plan``, in log order."""
    return [
        r.payload.result for r in result.log.records
        if isinstance(r.payload, NodeSettledPayload) and r.payload.plan_id == plan.plan_id
        and r.payload.result.kind is PlanStepKind.AGENT
    ]


_EVERY_ELIGIBLE_OUTCOME_AFTER_ARTIFACTS_WERE_STORED = {
    # every work step succeeded and stored its artifact; only VERIFY failed
    "verification_failed": dict(
        script=lambda: under_cited_first_n_calls(2), cause=MissionFailureCause.VERIFICATION_FAILED, status=MissionStatus.FAILED, verified=None,
    ),
    # every work step succeeded and stored its artifact; VERIFY could not establish success
    "verification_inconclusive": dict(
        script=lambda: ScriptedCalls(()), verifier_wrapper=InconclusiveOnFirstVerify,
        cause=MissionFailureCause.VERIFICATION_INCONCLUSIVE, status=MissionStatus.FAILED, verified=None,
    ),
    # the run finished with nothing verifying it (no VERIFY step at all)
    "finished_unverified": dict(
        script=lambda: ScriptedCalls(()), candidate_generator=_UnverifiedThenVerifiedGenerator(),
        cause=None, status=MissionStatus.COMPLETED, verified=False,
    ),
    # the first work step succeeded and stored its artifact; the second one's model call failed
    "execution_failed": dict(
        script=lambda: ScriptedCalls((uniformly_sufficient, always_fails)),
        cause=MissionFailureCause.EXECUTION_FAILED, status=MissionStatus.FAILED, verified=None,
    ),
    # the first work step succeeded and stored its artifact; the second one produced nothing usable
    "no_result": dict(
        script=lambda: ScriptedCalls((uniformly_sufficient, empty_response)),
        cause=MissionFailureCause.NO_RESULT, status=MissionStatus.FAILED, verified=None,
    ),
}


@pytest.mark.parametrize("scenario", sorted(_EVERY_ELIGIBLE_OUTCOME_AFTER_ARTIFACTS_WERE_STORED))
def test_a_replan_after_stored_artifacts_runs_fresh_work_under_fresh_step_ids_and_completes(tmp_path, scenario):
    spec = _EVERY_ELIGIBLE_OUTCOME_AFTER_ARTIFACTS_WERE_STORED[scenario]
    script = spec["script"]()
    state = make_mission(capabilities=_TWO, seed=20)
    result = replan(
        state, selector=DeterministicSelector(), store=_store(tmp_path), respond=script,
        verifier_wrapper=spec.get("verifier_wrapper"), candidate_generator=spec.get("candidate_generator"),
    )

    # the mission recovered inside itself: two plan versions, one replan, real completion
    assert len(result.plans) == 2 and result.replans_used == 1
    v1, v2 = result.plans
    assert v2.parent_plan_id == v1.plan_id and v2.version == 2
    assert (result.telemetry.mission_status, result.telemetry.verified) == (MissionStatus.COMPLETED, True)

    # attempt 1 really ran work and its artifact was really stored, then it ended for the expected eligible reason
    first, second = result.experiences
    assert (first.mission_status, first.failure_cause, first.verified) == (spec["status"], spec["cause"], spec["verified"])
    v1_work = _work_results(result, v1)
    assert any(r.status is NodeStatus.SUCCEEDED and r.artifact is not None for r in v1_work), "no artifact was stored by attempt 1"
    assert all(str(r.step_id).startswith("stage") for r in v1_work)  # version 1 keeps the D-194 ids

    # attempt 2 used fresh, version-namespaced step ids, and its work actually ran and succeeded — never refused by D-147
    v2_work = _work_results(result, v2)
    assert v2_work and all(str(r.step_id).startswith("v2_stage") for r in v2_work)
    assert all(r.status is NodeStatus.SUCCEEDED and str(r.artifact).startswith("artifact:v2_stage") for r in v2_work)
    assert {r.step_id for r in v1_work}.isdisjoint({r.step_id for r in v2_work})
    assert {r.artifact for r in v1_work if r.artifact}.isdisjoint({r.artifact for r in v2_work})
    assert not any("step_id_reused" in (getattr(r.payload, "result", None) and r.payload.result.reason or "") for r in result.log.records)

    # the recorded REPLAN_TRIGGERED names both plans, the real cause, and is the very reason the next plan carries
    (trigger,) = [r.payload for r in result.log.records if isinstance(r.payload, ReplanTriggeredPayload)]
    expected_cause = spec["cause"] or MissionFailureCause.VERIFICATION_INCONCLUSIVE  # finished-unverified reuses the closest member
    assert (trigger.failed_plan_id, trigger.next_plan_id, trigger.cause) == (v1.plan_id, v2.plan_id, expected_cause)
    assert v2.replan_reason == f"{trigger.cause.value}: {trigger.reason}"

    # both attempts genuinely reached the model (2 work steps each): the replan was not refused before any call
    assert script.calls == 4

    # and each attempt's own experience carries only that attempt's own work — never the mission's running total
    assert (first.plan_id, first.plan_version) == (v1.plan_id, 1) and (second.plan_id, second.plan_version) == (v2.plan_id, 2)
    assert first.agent_calls_used == second.agent_calls_used == 2  # two work steps each; a cumulative total would say 4
    assert (first.replans_used, second.replans_used) == (0, 1)  # the one counter that is honestly the mission's running total
    assert (second.mission_status, second.verified) == (MissionStatus.COMPLETED, True)


def test_three_plan_versions_all_use_fresh_step_ids_and_the_third_completes(tmp_path):
    state = make_mission(capabilities=_THREE, seed=21)
    script = under_cited_first_n_calls(6)  # attempts 1 and 2 (3 work steps each) store artifacts, then fail verification
    result = replan(
        state, selector=DeterministicSelector(), store=_store(tmp_path), respond=script,
        limits=make_system_limits(max_replans=2),
    )
    assert len(result.plans) == 3 and result.replans_used == 2
    assert (result.telemetry.mission_status, result.telemetry.verified) == (MissionStatus.COMPLETED, True)
    assert [e.failure_cause for e in result.experiences[:2]] == [MissionFailureCause.VERIFICATION_FAILED] * 2

    per_plan = [_work_results(result, plan) for plan in result.plans]
    assert all(str(r.step_id).startswith("stage") for r in per_plan[0])
    assert all(str(r.step_id).startswith("v2_stage") for r in per_plan[1])
    assert all(str(r.step_id).startswith("v3_stage") for r in per_plan[2])
    assert all(r.status is NodeStatus.SUCCEEDED for results in per_plan for r in results)
    everything = [r.step_id for results in per_plan for r in results]
    assert len(everything) == len(set(everything))  # no work-step id repeats across the mission's three plan versions
    assert script.calls == 9


# --- M: a mission that never replans is recorded exactly as record_baseline records it ---------------------------


def test_m_a_mission_that_never_replans_records_exactly_what_record_baseline_records(tmp_path):
    state = make_mission(capabilities=_TWO, seed=14)
    result = replan(state, selector=DeterministicSelector(), store=_store(tmp_path), respond=uniformly_sufficient)
    assert len(result.plans) == 1

    agents, verifier = build_agents(state, uniformly_sufficient)
    baseline = record_baseline(
        state=state, plan=result.plans[0], limits=GENEROUS_LIMITS, registry=make_registry(), agents=agents,
        verifier=verifier, admission_guard=admit_all(), executor_factory=SequentialExecutor, clock=FixedClock(),
        ids=UuidEventIds(),
    )

    def settled(log):
        return [
            (p.result.step_id, p.result.status, p.result.artifact, p.dispatched)
            for p in (r.payload for r in log.records) if isinstance(p, NodeSettledPayload)
        ]

    assert [r.event.type for r in result.log.records] == [r.event.type for r in baseline.log.records]
    assert [r.event.sequence for r in result.log.records] == [r.event.sequence for r in baseline.log.records]
    assert settled(result.log) == settled(baseline.log)
    assert result.log.records[-1].payload == baseline.log.records[-1].payload
    assert isinstance(result.log.records[-1].payload, MissionCompletedPayload)


# --- a replan-time selection that yields no usable candidate ends the mission honestly, never crashes or loops ---


@dataclass
class _GoodOnceThenBad:
    """The real ``DeterministicSelector`` for the very first selection, then whatever ``bad`` is for every later one."""

    bad: SelectorChoice
    calls: int = 0

    def select(self, candidates, task_genome) -> SelectorChoice:
        self.calls += 1
        return DeterministicSelector().select(candidates, task_genome) if self.calls == 1 else self.bad


@pytest.mark.parametrize("bad", [
    SelectorFailure(kind=SelectorFailureKind.UNAVAILABLE, message="test: the selector is down"),
    SelectedCandidate(strategy_id=StrategyId(uuid4())),  # a well-formed choice naming a candidate that does not exist
], ids=["selector_failed", "invalid_candidate_returned"])
def test_a_replan_time_selection_that_is_refused_ends_the_mission_with_the_last_attempts_real_outcome(tmp_path, bad):
    state = make_mission(capabilities=_THREE, seed=22)  # three candidates: the replan's own selection does reach the selector
    result = replan(
        state, selector=_GoodOnceThenBad(bad=bad), store=_store(tmp_path), respond=always_fails,
        limits=make_system_limits(max_replans=2),
    )
    assert len(result.plans) == 1 and result.replans_used == 0
    assert (result.telemetry.mission_status, result.telemetry.failure_cause) == (MissionStatus.FAILED, MissionFailureCause.EXECUTION_FAILED)
    assert not any(isinstance(r.payload, ReplanTriggeredPayload) for r in result.log.records)
    assert result.log.records[-1].event.type is MissionEventType.MISSION_FAILED


# --- G (later attempt): a halt in a REPLANNED attempt is just as terminal as one in the first ---------------------


def test_g_an_admission_guard_halt_in_a_replanned_attempt_ends_the_mission_paused_with_no_further_replan(tmp_path):
    state = make_mission(capabilities=_THREE, seed=23)
    # Attempt 1 (parallel) fails on its first model call under a guard that admits everything, so it is an ordinary
    # replan-eligible failure. Attempt 2's own guard halts any concurrent dispatch (rank_in_level >= 1), which the
    # replanned (two-stage) shape hits: a halt stays terminal for the attempt it happens in, whichever attempt that is.
    guards = iter([lambda: halt_when(lambda request: False, "never"), lambda: halt_when(lambda request: request.rank_in_level >= 1, "test: halt")])
    result = replan(
        state, selector=DeterministicSelector(), store=_store(tmp_path), respond=fail_first_n_calls(1),
        admission_guard_factory=lambda: next(guards)(), limits=make_system_limits(max_replans=2),
    )
    assert len(result.plans) == 2 and result.replans_used == 1  # replanned once (attempt 1 was an ordinary failure)
    assert (result.telemetry.mission_status, result.telemetry.run_outcome) == (MissionStatus.PAUSED, RunOutcome.HALTED)
    assert result.log.records[-1].event.type is MissionEventType.MISSION_PAUSED
    assert sum(isinstance(r.payload, ReplanTriggeredPayload) for r in result.log.records) == 1  # never a second one


# --- a fresh admission guard for every attempt; no candidate at all is refused up front ---------------------------


def test_a_fresh_admission_guard_is_built_and_actually_used_for_every_attempt(tmp_path):
    state = make_mission(capabilities=_TWO, seed=24)
    built = []

    def factory():
        built.append(admit_all())
        return built[-1]

    result = replan(
        state, selector=DeterministicSelector(), store=_store(tmp_path), respond=fail_first_n_calls(1),
        admission_guard_factory=factory,
    )
    assert len(result.plans) == 2 and len(built) == 2 and built[0] is not built[1]
    # each guard was asked only about its own attempt's steps: version 1's ids, then version 2's, never mixed
    # (`verify` is the one control step, whose id is the same in every version, D-200)
    def own_steps(guard, prefix):
        return guard.requests and all(str(r.step_id).startswith(prefix) or r.step_id == "verify" for r in guard.requests)

    assert own_steps(built[0], "stage") and own_steps(built[1], "v2_stage")


@dataclass(frozen=True)
class _NoCandidates:
    def generate(self, task_genome):
        return ()


def test_a_mission_with_no_candidate_strategy_at_all_is_refused_up_front_and_records_nothing(tmp_path):
    state = make_mission(capabilities=_TWO, seed=25)
    store, log = _store(tmp_path), EventLog()
    with pytest.raises(ValueError, match="no feasible candidate strategy"):
        replan(state, selector=DeterministicSelector(), store=store, candidate_generator=_NoCandidates(), log=log)
    assert store.all() == ()  # no experience: nothing ran
    assert log.records == ()  # and no event at all, not even MISSION_CREATED: the mission has no plan to run
