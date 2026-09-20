"""Scenario: a baseline mission, from MissionState to a run result (V0.3).

A real MissionState -> a plan -> V0.2 validation -> the compiler -> a frozen execution context -> both
executors. Work is done by scripted test doubles (no product mock agents exist at V0.3), so what these
scenarios prove is the pipeline and the run's *meaning*, not any agent's quality.

V0.3 emits no events (D-123: invariant 15 is not exercised), so each scenario asserts on the ``RunResult``
— the typed record of a run, in plan order, with its dispatch order — and on what the ports were asked.
Every ``drive`` also asserts that the LangGraph backend returned exactly what the reference executor did.
"""

import json

from eidos.contracts import MissionStatus, StepId
from eidos.runtime import NodeStatus, RunOutcome

from eidos_scenario_factories import drive, make_mission, make_mission_plan

# Two independent gathering steps, an analysis that needs both, and a verification of the analysis.
SPEC = {"gather_a": "", "gather_b": "", "analyse": "gather_a gather_b", "check": "analyse"}
CAPABILITY_OF = {"analyse": "analysis"}


def baseline():
    state = make_mission()
    plan = make_mission_plan(state, SPEC, verify=("check",), capability_of=CAPABILITY_OF)
    return state, plan


def test_a_baseline_mission_runs_to_a_finished_and_verified_result():
    state, plan = baseline()
    attempt = drive(state, plan)

    # The plan went through every gate before anything ran.
    assert attempt.report.accepted
    assert attempt.compile_report.succeeded
    assert attempt.ran

    result = attempt.result
    assert result.outcome is RunOutcome.FINISHED
    assert result.halt is None
    assert result.verified is True

    # The run is bound to this mission, this execution and this plan version.
    assert (result.tenant_id, result.mission_id, result.execution_id) == (
        state.tenant_id,
        state.mission_id,
        state.execution_id,
    )
    assert (result.plan_id, result.plan_version) == (plan.plan_id, 1)

    # What ran, in the order it ran: level by level, plan order within a level.
    assert result.dispatched == ("gather_a", "gather_b", "analyse", "check")
    assert [(r.step_id, r.status) for r in result.results] == [
        ("gather_a", NodeStatus.SUCCEEDED),
        ("gather_b", NodeStatus.SUCCEEDED),
        ("analyse", NodeStatus.SUCCEEDED),
        ("check", NodeStatus.SUCCEEDED),
    ]
    assert [r.artifact for r in result.results[:3]] == [
        "artifact:gather_a",
        "artifact:gather_b",
        "artifact:analyse",
    ]
    assert result.result_for(StepId("check")).reason == "verified"


def test_the_ports_are_asked_exactly_what_the_plan_requires_and_nothing_more():
    state, plan = baseline()
    attempt = drive(state, plan)
    result = attempt.result

    assert sorted(attempt.work.calls) == ["analyse", "gather_a", "gather_b"]
    # The verifier saw the one thing it verifies: the analysis it depends on, as it stood.
    assert attempt.verifier.records == [("check", (result.result_for(StepId("analyse")),))]
    # One admission request per dispatched node: (step, level, rank in level, dispatched before the level).
    assert sorted(attempt.guard.asked()) == [
        ("analyse", 2, 0, 2),
        ("check", 3, 0, 3),
        ("gather_a", 1, 0, 0),
        ("gather_b", 1, 1, 0),
    ]
    # Every port was handed the same frozen snapshot of the mission, and nothing else.
    assert all(context == attempt.context for context in attempt.work.contexts + attempt.verifier.contexts)
    assert attempt.context.task_genome == state.task_genome


def test_a_run_reads_the_mission_state_and_never_writes_it():
    state, plan = baseline()
    before = state.model_dump_json()

    drive(state, plan)

    assert state.model_dump_json() == before
    # V0.3 keeps no accounting and records nothing (D-123, D-127): the mission is exactly as created.
    assert state.status is MissionStatus.CREATED
    assert state.plans == ()
    assert state.agent_tasks == ()
    assert state.agent_calls_used == 0
    assert state.state_version == 0


def test_a_finished_run_that_verified_nothing_is_not_reported_as_verified():
    # "An agent returned output" is never success (invariant 12): no VERIFY step, no verification.
    state = make_mission()
    plan = make_mission_plan(state, {"gather": "", "analyse": "gather"}, capability_of=CAPABILITY_OF)

    result = drive(state, plan).result

    assert result.outcome is RunOutcome.FINISHED
    assert all(r.status is NodeStatus.SUCCEEDED for r in result.results)
    assert result.verified is False


def test_an_empty_plan_finishes_with_nothing_run_and_is_not_verified():
    # D-106: an empty plan is valid. It runs nothing, and nothing was verified.
    state = make_mission()
    plan = make_mission_plan(state, {})

    attempt = drive(state, plan)

    assert attempt.report.accepted
    result = attempt.result
    assert (result.outcome, result.results, result.dispatched) == (RunOutcome.FINISHED, (), ())
    assert result.verified is False
    assert attempt.work.calls == [] and attempt.verifier.calls == [] and attempt.guard.requests == []


def test_a_wide_mission_runs_every_independent_branch_level_by_level():
    state = make_mission()
    spec = {
        "a1": "", "a2": "", "a3": "",
        "b1": "a1", "b2": "a2", "b3": "a3",
        "join": "b1 b2 b3",
    }
    plan = make_mission_plan(state, spec)

    result = drive(state, plan).result

    assert result.outcome is RunOutcome.FINISHED
    assert result.dispatched == ("a1", "a2", "a3", "b1", "b2", "b3", "join")
    assert all(r.status is NodeStatus.SUCCEEDED for r in result.results)


def test_the_same_mission_gives_the_same_run_every_time():
    # A repeat is byte for byte the first run: results are ordered by the plan, never by completion.
    state, plan = baseline()
    first = drive(state, plan).result.model_dump_json()

    for _ in range(3):
        assert drive(state, plan).result.model_dump_json() == first
    json.loads(first)  # and it is a plain, serializable record
