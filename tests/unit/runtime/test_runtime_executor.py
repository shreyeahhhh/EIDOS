"""The sequential reference executor (decisions.md D-117, D-118, D-119, D-121, D-122, D-123).

These tests *define* what a run means. They are written against the EIDOS-defined
level-synchronous model — not against whatever a scheduler happens to do — and a future
backend is held to the same expectations.
"""

import dataclasses
import inspect
import json
import os
import random
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

from eidos.contracts import MissionId, PlanId, StepId, TenantId
from eidos.runtime import (
    HaltInfo,
    NodeStatus,
    RunOutcome,
    RunRejection,
    RunResult,
    SequentialExecutor,
    VerificationResult,
    WorkResult,
)

from eidos_factories import make_mission_state, make_reliability_contract, make_task_genome
from eidos_runtime_factories import (
    JunkGuard,
    RaisingGuard,
    RecordingGuard,
    ScriptedVerifier,
    ScriptedWork,
    admit_all,
    artifact_of,
    compiled_of,
    context_for,
    halt_when,
    make_executor,
    statuses,
)

S = NodeStatus


def go(spec, *, verify=(), work=None, verifier=None, guard=None, prior=None, **plan_overrides):
    """Compile ``spec`` and run it. Returns (result, work, verifier, guard, compiled)."""
    compiled = compiled_of(spec, verify=verify, **plan_overrides)
    work = work if work is not None else ScriptedWork()
    verifier = verifier if verifier is not None else ScriptedVerifier()
    guard = guard if guard is not None else admit_all()
    result = make_executor(work, verifier, guard).run(compiled, context_for(compiled), prior)
    return result, work, verifier, guard, compiled


# --- the trivial and the empty ------------------------------------------------------------------


def test_one_node_runs_and_finishes_unverified():
    result, work, _, guard, _ = go({"a": ""})
    assert isinstance(result, RunResult)
    assert result.outcome is RunOutcome.FINISHED and result.halt is None
    assert statuses(result) == {"a": "succeeded"}
    assert result.result_for(StepId("a")).artifact == artifact_of("a")
    assert result.dispatched == ("a",) and work.calls == ["a"]
    assert guard.asked() == [("a", 1, 0, 0)]
    assert result.verified is False  # finished, but nothing verified it (D-118)


def test_an_empty_plan_finishes_vacuously_and_touches_no_port():
    result, work, verifier, guard, _ = go({})
    assert result.outcome is RunOutcome.FINISHED
    assert result.results == () and result.dispatched == ()
    assert work.calls == [] and verifier.calls == [] and guard.requests == []
    assert result.verified is False


def test_the_result_carries_the_runs_identity():
    result, _, _, _, compiled = go({"a": ""}, version=4)
    context = context_for(compiled)
    assert (result.tenant_id, result.mission_id, result.execution_id) == (
        compiled.tenant_id, compiled.mission_id, context.execution_id,
    )
    assert (result.plan_id, result.plan_version) == (compiled.plan_id, 4)


# --- level-synchronous order ---------------------------------------------------------------------


def test_a_chain_runs_in_order_and_the_guard_sees_levels_ranks_and_counts():
    result, work, _, guard, _ = go({"a": "", "b": "a", "c": "b"})
    assert result.outcome is RunOutcome.FINISHED
    assert work.calls == ["a", "b", "c"]
    assert guard.asked() == [("a", 1, 0, 0), ("b", 2, 0, 1), ("c", 3, 0, 2)]


def test_a_diamond():
    result, work, _, guard, _ = go({"a": "", "b": "a", "c": "a", "d": "b c"})
    assert result.outcome is RunOutcome.FINISHED
    assert work.calls == ["a", "b", "c", "d"]
    assert guard.asked() == [("a", 1, 0, 0), ("b", 2, 0, 1), ("c", 2, 1, 1), ("d", 3, 0, 3)]


def test_fan_out():
    result, work, _, guard, _ = go({"root": "", "x": "root", "y": "root", "z": "root"})
    assert work.calls == ["root", "x", "y", "z"]
    assert guard.asked() == [("root", 1, 0, 0), ("x", 2, 0, 1), ("y", 2, 1, 1), ("z", 2, 2, 1)]


def test_fan_in():
    result, work, _, guard, _ = go({"x": "", "y": "", "z": "", "join": "x y z"})
    assert work.calls == ["x", "y", "z", "join"]
    assert guard.asked()[-1] == ("join", 2, 0, 3)
    assert result.outcome is RunOutcome.FINISHED


def test_disconnected_components_advance_level_by_level_not_component_by_component():
    # Level-synchronous: level 1 (a, x) before level 2 (b, y) — not a, b, x, y.
    result, work, _, _, _ = go({"a": "", "b": "a", "x": "", "y": "x"})
    assert work.calls == ["a", "x", "b", "y"]
    assert result.dispatched == ("a", "x", "b", "y")
    assert result.outcome is RunOutcome.FINISHED


def test_independent_node_runs_before_a_dependent_of_an_earlier_node():
    # A -> B, C independent. The EIDOS level model runs A and C (level 1) before B (level 2);
    # a depth-first scheduler would run A, B, C. Scheduling detail must not decide this.
    result, work, _, _, _ = go({"a": "", "b": "a", "c": ""})
    assert work.calls == ["a", "c", "b"]
    assert result.dispatched == ("a", "c", "b")


def test_within_a_level_nodes_run_in_ascending_plan_position_not_by_name():
    _, work, _, _, _ = go({"z": "", "m": "", "a": ""})
    assert work.calls == ["z", "m", "a"]


def test_dispatch_follows_level_then_position_even_when_plan_order_is_not_topological():
    # positions: c=0, b=1, a=2, z=3; levels: a=1, z=1, b=2, c=3
    result, work, _, _, _ = go({"c": "b", "b": "a", "a": "", "z": ""})
    assert work.calls == ["a", "z", "b", "c"]
    assert [r.step_id for r in result.results] == ["c", "b", "a", "z"]  # results stay in plan order


def test_results_are_in_compiled_plan_order_whatever_the_dispatch_order():
    result, _, _, _, compiled = go({"a": "", "b": "a", "c": ""})
    assert [r.step_id for r in result.results] == [n.step_id for n in compiled.nodes]


def test_multiple_levels_are_all_resolved_before_the_next_begins():
    _, work, _, guard, _ = go({"a": "", "b": "", "c": "a b", "d": "a", "e": "c d"})
    levels_asked = [level for _, level, _, _ in guard.asked()]
    assert levels_asked == sorted(levels_asked)
    assert work.calls == ["a", "b", "c", "d", "e"]


# --- failed predecessors and propagation -----------------------------------------------------------


def test_a_failed_first_node_skips_every_descendant_without_dispatching_them():
    script = {"a": WorkResult.failed("boom")}
    result, work, _, guard, _ = go({"a": "", "b": "a", "c": "b"}, work=ScriptedWork(script))
    assert statuses(result) == {"a": "failed", "b": "skipped", "c": "skipped"}
    assert work.calls == ["a"]
    assert [r[0] for r in guard.asked()] == ["a"]  # skipped nodes are never put to the guard
    assert result.outcome is RunOutcome.FAILED and result.dispatched == ("a",)


def test_a_failed_node_records_its_reason_verbatim():
    result, *_ = go({"a": ""}, work=ScriptedWork({"a": WorkResult.failed("the source was unreachable")}))
    assert result.result_for(StepId("a")).reason == "the source was unreachable"


def test_a_no_result_predecessor_skips_its_descendants():
    script = {"a": WorkResult.no_result("nothing came back")}
    result, work, *_ = go({"a": "", "b": "a"}, work=ScriptedWork(script))
    assert statuses(result) == {"a": "no_result", "b": "skipped"}
    assert result.result_for(StepId("b")).reason == "not dispatched: predecessor(s) did not succeed: 'a' (no_result)"
    assert work.calls == ["a"] and result.outcome is RunOutcome.FAILED


@pytest.mark.parametrize(
    "verdict, expected",
    [
        (VerificationResult.failed("claim not supported"), "verification_failed"),
        (VerificationResult.inconclusive("not enough evidence"), "verification_inconclusive"),
    ],
)
def test_a_verification_that_did_not_pass_skips_its_descendants(verdict, expected):
    verifier = ScriptedVerifier({"v": verdict})
    result, work, verifier, *_ = go(
        {"a": "", "v": "a", "b": "v"}, verify=("v",), verifier=verifier
    )
    assert statuses(result) == {"a": "succeeded", "v": expected, "b": "skipped"}
    assert work.calls == ["a"] and verifier.calls == ["v"]
    assert result.result_for(StepId("b")).reason == f"not dispatched: predecessor(s) did not succeed: 'v' ({expected})"
    assert result.outcome is RunOutcome.FAILED


def test_skipping_propagates_through_skipped_nodes():
    result, *_ = go({"a": "", "b": "a", "c": "b", "d": "c"}, work=ScriptedWork({"a": WorkResult.failed("x")}))
    assert statuses(result) == {"a": "failed", "b": "skipped", "c": "skipped", "d": "skipped"}
    assert result.result_for(StepId("c")).reason == "not dispatched: predecessor(s) did not succeed: 'b' (skipped)"


def test_a_failed_a_to_b_and_a_to_c_skips_both():
    result, work, *_ = go({"a": "", "b": "a", "c": "a"}, work=ScriptedWork({"a": WorkResult.failed("x")}))
    assert statuses(result) == {"a": "failed", "b": "skipped", "c": "skipped"}
    assert work.calls == ["a"]


def test_independent_branch_continues_after_a_failure():
    # A -> B, C independent, and A fails: B is skipped, C still executes.
    result, work, *_ = go({"a": "", "b": "a", "c": ""}, work=ScriptedWork({"a": WorkResult.failed("x")}))
    assert statuses(result) == {"a": "failed", "b": "skipped", "c": "succeeded"}
    assert work.calls == ["a", "c"]
    assert result.outcome is RunOutcome.FAILED


def test_independent_branches_continue_through_every_later_level():
    spec = {"a": "", "b": "a", "c": "b", "x": "", "y": "x", "z": "y"}
    result, work, *_ = go(spec, work=ScriptedWork({"a": WorkResult.failed("x")}))
    assert statuses(result) == {
        "a": "failed", "b": "skipped", "c": "skipped", "x": "succeeded", "y": "succeeded", "z": "succeeded",
    }
    assert work.calls == ["a", "x", "y", "z"]


def test_a_join_is_skipped_if_any_one_predecessor_did_not_succeed_though_the_others_did():
    result, work, *_ = go({"x": "", "y": "", "join": "x y"}, work=ScriptedWork({"x": WorkResult.failed("boom")}))
    assert statuses(result) == {"x": "failed", "y": "succeeded", "join": "skipped"}
    assert work.calls == ["x", "y"]
    assert "'x' (failed)" in result.result_for(StepId("join")).reason


def test_a_skipped_join_names_every_blocking_predecessor_in_predecessor_order():
    script = {"y": WorkResult.failed("1"), "x": WorkResult.no_result("2")}
    result, *_ = go({"y": "", "x": "", "ok": "", "join": "x ok y"}, work=ScriptedWork(script))
    assert result.result_for(StepId("join")).reason == (
        "not dispatched: predecessor(s) did not succeed: 'x' (no_result), 'y' (failed)"
    )


def test_a_run_of_one_success_and_one_failure_in_a_fan_out_only_skips_the_descendants_of_the_failure():
    spec = {"root": "", "left": "root", "right": "root", "l2": "left", "r2": "right"}
    result, work, *_ = go(spec, work=ScriptedWork({"left": WorkResult.failed("x")}))
    assert statuses(result) == {
        "root": "succeeded", "left": "failed", "right": "succeeded", "l2": "skipped", "r2": "succeeded",
    }


# --- awaiting: a work port that dispatches without concluding (decisions.md D-165, V0.6 Step 3) -----
#
# Nothing in eidos.agents, eidos.providers or the V0.4 agents is touched by this step. ScriptedWork must be
# explicitly told to return WorkResult.submitted(...) for any of this to happen at all — no existing WorkExecutor
# implementation ever does.


def test_one_node_dispatches_and_reports_it_is_awaiting():
    result, work, *_ = go({"a": ""}, work=ScriptedWork({"a": WorkResult.submitted("dispatched; outcome pending")}))
    assert statuses(result) == {"a": "awaiting"}
    assert result.outcome is RunOutcome.AWAITING and result.halt is None
    assert [i.step_id for i in result.awaiting] == ["a"]
    assert work.calls == ["a"] and result.dispatched == ("a",)  # genuinely dispatched, unlike a halted node


def test_multiple_independently_submitted_nodes_are_all_reported():
    script = {"a": WorkResult.submitted("pending a"), "b": WorkResult.submitted("pending b")}
    result, work, *_ = go({"a": "", "b": ""}, work=ScriptedWork(script))
    assert statuses(result) == {"a": "awaiting", "b": "awaiting"}
    assert result.outcome is RunOutcome.AWAITING
    assert [i.step_id for i in result.awaiting] == ["a", "b"]
    assert work.calls == ["a", "b"]


def test_a_node_blocked_only_by_an_awaiting_predecessor_is_not_reached_not_skipped():
    # not_reached, not skipped: nothing has concluded unsuccessfully, so "did not succeed" would claim too much.
    result, work, *_ = go({"a": "", "b": "a"}, work=ScriptedWork({"a": WorkResult.submitted("pending")}))
    assert statuses(result) == {"a": "awaiting", "b": "not_reached"}
    assert result.result_for(StepId("b")).reason == "not dispatched: predecessor(s) have not concluded yet: 'a' (awaiting)"
    assert work.calls == ["a"]  # b's port was never called
    assert result.outcome is RunOutcome.AWAITING


def test_blocking_by_awaiting_propagates_transitively_through_not_reached_nodes():
    result, *_ = go({"a": "", "b": "a", "c": "b"}, work=ScriptedWork({"a": WorkResult.submitted("pending")}))
    assert statuses(result) == {"a": "awaiting", "b": "not_reached", "c": "not_reached"}
    assert result.result_for(StepId("c")).reason == "not dispatched: predecessor(s) have not concluded yet: 'b' (not_reached)"


def test_a_node_with_one_doomed_and_one_awaiting_predecessor_is_skipped_not_not_reached():
    # x has genuinely failed; waiting for y (still awaiting) would not change that join's fate.
    script = {"x": WorkResult.failed("boom"), "y": WorkResult.submitted("pending")}
    result, *_ = go({"x": "", "y": "", "join": "x y"}, work=ScriptedWork(script))
    assert statuses(result) == {"x": "failed", "y": "awaiting", "join": "skipped"}
    assert "'x' (failed)" in result.result_for(StepId("join")).reason


def test_independent_branches_continue_normally_after_an_awaiting_node_unlike_a_halt():
    # D-165: awaiting does not stop the run the way a halt does. An independent branch, and a later level that
    # does not depend on the awaiting node, both proceed and can even finish normally.
    spec = {"a": "", "b": "a", "x": "", "y": "x"}
    result, work, *_ = go(spec, work=ScriptedWork({"a": WorkResult.submitted("pending")}))
    assert statuses(result) == {"a": "awaiting", "b": "not_reached", "x": "succeeded", "y": "succeeded"}
    assert work.calls == ["a", "x", "y"]
    assert result.outcome is RunOutcome.AWAITING


def test_the_guard_is_still_asked_for_other_nodes_of_the_level_after_one_goes_awaiting():
    result, work, verifier, guard, _ = go(
        {"a": "", "b": ""}, work=ScriptedWork({"a": WorkResult.submitted("pending")})
    )
    assert [r[0] for r in guard.asked()] == ["a", "b"]
    assert work.calls == ["a", "b"]


def test_an_admission_halt_takes_precedence_over_an_independently_awaiting_node():
    # a (level 1) is submitted and awaiting; c (level 2) is halted. The run's outcome is HALTED (D-165's
    # extension of D-118 rule 4), and a is still named in RunResult.awaiting — nothing about it is hidden.
    spec = {"a": "", "b": "a", "c": ""}
    guard = halt_when(lambda r: r.step_id == "c")
    result, work, *_ = go(spec, work=ScriptedWork({"a": WorkResult.submitted("pending")}), guard=guard)
    assert statuses(result) == {"a": "awaiting", "b": "not_reached", "c": "not_reached"}
    assert result.outcome is RunOutcome.HALTED
    assert [i.step_id for i in result.awaiting] == ["a"]


def test_an_awaiting_node_never_stops_a_verify_node_from_being_skipped_the_ordinary_way():
    # v depends on the awaiting node a: v is not_reached (D-165's pending case), same as any other descendant.
    result, work, verifier, *_ = go(
        {"a": "", "v": "a"}, verify=("v",), work=ScriptedWork({"a": WorkResult.submitted("pending")})
    )
    assert statuses(result) == {"a": "awaiting", "v": "not_reached"}
    assert verifier.calls == []


def test_an_awaiting_run_is_never_verified_even_if_a_verify_node_already_passed():
    spec = {"a": "", "v": "a", "z": ""}
    result, *_ = go(spec, verify=("v",), work=ScriptedWork({"z": WorkResult.submitted("pending")}))
    assert result.result_for(StepId("v")).status is S.SUCCEEDED
    assert result.outcome is RunOutcome.AWAITING and result.verified is False


def test_the_results_carry_the_runs_identity_the_same_way_for_an_awaiting_run():
    result, _, _, _, compiled = go({"a": ""}, work=ScriptedWork({"a": WorkResult.submitted("pending")}), version=4)
    context = context_for(compiled)
    assert (result.tenant_id, result.mission_id, result.execution_id) == (
        compiled.tenant_id, compiled.mission_id, context.execution_id,
    )
    assert (result.plan_id, result.plan_version) == (compiled.plan_id, 4)


# --- nothing is retried; each node is dispatched at most once ---------------------------------------


def test_a_failing_node_is_dispatched_exactly_once_and_never_retried():
    work = ScriptedWork({"a": WorkResult.failed("x")})
    result, *_ = go({"a": ""}, work=work)
    assert work.calls == ["a"]
    assert result.dispatched == ("a",)


def test_no_node_is_ever_dispatched_twice_in_a_mixed_run():
    spec = {"a": "", "b": "a", "c": "a", "v": "b c", "d": "v", "e": ""}
    work = ScriptedWork({"b": WorkResult.no_result("x")})
    verifier = ScriptedVerifier()
    result, work, verifier, *_ = go(spec, verify=("v",), work=work, verifier=verifier)
    everything = work.calls + verifier.calls
    assert len(everything) == len(set(everything))
    assert len(result.dispatched) == len(set(result.dispatched))


# --- the work port ------------------------------------------------------------------------------------


def test_the_work_executor_gets_the_frozen_context_and_the_compiled_work_node():
    result, work, _, _, compiled = go({"a": ""})
    assert work.contexts[0] == context_for(compiled)
    (node,) = work.nodes
    assert node is compiled.nodes[0]  # the compiled node itself, not a copy or an agent handle
    assert node.capability == "research"  # a requested capability; never a named agent
    assert not hasattr(node, "agent") and not hasattr(node, "agent_id")


def test_an_executor_result_of_failed_or_no_result_maps_to_the_matching_status():
    script = {"f": WorkResult.failed("f"), "n": WorkResult.no_result("n")}
    result, *_ = go({"f": "", "n": ""}, work=ScriptedWork(script))
    assert statuses(result) == {"f": "failed", "n": "no_result"}
    assert result.result_for(StepId("n")).reason == "n"


def test_an_executor_that_raises_is_caught_and_recorded_as_failed():
    work = ScriptedWork({"a": RuntimeError("kaboom")})
    result, *_ = go({"a": "", "b": "a", "c": ""}, work=work)  # must not raise
    assert isinstance(result, RunResult)
    assert statuses(result) == {"a": "failed", "b": "skipped", "c": "succeeded"}
    assert result.result_for(StepId("a")).reason == "the work executor raised RuntimeError: kaboom"
    assert work.calls == ["a", "c"]  # the independent branch still ran


def test_an_exception_with_no_message_still_gives_a_reason():
    result, *_ = go({"a": ""}, work=ScriptedWork({"a": ValueError()}))
    assert result.result_for(StepId("a")).reason == "the work executor raised ValueError"


@pytest.mark.parametrize("bad", [None, "artifact:a", {"artifact": "a"}, 7])
def test_an_executor_that_returns_something_that_is_not_a_work_result_is_a_failure_not_a_leak(bad):
    result, *_ = go({"a": ""}, work=ScriptedWork({"a": lambda context, node: bad}))
    assert result.result_for(StepId("a")).status is S.FAILED
    assert f"returned {type(bad).__name__}, not a WorkResult" in result.result_for(StepId("a")).reason


# --- the verify node -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "verdict, status, outcome",
    [
        (VerificationResult.passed("supported"), "succeeded", RunOutcome.FINISHED),
        (VerificationResult.failed("contradicted"), "verification_failed", RunOutcome.FAILED),
        (VerificationResult.inconclusive("insufficient"), "verification_inconclusive", RunOutcome.FAILED),
    ],
)
def test_a_verdict_maps_to_its_status_and_keeps_the_verifiers_reason(verdict, status, outcome):
    result, _, verifier, *_ = go(
        {"a": "", "v": "a"}, verify=("v",), verifier=ScriptedVerifier({"v": verdict})
    )
    node = result.result_for(StepId("v"))
    assert node.status.value == status and node.reason == verdict.reason
    assert node.artifact is None
    assert result.outcome is outcome
    assert verifier.calls == ["v"]  # called exactly once


def test_the_verifier_is_called_exactly_once_with_the_predecessors_results_in_predecessor_order():
    result, work, verifier, *_ = go({"a": "", "b": "", "v": "b a"}, verify=("v",))
    assert verifier.calls == ["v"]
    (received,) = verifier.received
    assert [r.step_id for r in received] == ["b", "a"]
    assert [r.artifact for r in received] == [artifact_of("b"), artifact_of("a")]
    assert all(r.status is S.SUCCEEDED for r in received)


def test_a_verify_node_after_another_verify_node_receives_its_reason_and_no_artifact():
    result, _, verifier, *_ = go({"a": "", "v1": "a", "v2": "v1"}, verify=("v1", "v2"))
    (_, second) = verifier.received
    assert [r.step_id for r in second] == ["v1"] and second[0].artifact is None and second[0].reason == "verified"


def test_a_verifier_that_raises_is_a_failure_never_a_pass_or_an_inconclusive():
    verifier = ScriptedVerifier({"v": RuntimeError("verifier down")})
    result, *_ = go({"a": "", "v": "a", "b": "v"}, verify=("v",), verifier=verifier)
    node = result.result_for(StepId("v"))
    assert node.status is S.FAILED
    assert node.reason == "the verifier raised RuntimeError: verifier down"
    assert result.result_for(StepId("b")).status is S.SKIPPED
    assert result.outcome is RunOutcome.FAILED and result.verified is False


@pytest.mark.parametrize("bad", [None, "pass", True, {"verdict": "pass"}])
def test_a_verifier_that_returns_something_else_is_a_failure_not_a_verdict(bad):
    verifier = ScriptedVerifier({"v": lambda context, node, predecessors: bad})
    result, *_ = go({"a": "", "v": "a"}, verify=("v",), verifier=verifier)
    node = result.result_for(StepId("v"))
    assert node.status is S.FAILED and "not a VerificationResult" in node.reason


def test_a_verify_node_behind_a_failed_predecessor_is_skipped_and_never_verified():
    verifier = ScriptedVerifier()
    result, work, verifier, *_ = go(
        {"a": "", "v": "a"}, verify=("v",), work=ScriptedWork({"a": WorkResult.failed("x")}), verifier=verifier
    )
    assert statuses(result) == {"a": "failed", "v": "skipped"}
    assert verifier.calls == []


def test_the_verifier_receives_the_same_context():
    result, _, verifier, _, compiled = go({"a": "", "v": "a"}, verify=("v",))
    assert verifier.contexts == [context_for(compiled)]


def test_verify_nodes_are_put_to_the_admission_guard_like_any_dispatch():
    _, _, _, guard, _ = go({"a": "", "v": "a"}, verify=("v",))
    assert guard.asked() == [("a", 1, 0, 0), ("v", 2, 0, 1)]


# --- verified versus unverified -----------------------------------------------------------------------------


def test_a_finished_run_with_a_passing_verify_node_is_verified():
    result, *_ = go({"a": "", "v": "a"}, verify=("v",))
    assert result.outcome is RunOutcome.FINISHED and result.verified is True


def test_a_finished_run_with_no_verify_node_is_explicitly_unverified():
    result, *_ = go({"a": "", "b": "a"})
    assert result.outcome is RunOutcome.FINISHED and result.verified is False


def test_a_failed_verification_never_leaves_a_verified_run():
    verifier = ScriptedVerifier({"v": VerificationResult.failed("no")})
    result, *_ = go({"a": "", "v": "a"}, verify=("v",), verifier=verifier)
    assert result.verified is False and result.outcome is RunOutcome.FAILED


# --- admission and halting -----------------------------------------------------------------------------------


def test_the_guard_is_asked_once_per_dispatched_node_and_never_for_a_skipped_one():
    spec = {"a": "", "x": "", "b": "a", "c": "x"}
    _, _, _, guard, _ = go(spec, work=ScriptedWork({"a": WorkResult.failed("x")}))
    # b is skipped (never asked); c is the only level-2 node dispatched, so its rank is 0.
    assert guard.asked() == [("a", 1, 0, 0), ("x", 1, 1, 0), ("c", 2, 0, 2)]


def test_dispatched_before_level_counts_dispatches_including_failed_ones():
    spec = {"a": "", "b": "", "c": "a b"}
    _, _, _, guard, _ = go(spec, work=ScriptedWork({"a": WorkResult.failed("x")}))
    assert guard.asked() == [("a", 1, 0, 0), ("b", 1, 1, 0)]  # c is skipped, so never asked
    spec = {"a": "", "b": "", "c": "", "d": "a b c"}
    _, _, _, guard, _ = go(spec)
    assert guard.asked()[-1] == ("d", 2, 0, 3)


def test_a_halt_stops_dispatching_after_the_current_level_and_leaves_later_nodes_not_reached():
    guard = halt_when(lambda r: r.step_id == "b", "budget exhausted")
    result, work, *_ = go({"a": "", "b": "a", "c": "b"}, guard=guard)
    assert statuses(result) == {"a": "succeeded", "b": "not_reached", "c": "not_reached"}
    assert result.outcome is RunOutcome.HALTED
    assert result.halt == HaltInfo(step_id=StepId("b"), level=2, reason="budget exhausted")
    assert work.calls == ["a"] and result.dispatched == ("a",)
    assert result.result_for(StepId("b")).reason == "admission halted the run at this node: budget exhausted"
    assert result.result_for(StepId("c")).reason == "the run halted after level 2, before this node's level"


def test_the_other_nodes_of_the_halting_level_are_still_asked_and_still_run():
    # Level 2 is b, c, d; only b is denied. c and d run; the run halts after the level.
    guard = halt_when(lambda r: r.step_id == "b")
    result, work, *_ = go({"a": "", "b": "a", "c": "a", "d": "a", "e": "c"}, guard=guard)
    assert statuses(result) == {
        "a": "succeeded", "b": "not_reached", "c": "succeeded", "d": "succeeded", "e": "not_reached",
    }
    assert work.calls == ["a", "c", "d"]
    assert result.halt.step_id == "b" and result.halt.level == 2
    assert result.outcome is RunOutcome.HALTED


def test_nodes_of_the_halting_level_that_are_skipped_are_still_resolved_as_skipped():
    spec = {"a": "", "x": "", "b": "a", "c": "x", "d": "c"}
    guard = halt_when(lambda r: r.step_id == "c")
    result, *_ = go(spec, work=ScriptedWork({"a": WorkResult.failed("x")}), guard=guard)
    assert statuses(result) == {
        "a": "failed", "x": "succeeded", "b": "skipped", "c": "not_reached", "d": "not_reached",
    }
    assert result.halt.step_id == "c"


def test_a_halt_takes_precedence_over_an_earlier_failure():
    guard = halt_when(lambda r: r.level == 2)
    result, *_ = go({"a": "", "b": "a", "x": "", "y": "x"}, work=ScriptedWork({"a": WorkResult.failed("x")}), guard=guard)
    assert S.FAILED in {r.status for r in result.results}
    assert result.outcome is RunOutcome.HALTED


def test_a_halt_in_the_first_level_leaves_everything_not_reached():
    guard = halt_when(lambda r: True, "no budget at all")
    result, work, verifier, *_ = go({"a": "", "b": "a", "c": ""}, guard=guard)
    assert set(statuses(result).values()) == {"not_reached"}
    assert work.calls == [] and result.dispatched == ()
    assert result.halt == HaltInfo(step_id=StepId("a"), level=1, reason="no budget at all")
    assert result.verified is False


def test_a_halt_in_the_last_level_still_halts_the_run():
    guard = halt_when(lambda r: r.step_id == "c")
    result, *_ = go({"a": "", "b": "a", "c": "b"}, guard=guard)
    assert statuses(result) == {"a": "succeeded", "b": "succeeded", "c": "not_reached"}
    assert result.outcome is RunOutcome.HALTED


def test_a_halted_run_is_never_verified_even_if_a_verify_node_already_passed():
    guard = halt_when(lambda r: r.step_id == "z")
    result, *_ = go({"a": "", "v": "a", "z": "v"}, verify=("v",), guard=guard)
    assert result.result_for(StepId("v")).status is S.SUCCEEDED
    assert result.outcome is RunOutcome.HALTED and result.verified is False


def test_the_first_denied_node_in_level_and_rank_order_is_the_recorded_halt():
    guard = halt_when(lambda r: r.step_id in ("c", "d"), "stop")
    result, *_ = go({"a": "", "b": "a", "c": "a", "d": "a"}, guard=guard)
    assert result.halt.step_id == "c"
    assert statuses(result)["d"] == "not_reached"


def test_a_pure_rank_based_guard_admits_a_prefix_of_each_level():
    # A budget of 3 dispatches: root (1), then ranks 0 and 1 of the four-node level.
    guard = halt_when(lambda r: r.dispatched_before_level + r.rank_in_level >= 3, "3 dispatches used")
    result, work, *_ = go({"root": "", "a": "root", "b": "root", "c": "root", "d": "root"}, guard=guard)
    assert work.calls == ["root", "a", "b"]
    assert statuses(result) == {
        "root": "succeeded", "a": "succeeded", "b": "succeeded", "c": "not_reached", "d": "not_reached",
    }
    assert result.halt.step_id == "c" and result.outcome is RunOutcome.HALTED


def test_no_guard_call_is_made_for_a_level_after_a_halt():
    guard = halt_when(lambda r: r.step_id == "b")
    _, _, _, guard, _ = go({"a": "", "b": "a", "c": "b", "d": "c"}, guard=guard)
    assert [r.step_id for r in guard.requests] == ["a", "b"]


def test_a_guard_that_raises_fails_closed_and_halts_the_run():
    result, work, *_ = go({"a": "", "b": "a"}, guard=RaisingGuard())
    assert result.outcome is RunOutcome.HALTED
    assert work.calls == []  # nothing was dispatched without an answer
    assert result.halt.reason == "the admission guard raised RuntimeError: guard is broken"
    assert set(statuses(result).values()) == {"not_reached"}


@pytest.mark.parametrize("junk", [None, "admit", True, 1])
def test_a_guard_that_answers_with_anything_else_fails_closed(junk):
    result, work, *_ = go({"a": ""}, guard=JunkGuard(junk))
    assert result.outcome is RunOutcome.HALTED and work.calls == []
    assert f"returned {type(junk).__name__}, not an AdmissionDecision" in result.halt.reason


def test_there_is_no_default_guard_and_every_port_is_required_by_keyword():
    with pytest.raises(TypeError):
        SequentialExecutor()
    ports = dict(work_executor=ScriptedWork(), verifier=ScriptedVerifier(), admission_guard=admit_all())
    for missing in ports:
        with pytest.raises(TypeError):
            SequentialExecutor(**{k: v for k, v in ports.items() if k != missing})
    with pytest.raises(TypeError):
        SequentialExecutor(*ports.values())  # keyword-only


def test_the_executor_is_frozen_and_holds_only_its_three_ports():
    executor = make_executor()
    assert [f.name for f in dataclasses.fields(executor)] == ["work_executor", "verifier", "admission_guard"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        executor.admission_guard = admit_all()


def test_the_executor_keeps_no_state_between_runs():
    work = ScriptedWork()
    executor = make_executor(work)
    compiled = compiled_of({"a": "", "b": "a"})
    first = executor.run(compiled, context_for(compiled))
    second = executor.run(compiled, context_for(compiled))
    assert first == second
    assert work.calls == ["a", "b", "a", "b"]  # the recording is the test double's, not the executor's


# --- purity, immutability, MissionState, events ---------------------------------------------------------------


def test_running_never_mutates_the_compiled_plan_or_the_context():
    compiled = compiled_of({"a": "", "v": "a", "b": "v"}, verify=("v",))
    context = context_for(compiled)
    before = (compiled.model_dump_json(), context.model_dump_json())
    make_executor(ScriptedWork({"a": WorkResult.failed("x")})).run(compiled, context)
    assert (compiled.model_dump_json(), context.model_dump_json()) == before


def test_running_never_mutates_or_receives_mission_state():
    from eidos.runtime import context_from_state

    compiled = compiled_of({"a": "", "b": "a"})
    contract = make_reliability_contract(tenant_id=compiled.tenant_id)
    state = make_mission_state(
        tenant_id=compiled.tenant_id, mission_id=compiled.mission_id,
        reliability_contract=contract, task_genome=make_task_genome(contract=contract),
    )
    before = state.model_dump_json()
    result = make_executor().run(compiled, context_from_state(state, compiled))
    assert isinstance(result, RunResult)
    assert state.model_dump_json() == before
    assert list(inspect.signature(SequentialExecutor.run).parameters) == ["self", "compiled", "context", "prior"]


def test_a_run_result_is_a_plain_value_not_an_event():
    result, *_ = go({"a": ""})
    assert not {"event_id", "sequence", "occurred_at", "recorded_at", "type"} & set(RunResult.model_fields)
    assert not any(name in result.model_dump_json() for name in ("event_id", "recorded_at", "MISSION_"))


def test_a_run_over_the_same_inputs_is_repeatable():
    compiled = compiled_of({"a": "", "b": "a", "c": "", "v": "b c"}, verify=("v",))
    context = context_for(compiled)
    outcomes = [
        make_executor(ScriptedWork({"b": WorkResult.no_result("x")})).run(compiled, context) for _ in range(4)
    ]
    assert all(o == outcomes[0] for o in outcomes)
    assert len({o.model_dump_json() for o in outcomes}) == 1


def test_a_very_long_chain_runs_iteratively_without_hitting_the_recursion_limit():
    n = 3_000
    assert sys.getrecursionlimit() < n
    spec = {"s0": ""}
    for i in range(1, n):
        spec[f"s{i}"] = f"s{i - 1}"
    result, *_ = go(spec)
    assert result.outcome is RunOutcome.FINISHED and len(result.dispatched) == n
    assert result.dispatched[0] == "s0" and result.dispatched[-1] == f"s{n - 1}"


# --- a property test against an independent computation ------------------------------------------------------------


WORK_OUTCOMES = ["produced", "failed", "no_result"]
VERIFY_OUTCOMES = ["pass", "fail", "inconclusive"]


def _work_result(kind: str) -> WorkResult:
    return {"failed": WorkResult.failed("f"), "no_result": WorkResult.no_result("n")}.get(kind) or WorkResult.produced("art")


def _verdict(kind: str) -> VerificationResult:
    return {"pass": VerificationResult.passed("p"), "fail": VerificationResult.failed("f"),
            "inconclusive": VerificationResult.inconclusive("i")}[kind]


OWN_STATUS = {
    "produced": "succeeded", "failed": "failed", "no_result": "no_result",
    "pass": "succeeded", "fail": "verification_failed", "inconclusive": "verification_inconclusive",
}


def _random_case(seed: int):
    rng = random.Random(seed)
    n = rng.randint(1, 12)
    names = [f"n{i}" for i in range(n)]
    p = rng.choice([0.15, 0.35, 0.6])
    spec = {name: tuple(names[j] for j in range(i) if rng.random() < p) for i, name in enumerate(names)}
    order = names[:]
    rng.shuffle(order)  # plan order need not be topological
    spec = {name: spec[name] for name in order}
    verify = tuple(name for name in names if rng.random() < 0.3)
    outcomes = {
        name: rng.choice(VERIFY_OUTCOMES if name in verify else WORK_OUTCOMES) for name in names
    }
    return spec, verify, outcomes


def _expected(spec, outcomes):
    memo: dict = {}

    def status(name):
        if name not in memo:
            blocked = any(status(dep) != "succeeded" for dep in spec[name])
            memo[name] = "skipped" if blocked else OWN_STATUS[outcomes[name]]
        return memo[name]

    return {name: status(name) for name in spec}


def _run_case(seed, guard=None):
    spec, verify, outcomes = _random_case(seed)
    work = ScriptedWork({n: _work_result(o) for n, o in outcomes.items() if n not in verify})
    verifier = ScriptedVerifier({n: _verdict(o) for n, o in outcomes.items() if n in verify})
    result, work, verifier, guard, compiled = go(
        {k: " ".join(v) for k, v in spec.items()}, verify=verify, work=work, verifier=verifier, guard=guard
    )
    return spec, verify, outcomes, result, work, verifier, guard, compiled


@pytest.mark.parametrize("seed", range(60))
def test_statuses_match_an_independent_computation_on_random_plans(seed):
    spec, verify, outcomes, result, work, verifier, guard, compiled = _run_case(seed)
    assert statuses(result) == _expected(spec, outcomes)
    assert [r.step_id for r in result.results] == list(spec)  # plan order
    assert not any(r.status is S.NOT_REACHED for r in result.results)  # no halt, so all settled
    assert result.halt is None

    dispatched = [n for n, s in statuses(result).items() if s != "skipped"]
    level = {n.step_id: n.level for n in compiled.nodes}
    position = {n.step_id: n.position for n in compiled.nodes}
    assert list(result.dispatched) == sorted(dispatched, key=lambda s: (level[s], position[s]))
    calls = work.calls + verifier.calls
    assert sorted(calls) == sorted(dispatched) and len(calls) == len(set(calls))  # at most once

    finished = all(s == "succeeded" for s in statuses(result).values())
    assert result.outcome is (RunOutcome.FINISHED if finished else RunOutcome.FAILED)
    assert result.verified is (finished and bool(verify))


@pytest.mark.parametrize("seed", range(40))
def test_halting_invariants_hold_on_random_plans(seed):
    budget = random.Random(seed).randint(0, 6)
    guard = halt_when(lambda r: r.dispatched_before_level + r.rank_in_level >= budget, "budget")
    spec, verify, outcomes, result, work, verifier, _, compiled = _run_case(seed, guard)
    level = {n.step_id: n.level for n in compiled.nodes}
    by_status = statuses(result)
    assert len(work.calls) + len(verifier.calls) == len(result.dispatched)  # calls are exactly the dispatches
    if result.halt is None:
        assert "not_reached" not in by_status.values()
        return
    assert result.outcome is RunOutcome.HALTED
    halt_level = result.halt.level
    assert halt_level == min(level[s] for s, st in by_status.items() if st == "not_reached")
    for step, st in by_status.items():
        if level[step] > halt_level:
            assert st == "not_reached"  # a later level is never reached
        if level[step] < halt_level:
            assert st != "not_reached"  # earlier levels are fully resolved
    assert all(level[s] <= halt_level for s in result.dispatched)
    assert result.verified is False


def test_the_halting_property_test_really_exercises_both_halted_and_unhalted_runs():
    halted = 0
    for seed in range(40):
        budget = random.Random(seed).randint(0, 6)
        guard = halt_when(lambda r: r.dispatched_before_level + r.rank_in_level >= budget, "budget")
        result = _run_case(seed, guard)[3]
        halted += result.outcome is RunOutcome.HALTED
    assert 8 <= halted <= 32, halted  # both kinds occur, so the invariants above are not vacuous


# --- the same result under any process hash seed ----------------------------------------------------------------------


def test_results_are_identical_across_hash_seeds():
    # String hashing is randomized per process; a result may not depend on it.
    script = (
        "import sys\n"
        "sys.path[:0] = ['src', 'tests/support']\n"
        "from uuid import UUID\n"
        "from eidos.contracts import *\n"
        "from eidos.runtime import *\n"
        "from eidos_runtime_factories import *\n"
        "names = ['step_%d' % i for i in range(30)]\n"
        "spec = {n: ' '.join(m for m in names[:i] if (i * 5 + int(m[5:]) * 3) % 4 == 0) for i, n in enumerate(names)}\n"
        "verify = tuple(n for i, n in enumerate(names) if i % 7 == 6)\n"
        "ids = dict(tenant_id=TenantId(UUID(int=1)), mission_id=MissionId(UUID(int=2)), plan_id=PlanId(UUID(int=3)))\n"
        "compiled = compiled_of(dict(reversed(list(spec.items()))), verify=verify, **ids)\n"
        "work = ScriptedWork({'step_3': WorkResult.failed('x'), 'step_9': WorkResult.no_result('y')})\n"
        "verifier = ScriptedVerifier({'step_13': VerificationResult.inconclusive('z')})\n"
        "guard = halt_when(lambda r: r.dispatched_before_level + r.rank_in_level >= 20)\n"
        "print(make_executor(work, verifier, guard).run(compiled, context_for(compiled)).model_dump_json())\n"
    )
    root = Path(__file__).resolve().parents[3]
    outputs = set()
    for seed in ("0", "1", "4242", "random"):
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, cwd=root,
            env=dict(os.environ, PYTHONHASHSEED=seed),
        )
        assert result.returncode == 0, result.stderr
        outputs.add(result.stdout)
    assert len(outputs) == 1
    document = json.loads(outputs.pop())
    statuses_seen = {r["status"] for r in document["results"]}
    assert {"succeeded", "failed", "skipped"} <= statuses_seen  # a real, varied run was compared
