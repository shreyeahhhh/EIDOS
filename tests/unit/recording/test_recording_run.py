"""Recording one baseline pass as events (decisions.md D-152, D-158, D-160; V0.5 Step 5b).

What a pass logs, in what order, for every way it can end; that recording changes nothing about the pass; and that nothing is silent: a
refused proposal, a live settlement the run then contradicts, and a fault inside the recorder's own observer are all surfaced.
"""

import os
import subprocess
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

import eidos.recording.adapters as adapters
import eidos.recording.run as run_module
from eidos.agents import ModelFailure, ModelFailureKind, ModelRequest
from eidos.baseline import BaselineStage
from eidos.contracts import MissionEventType, MissionStatus, PlanStepKind, StepId
from eidos.recording import Recorder, RecordingModel
from eidos.runtime import NodeResult, NodeStatus, PriorOutcomes, RunOutcome, RunRejection, WorkResult
from eidos.state import (
    EventLog,
    MissionCreatedPayload,
    MissionFailureCause,
    ModelCallFacts,
    ModelCallOutcome,
    NodeStartedPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    PlanRejectionStage,
    ReduceOutcome,
    replay,
)

from eidos_agents_factories import make_settings
from eidos_mission_factories import make_mission, make_mission_plan
from eidos_recording_factories import (
    FixedClock,
    SequentialIds,
    baseline_mission,
    new_rig,
    record,
    respond_with_facts,
    unrecorded,
)
from eidos_runtime_factories import halt_when
from eidos_state_factories import T0
from eidos_v04_registry import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID

ROOT = Path(__file__).resolve().parents[3]


def shape(log):
    """(type, detail) for each recorded event, in sequence order."""
    out = []
    for r in log.records:
        p, detail = r.payload, ""
        if r.event.type is MissionEventType.NODE_STARTED:
            detail = str(p.step_id)
        elif r.event.type is MissionEventType.NODE_SETTLED:
            detail = f"{p.result.step_id}:{p.result.status.value}" + ("" if p.dispatched else ":not-dispatched")
        elif r.event.type is MissionEventType.PLAN_REJECTED:
            detail = p.stage.value
        elif r.event.type is MissionEventType.MISSION_FAILED:
            detail = p.cause.value
        elif r.event.type is MissionEventType.MISSION_COMPLETED:
            detail = f"verified={p.verified}"
        elif r.event.type is MissionEventType.MISSION_PAUSED:
            detail = str(p.halt.step_id)
        out.append((r.event.type.value, detail))
    return out


def settled(log, step):
    return next(r.payload for r in log.records if r.event.type is MissionEventType.NODE_SETTLED and r.payload.result.step_id == step)


VERIFIED = [
    ("MISSION_CREATED", ""), ("PLAN_GENERATED", ""), ("PLAN_COMPILED", ""),
    ("NODE_STARTED", "gather"), ("NODE_SETTLED", "gather:succeeded"),
    ("NODE_STARTED", "analyse"), ("NODE_SETTLED", "analyse:succeeded"),
    ("NODE_STARTED", "check"), ("NODE_SETTLED", "check:succeeded"),
    ("MISSION_COMPLETED", "verified=True"),
]


# --- a verified baseline ---------------------------------------------------------------------------------------------------------------


def test_a_verified_baseline_is_recorded_started_then_settled_node_by_node():
    state, plan = baseline_mission()
    run, _ = record(state, plan)
    assert shape(run.log) == VERIFIED
    assert run.refused == () and run.discrepancies == ()
    assert run.report.run.outcome is RunOutcome.FINISHED and run.report.run.verified


def test_the_folded_state_of_the_recorded_pass_is_the_completed_mission_with_its_counters_written_out():
    state, plan = baseline_mission()
    run, _ = record(state, plan)
    folded = run.log.state
    assert folded.status is MissionStatus.COMPLETED and folded.status_reason == "finished and verified"
    assert folded.plans == (plan,) and folded.active_plan_id == plan.plan_id and folded.state_version == 10
    assert folded.agent_calls_used == 2  # the two work nodes
    assert folded.tokens_used == 2 * (100 + 200)  # what the scripted provider reported, for two calls
    assert folded.execution_time_used_ms == 3 * 1000  # three nodes, each one fixed clock step long
    assert (folded.retries_used, folded.replans_used, folded.tool_calls_used) == (0, 0, 0)


def test_the_recorded_pass_reports_exactly_what_an_unrecorded_pass_reports():
    state, plan = baseline_mission()
    run, _ = record(state, plan)
    assert run.report.model_dump_json() == unrecorded(state, plan).model_dump_json()


def test_each_work_node_carries_the_model_calls_made_while_it_ran_and_the_verify_node_carries_the_verdict():
    state, plan = baseline_mission()
    run, _ = record(state, plan)
    expected = (ModelCallFacts(outcome=ModelCallOutcome.RESPONSE, prompt_tokens=100, output_tokens=200, elapsed_seconds=0.5),)
    assert settled(run.log, StepId("gather")).model_calls == expected
    assert settled(run.log, StepId("analyse")).model_calls == expected
    check = settled(run.log, StepId("check"))
    assert check.model_calls == () and check.verification.verdict.value == "pass"
    assert check.verification.reason == run.report.run.result_for(StepId("check")).reason  # the verifier's own words, unchanged


def test_a_started_event_names_what_did_the_work_and_a_verify_node_names_nothing():
    state, plan = baseline_mission()
    run, _ = record(state, plan)
    starts = {r.payload.step_id: r.payload for r in run.log.records if r.event.type is MissionEventType.NODE_STARTED}
    assert (starts["gather"].capability, starts["gather"].agent_id) == ("research", RESEARCH_AGENT_ID)
    assert (starts["analyse"].capability, starts["analyse"].agent_id) == ("cost", ANALYSIS_AGENT_ID)
    assert (starts["check"].kind, starts["check"].capability, starts["check"].agent_id) == (PlanStepKind.VERIFY, None, None)


def test_every_time_in_the_log_comes_from_the_injected_clock_and_no_two_of_them_are_read_out_of_order():
    state, plan = baseline_mission()
    run, _ = record(state, plan, clock=FixedClock(step_seconds=5))
    times = [r.event.occurred_at for r in run.log.records]
    assert times == [T0 + timedelta(seconds=5 * k) for k in range(1, 11)]
    assert all(r.event.occurred_at == r.event.recorded_at for r in run.log.records)  # an EIDOS-internal event: one instant (D-086)


def test_the_recorded_log_replays_to_the_state_the_intake_built():
    state, plan = baseline_mission()
    run, _ = record(state, plan)
    assert replay(run.log.records).state == run.log.state


# --- the other ways a pass can end -----------------------------------------------------------------------------------------------------


def test_a_finished_run_without_a_verify_node_is_completed_with_verified_false():
    state = make_mission(capabilities=("research", "cost"))
    plan = make_mission_plan(state, {"gather": "", "analyse": "gather"}, capability_of={"gather": "research", "analyse": "cost"})
    run, _ = record(state, plan)
    assert shape(run.log)[-1] == ("MISSION_COMPLETED", "verified=False")
    assert run.log.state.status is MissionStatus.COMPLETED and "verified is false" in run.log.state.status_reason


def test_a_failed_verification_is_a_settled_verify_node_and_a_failed_mission_with_that_cause():
    state, plan = baseline_mission()
    run, _ = record(state, plan, respond=respond_with_facts(research="Findings [[doc:9]]."))  # cites a source that was never supplied
    assert shape(run.log)[-2:] == [("NODE_SETTLED", "check:verification_failed"), ("MISSION_FAILED", "verification_failed")]
    check = settled(run.log, StepId("check"))
    assert check.verification.verdict.value == "fail" and check.verification.reason == check.result.reason
    failed = run.log.records[-1].payload
    assert failed.cause is MissionFailureCause.VERIFICATION_FAILED and failed.reason == check.result.reason
    assert run.log.state.status is MissionStatus.FAILED
    assert MissionEventType.VERIFICATION_FAILED.value not in {t for t, _ in shape(run.log)}  # not emitted (D-160 item 2)


@pytest.mark.parametrize("kind, status, cause", [
    (ModelFailureKind.TIMEOUT, NodeStatus.FAILED, MissionFailureCause.EXECUTION_FAILED),
    (ModelFailureKind.UNAVAILABLE, NodeStatus.FAILED, MissionFailureCause.EXECUTION_FAILED),
    (ModelFailureKind.EMPTY_RESPONSE, NodeStatus.NO_RESULT, MissionFailureCause.NO_RESULT),
    (ModelFailureKind.MALFORMED_RESPONSE, NodeStatus.NO_RESULT, MissionFailureCause.NO_RESULT),
], ids=lambda x: getattr(x, "value", None) or "")
def test_a_model_failure_settles_its_node_and_skips_the_rest_and_the_typed_kind_is_recorded(kind, status, cause):
    state, plan = baseline_mission()
    failure = ModelFailure(kind=kind, message="the model did not answer")
    run, _ = record(state, plan, respond=respond_with_facts(research=failure))
    assert shape(run.log)[3:] == [
        ("NODE_STARTED", "gather"), ("NODE_SETTLED", f"gather:{status.value}"),
        ("NODE_SETTLED", "analyse:skipped:not-dispatched"), ("NODE_SETTLED", "check:skipped:not-dispatched"), ("MISSION_FAILED", cause.value),
    ]
    call = settled(run.log, StepId("gather")).model_calls
    assert call == (ModelCallFacts(outcome=ModelCallOutcome(kind.value)),)  # the typed kind, and no provider facts for a failed call
    assert run.log.records[-1].payload.reason == settled(run.log, StepId("gather")).result.reason
    folded = run.log.state
    assert (folded.agent_calls_used, folded.tokens_used, folded.execution_time_used_ms) == (1, 0, 1000)


@pytest.mark.parametrize("name", ["validation", "compilation", "binding"])
def test_a_plan_refused_at_a_gate_is_generated_then_rejected_then_the_mission_fails(name):
    state = make_mission(capabilities=("research", "billing"))
    plans = {
        "validation": make_mission_plan(state, {"a": "b", "b": "a"}, capability_of={"a": "research", "b": "research"}),
        "compilation": make_mission_plan(state, {"a": "", "r": "a"}, controls={"r": PlanStepKind.ROUTE}, capability_of={"a": "research"}),
        "binding": make_mission_plan(state, {"a": ""}, capability_of={"a": "billing"}),
    }
    run, rig = record(state, plans[name])
    assert shape(run.log) == [("MISSION_CREATED", ""), ("PLAN_GENERATED", ""), ("PLAN_REJECTED", name), ("MISSION_FAILED", "plan_rejected")]
    rejected = run.log.records[2].payload
    gate = {"validation": run.report.validation, "compilation": run.report.compilation, "binding": run.report.binding}[name]
    assert rejected.stage is PlanRejectionStage(name) and rejected.plan_id == plans[name].plan_id
    assert [(r.code, r.message) for r in rejected.reasons] == [(v.code.value, v.message) for v in gate.violations] and rejected.reasons
    assert run.report.stopped_at is BaselineStage(name) and rig.scripted.requests == []  # nothing ran
    assert run.log.state.status is MissionStatus.FAILED and run.log.state.active_plan_id is None
    assert run.report.model_dump_json() == unrecorded(state, plans[name]).model_dump_json()


def test_an_admission_halt_settles_the_undispatched_nodes_as_not_reached_and_pauses_the_mission():
    state, plan = baseline_mission()
    run, _ = record(state, plan, guard=halt_when(lambda request: request.step_id == "analyse", "held for review"))
    assert shape(run.log)[3:] == [
        ("NODE_STARTED", "gather"), ("NODE_SETTLED", "gather:succeeded"),
        ("NODE_SETTLED", "analyse:not_reached:not-dispatched"), ("NODE_SETTLED", "check:not_reached:not-dispatched"), ("MISSION_PAUSED", "analyse"),
    ]
    paused = run.log.records[-1].payload
    assert (paused.halt.step_id, paused.halt.level, paused.halt.reason) == ("analyse", 2, "held for review")
    assert run.log.state.status is MissionStatus.PAUSED and run.log.state.status_reason == "held for review"


def test_a_node_carried_over_from_prior_outcomes_is_settled_but_not_dispatched_and_is_not_an_agent_call():
    state, plan = baseline_mission()
    first, rig = record(state, plan, guard=halt_when(lambda request: request.step_id == "analyse", "held"))
    second, _ = record(state, plan, rig=rig, prior=PriorOutcomes.succeeded_from(first.report.run))
    carried = settled(second.log, StepId("gather"))
    assert carried.dispatched is False and carried.duration_ms is None and carried.model_calls == () and carried.result.status is NodeStatus.SUCCEEDED
    assert ("NODE_STARTED", "gather") not in shape(second.log)
    assert second.log.state.agent_calls_used == 1  # only analyse ran
    assert second.log.state.status is MissionStatus.COMPLETED


def test_a_port_that_raises_is_settled_after_the_run_from_the_executors_own_result_with_what_was_observed():
    state, plan = baseline_mission()
    rig = new_rig(state)

    class Raiser:
        def run(self, context, node):
            raise RuntimeError("boom")

    rig.agents[RESEARCH_AGENT_ID] = Raiser()
    run, _ = record(state, plan, rig=rig)
    gather = settled(run.log, StepId("gather"))
    assert gather.result.status is NodeStatus.FAILED and "raised" in gather.result.reason and "boom" in gather.result.reason
    assert gather.dispatched and gather.duration_ms == 1000  # observed, even though the work never returned
    assert run.discrepancies == () and run.refused == ()
    assert ("NODE_STARTED", "gather") in shape(run.log) and shape(run.log)[-1] == ("MISSION_FAILED", "execution_failed")


def test_the_model_calls_a_raising_port_made_before_it_raised_are_kept_and_counted():
    state, plan = baseline_mission()
    rig = new_rig(state)
    model = RecordingModel(rig.scripted, rig.tracker)

    class CallsThenRaises:
        def run(self, context, node):
            model.complete(ModelRequest(settings=make_settings(), prompt="Documents: none"))
            raise RuntimeError("boom after one call")

    rig.agents[RESEARCH_AGENT_ID] = CallsThenRaises()
    run, _ = record(state, plan, rig=rig)
    gather = settled(run.log, StepId("gather"))
    assert gather.dispatched and gather.result.status is NodeStatus.FAILED
    assert gather.model_calls == (ModelCallFacts(outcome=ModelCallOutcome.RESPONSE, prompt_tokens=100, output_tokens=200, elapsed_seconds=0.5),)
    assert (run.log.state.agent_calls_used, run.log.state.tokens_used) == (1, 300)  # the call was made, so it is counted


@pytest.mark.parametrize("first, second, cause", [
    (ModelFailureKind.TIMEOUT, ModelFailureKind.EMPTY_RESPONSE, MissionFailureCause.EXECUTION_FAILED),
    (ModelFailureKind.EMPTY_RESPONSE, ModelFailureKind.TIMEOUT, MissionFailureCause.NO_RESULT),
], ids=["failed-then-no-result", "no-result-then-failed"])
def test_the_cause_of_a_failed_mission_is_the_first_failing_node_in_plan_order(first, second, cause):
    state = make_mission(capabilities=("research",))
    plan = make_mission_plan(state, {"one": "", "two": ""}, capability_of={"one": "research", "two": "research"})
    answers = iter([ModelFailure(kind=first, message="first"), ModelFailure(kind=second, message="second")])
    run, _ = record(state, plan, respond=lambda request: next(answers))
    failed = run.log.records[-1].payload
    assert failed.cause is cause and failed.reason == settled(run.log, StepId("one")).result.reason
    assert {settled(run.log, StepId(s)).result.status for s in ("one", "two")} == {NodeStatus.FAILED, NodeStatus.NO_RESULT}  # both did fail


def test_a_run_the_executor_refuses_is_a_failed_mission_whose_reason_carries_the_typed_code():
    state, plan = baseline_mission()
    first, rig = record(state, plan, guard=halt_when(lambda request: request.step_id == "analyse", "held"))
    prior = PriorOutcomes.succeeded_from(first.report.run).model_copy(update={"plan_version": 99})
    second, _ = record(state, plan, rig=rig, prior=prior)
    assert isinstance(second.report.run, RunRejection)
    assert shape(second.log) == [("MISSION_CREATED", ""), ("PLAN_GENERATED", ""), ("PLAN_COMPILED", ""), ("MISSION_FAILED", "run_rejected")]
    reason = second.log.records[-1].payload.reason
    assert reason == f"{second.report.run.code.value}: {second.report.run.message}" and reason.startswith("invalid_prior_state: ")
    assert second.log.state.status is MissionStatus.FAILED


# --- nothing is silent ---------------------------------------------------------------------------------------------------------------


def test_a_proposal_the_log_refuses_is_kept_and_the_pass_is_unchanged():
    state, plan = baseline_mission()
    finished, _ = record(state, plan)
    again, _ = record(state, plan, log=finished.log, ids=SequentialIds(start=1000))  # the mission is already complete: everything offered is refused
    assert len(again.log) == 10  # the log did not grow
    assert len(again.refused) == 13  # the ten events of a pass, plus the three node settlements proposed again after the run because the live ones were refused
    assert {r.outcome for r in again.refused} == {ReduceOutcome.POST_TERMINAL}
    assert again.report.model_dump_json() == unrecorded(state, plan).model_dump_json()


def test_a_live_settlement_the_run_contradicts_is_reported_as_a_discrepancy_not_hidden(monkeypatch):
    state, plan = baseline_mission()

    def wrong(node, result):
        return NodeResult(step_id=node.step_id, kind=node.kind, status=NodeStatus.FAILED, reason="the recorder mis-mapped this")

    monkeypatch.setattr(adapters, "node_result_of_work", wrong)
    run, _ = record(state, plan)
    assert run.discrepancies and all("settled live as failed but the run reports succeeded" in d for d in run.discrepancies)


def test_a_fault_inside_the_recorders_own_observer_is_visible_and_never_reaches_the_pass(monkeypatch):
    state, plan = baseline_mission()

    def broken(**kwargs):
        raise RuntimeError("payload could not be built")

    monkeypatch.setattr(run_module, "PlanGeneratedPayload", broken)
    run, _ = record(state, plan)
    assert any("could not record the plan" in d for d in run.discrepancies)
    assert run.report.run.outcome is RunOutcome.FINISHED  # the pass itself ran to the end


# --- the recorder is one door, safe from many threads --------------------------------------------------------------------------------


def test_many_threads_recording_at_once_lose_nothing_and_leave_the_sequence_contiguous():
    state, plan = baseline_mission()
    log = EventLog()
    recorder = Recorder(log=log, clock=FixedClock(), ids=SequentialIds(), tenant_id=state.tenant_id, mission_id=state.mission_id)
    recorder.record(MissionCreatedPayload(task_genome=state.task_genome, reliability_contract=state.reliability_contract, execution_id=state.execution_id))
    recorder.record(PlanGeneratedPayload(plan=plan))
    recorder.record(PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version))

    def worker():
        for _ in range(50):
            recorder.record(NodeStartedPayload(plan_id=plan.plan_id, step_id=StepId("check"), kind=PlanStepKind.VERIFY))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(log) == 3 + 8 * 50 and recorder.refused == ()
    assert [r.event.sequence for r in log.records] == list(range(1, len(log) + 1))
    assert len({r.event.event_id for r in log.records}) == len(log)
    assert log.state == replay(log.records).state


def test_two_threads_are_never_inside_the_recorder_at_once():
    class ProbingClock(FixedClock):
        """Widens the window inside the recorder and counts how many callers are in it together."""

        def __init__(self):
            super().__init__()
            self._probe, self.inside, self.deepest = threading.Lock(), 0, 0

        def now(self):
            with self._probe:
                self.inside += 1
                self.deepest = max(self.deepest, self.inside)
            time.sleep(0.002)
            with self._probe:
                self.inside -= 1
            return super().now()

    state, plan = baseline_mission()
    clock = ProbingClock()
    recorder = Recorder(log=EventLog(), clock=clock, ids=SequentialIds(), tenant_id=state.tenant_id, mission_id=state.mission_id)
    threads = [threading.Thread(target=lambda: [recorder.record(PlanGeneratedPayload(plan=plan)) for _ in range(5)]) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert clock.deepest == 1  # the lock covers the clock read as well as the intake


def test_a_recorder_holds_no_mission_state_and_exposes_no_way_to_write_one():
    state, plan = baseline_mission()
    recorder = Recorder(log=EventLog(), clock=FixedClock(), ids=SequentialIds(), tenant_id=state.tenant_id, mission_id=state.mission_id)
    assert not any(isinstance(v, type(state)) for v in vars(recorder).values())
    assert not hasattr(recorder, "state") and not hasattr(recorder, "reduce")


# --- determinism ---------------------------------------------------------------------------------------------------------------------


def test_the_recorded_log_is_identical_across_hash_seeds():
    script = (
        "import sys, hashlib; sys.path[:0] = ['src', 'tests/support']\n"
        "from eidos_recording_factories import baseline_mission, record\n"
        "state, plan = baseline_mission()\n"
        "run, _ = record(state, plan)\n"
        "print(hashlib.sha256(run.log.to_jsonl().encode()).hexdigest())\n"
    )
    seen = set()
    for seed in ("0", "1", "2", "12345"):
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": seed})
        assert result.returncode == 0, result.stderr
        seen.add(result.stdout.strip())
    assert len(seen) == 1 and len(next(iter(seen))) == 64
