"""Scenarios: the run halts for human review, and is resumed (V0.3).

Invariant 7: execution is bounded, and exhaustion *pauses* the mission. It never loops, never silently
truncates and never retries forever. At V0.3 the hook for that is the ``AdmissionGuard`` (D-122): a pure
function of a request that may say HALT. The guards below are test code standing in for a budget — the real
budgets, and the accounting behind them, are deferred (D-127) — so these scenarios prove what the runtime
does *when it is told to stop*, not that any budget is enforced.

Invariant 14: governance is code, so a guard that is broken stops the run rather than waving it through.

D-119 and D-120: there is no automatic retry. A halted or failed run is continued by a caller starting a new
run over the earlier run's SUCCEEDED outcomes; those nodes are not dispatched again.
"""

import pytest

from eidos.contracts import StepId
from eidos.runtime import NodeStatus, PriorOutcomes, RunOutcome

from eidos_backend_factories import locked_halt_when
from eidos_runtime_factories import JunkGuard, RaisingGuard
from eidos_scenario_factories import drive, make_mission, make_mission_plan

# a and b are independent (level 1); c needs both (2); then a chain d (3) and e (4).
SPEC = {"a": "", "b": "", "c": "a b", "d": "c", "e": "d"}
BUDGET = 3


def budget_guard():
    """Admit at most BUDGET dispatches in a run — a pure function of the request, as D-122 requires."""
    return locked_halt_when(
        lambda request: request.dispatched_before_level + request.rank_in_level >= BUDGET,
        "the agent-call budget of 3 is exhausted",
    )


def mission():
    state = make_mission()
    return state, make_mission_plan(state, SPEC)


# --- a halt pauses the mission ---------------------------------------------------------------------------------------


def test_an_exhausted_budget_halts_the_run_and_the_rest_is_reported_not_reached():
    state, plan = mission()
    attempt = drive(state, plan, guard=budget_guard)
    result = attempt.result

    assert result.outcome is RunOutcome.HALTED  # not FINISHED, and not FAILED: a human must look
    assert result.verified is False
    assert (result.halt.step_id, result.halt.level, result.halt.reason) == (
        "d",
        3,
        "the agent-call budget of 3 is exhausted",
    )
    assert [(r.step_id, r.status) for r in result.results] == [
        ("a", NodeStatus.SUCCEEDED),
        ("b", NodeStatus.SUCCEEDED),
        ("c", NodeStatus.SUCCEEDED),
        ("d", NodeStatus.NOT_REACHED),
        ("e", NodeStatus.NOT_REACHED),
    ]
    # Every step has a result: nothing was silently truncated. Only the three admitted nodes ran.
    assert len(result.results) == len(plan.steps)
    assert result.dispatched == ("a", "b", "c")
    assert sorted(attempt.work.calls) == ["a", "b", "c"]


def test_a_halt_ends_the_run_and_the_guard_is_asked_a_bounded_number_of_times():
    state, plan = mission()
    attempt = drive(state, plan, guard=budget_guard)

    # It stopped at d. It did not ask about e, and it did not loop back to ask again.
    assert sorted(attempt.guard.asked()) == [("a", 1, 0, 0), ("b", 1, 1, 0), ("c", 2, 0, 2), ("d", 3, 0, 3)]
    assert len(attempt.guard.requests) <= len(plan.steps)


def test_a_halt_takes_precedence_over_a_failure_in_the_same_run():
    # `a` fails, but `b` succeeds and unlocks `c`, which the guard then refuses. (Were `c` blocked by the
    # failure it would be skipped without being asked, and there would be nothing to halt.)
    state = make_mission()
    plan = make_mission_plan(state, {"a": "", "b": "", "c": "b", "d": "c"})
    halt_at_level_two = lambda: locked_halt_when(lambda request: request.level == 2, "held for review")

    attempt = drive(state, plan, guard=halt_at_level_two, work=lambda: {"a": RuntimeError("agent crashed")})
    result = attempt.result

    assert [(r.step_id, r.status) for r in result.results] == [
        ("a", NodeStatus.FAILED),
        ("b", NodeStatus.SUCCEEDED),
        ("c", NodeStatus.NOT_REACHED),
        ("d", NodeStatus.NOT_REACHED),
    ]
    assert result.outcome is RunOutcome.HALTED  # a failure does not hide that the run was stopped
    assert result.halt.step_id == "c"


@pytest.mark.parametrize("guard", [RaisingGuard, lambda: JunkGuard(None), lambda: JunkGuard("admit")])
def test_a_guard_that_is_broken_stops_the_run_before_anything_is_dispatched(guard):
    # Governance fails closed (invariant 14): an unreadable answer is never read as permission.
    state, plan = mission()
    attempt = drive(state, plan, guard=guard)
    result = attempt.result

    assert result.outcome is RunOutcome.HALTED
    assert result.halt.step_id == "a" and result.halt.level == 1
    assert "guard" in result.halt.reason
    assert all(r.status is NodeStatus.NOT_REACHED for r in result.results)
    assert result.dispatched == ()
    assert attempt.work.calls == [] and attempt.verifier.calls == []


# --- resuming: the caller continues from what succeeded --------------------------------------------------------------


def test_a_halted_run_resumes_over_its_succeeded_outcomes_and_matches_an_uninterrupted_run():
    state, plan = mission()
    halted = drive(state, plan, guard=budget_guard).result

    resumed = drive(state, plan, prior=PriorOutcomes.succeeded_from(halted))
    uninterrupted = drive(state, plan).result

    result = resumed.result
    assert result.outcome is RunOutcome.FINISHED
    assert result.execution_id == halted.execution_id  # the same execution (D-085)
    # Only what had not succeeded was dispatched, and the agents behind a, b and c were never called again.
    assert result.dispatched == ("d", "e")
    assert sorted(resumed.work.calls) == ["d", "e"]
    # Pausing and resuming leaves the mission exactly where an uninterrupted run would have left it.
    assert result.results == uninterrupted.results


def test_there_is_no_automatic_retry_a_failed_node_runs_once_and_the_caller_decides():
    state, plan = mission()
    first = drive(state, plan, work=lambda: {"b": RuntimeError("agent crashed")})

    assert first.work.calls.count("b") == 1  # dispatched once, failed once, never tried again
    assert first.result.outcome is RunOutcome.FAILED
    assert [(r.step_id, r.status) for r in first.result.results] == [
        ("a", NodeStatus.SUCCEEDED),
        ("b", NodeStatus.FAILED),
        ("c", NodeStatus.SKIPPED),
        ("d", NodeStatus.SKIPPED),
        ("e", NodeStatus.SKIPPED),
    ]

    # The caller decides to try again, over what succeeded. The agent has been fixed.
    second = drive(state, plan, prior=PriorOutcomes.succeeded_from(first.result))

    assert second.result.outcome is RunOutcome.FINISHED
    assert second.result.dispatched == ("b", "c", "d", "e")  # not `a`: it succeeded and stays settled
    assert second.result.results == drive(state, plan).result.results


def test_a_resumed_run_can_itself_be_halted_and_resumed_until_the_mission_finishes():
    # The guard admits two dispatches per run. Its count restarts with each run: the runtime keeps no
    # accounting across runs (D-043 and D-127), so a caller that wants a mission-wide budget supplies it.
    state, plan = mission()
    two_per_run = lambda: locked_halt_when(lambda request: request.dispatched_before_level >= 2, "two per run")

    first = drive(state, plan, guard=two_per_run).result
    assert (first.outcome, first.dispatched, first.halt.step_id) == (RunOutcome.HALTED, ("a", "b"), "c")

    second = drive(state, plan, prior=PriorOutcomes.succeeded_from(first), guard=two_per_run).result
    assert (second.outcome, second.dispatched, second.halt.step_id) == (RunOutcome.HALTED, ("c", "d"), "e")

    third = drive(state, plan, prior=PriorOutcomes.succeeded_from(second), guard=two_per_run).result
    assert (third.outcome, third.dispatched) == (RunOutcome.FINISHED, ("e",))  # each run made progress
    assert third.results == drive(state, plan).result.results
