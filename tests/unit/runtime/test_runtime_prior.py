"""Prior outcomes, resume and run preconditions (decisions.md D-113, D-119, D-120)."""

from uuid import UUID

import pytest

from eidos.contracts import ExecutionId, MissionId, PlanId, PlanStepKind, StepId, TenantId
from eidos.runtime import (
    NodeResult,
    NodeStatus,
    PriorOutcomes,
    RunOutcome,
    RunRejection,
    RunRejectionCode,
    RunResult,
    VerificationResult,
    WorkResult,
    check_run_preconditions,
)

from eidos_runtime_factories import (
    EXECUTION_ID,
    ScriptedVerifier,
    ScriptedWork,
    admit_all,
    artifact_of,
    compiled_of,
    context_for,
    halt_when,
    make_executor,
    statuses,
    succeeded_result,
)

Code = RunRejectionCode
S = NodeStatus


def prior_for(compiled, *outcomes, **overrides) -> PriorOutcomes:
    fields = dict(
        tenant_id=compiled.tenant_id,
        mission_id=compiled.mission_id,
        execution_id=EXECUTION_ID,
        plan_id=compiled.plan_id,
        plan_version=compiled.plan_version,
        outcomes=tuple(outcomes),
    )
    fields.update(overrides)
    return PriorOutcomes(**fields)


def run(compiled, prior=None, *, work=None, verifier=None, guard=None, context=None):
    work = work if work is not None else ScriptedWork()
    verifier = verifier if verifier is not None else ScriptedVerifier()
    guard = guard if guard is not None else admit_all()
    result = make_executor(work, verifier, guard).run(compiled, context or context_for(compiled), prior)
    return result, work, verifier, guard


def node_result(step_id, status, kind=PlanStepKind.AGENT, reason="because"):
    return NodeResult(step_id=StepId(step_id), kind=kind, status=status, reason=reason)


# --- resuming ---------------------------------------------------------------------------------------


def test_a_prior_succeeded_node_is_carried_over_and_never_redispatched():
    compiled = compiled_of({"a": "", "b": "a"})
    prior = prior_for(compiled, succeeded_result("a"))
    result, work, _, guard = run(compiled, prior)
    assert isinstance(result, RunResult)
    assert work.calls == ["b"]  # a is not called again
    assert result.dispatched == ("b",)
    assert [r[0] for r in guard.asked()] == ["b"]  # nor put to the guard
    assert statuses(result) == {"a": "succeeded", "b": "succeeded"}
    assert result.result_for(StepId("a")) == succeeded_result("a")  # carried over exactly
    assert result.outcome is RunOutcome.FINISHED


def test_descendants_of_a_prior_node_execute_normally():
    compiled = compiled_of({"a": "", "b": "a", "c": "b", "d": "a"})
    result, work, *_ = run(compiled, prior_for(compiled, succeeded_result("a")))
    assert work.calls == ["b", "d", "c"]  # level 2 (b, d) then level 3 (c)
    assert statuses(result) == {"a": "succeeded", "b": "succeeded", "c": "succeeded", "d": "succeeded"}


def test_a_prior_node_in_a_later_level_still_lets_the_others_run():
    compiled = compiled_of({"a": "", "b": "a", "x": "", "y": "x"})
    prior = prior_for(compiled, succeeded_result("a"), succeeded_result("b"))
    result, work, *_ = run(compiled, prior)
    assert work.calls == ["x", "y"]
    assert result.dispatched == ("x", "y")


def test_every_node_prior_succeeded_means_zero_calls_to_any_port():
    compiled = compiled_of({"a": "", "v": "a", "b": "v"}, verify=("v",))
    prior = prior_for(compiled, succeeded_result("a"), succeeded_result("v", verify=True), succeeded_result("b"))
    result, work, verifier, guard = run(compiled, prior)
    assert work.calls == [] and verifier.calls == [] and guard.requests == []
    assert result.dispatched == ()
    assert result.outcome is RunOutcome.FINISHED
    assert result.results == prior.outcomes
    assert result.verified is True  # a prior successful VERIFY node counts: the run's results say so


def test_a_resumed_run_hands_the_prior_artifacts_to_the_verifier():
    compiled = compiled_of({"a": "", "v": "a"}, verify=("v",))
    result, work, verifier, _ = run(compiled, prior_for(compiled, succeeded_result("a")))
    assert work.calls == []
    (received,) = verifier.received
    assert received == (succeeded_result("a"),) and received[0].artifact == artifact_of("a")


def test_resuming_after_a_failure_reruns_only_what_did_not_succeed():
    compiled = compiled_of({"a": "", "b": "a", "c": "b"})
    first, work1, *_ = run(compiled, work=ScriptedWork({"b": WorkResult.failed("transient")}))
    assert statuses(first) == {"a": "succeeded", "b": "failed", "c": "skipped"}

    second, work2, *_ = run(compiled, PriorOutcomes.succeeded_from(first))
    assert work2.calls == ["b", "c"]  # a was not called again
    assert second.outcome is RunOutcome.FINISHED
    assert second.dispatched == ("b", "c")


def test_resuming_a_halted_run_completes_it_without_redispatching_the_first_level():
    compiled = compiled_of({"a": "", "b": "a", "c": "b"})
    halted, work1, *_ = run(compiled, guard=halt_when(lambda r: r.level == 2))
    assert halted.outcome is RunOutcome.HALTED and work1.calls == ["a"]

    resumed, work2, *_ = run(compiled, PriorOutcomes.succeeded_from(halted))
    assert work2.calls == ["b", "c"]
    assert resumed.outcome is RunOutcome.FINISHED and resumed.halt is None


def test_a_chain_of_resumes_keeps_carrying_earlier_successes():
    compiled = compiled_of({"a": "", "b": "a", "c": "b", "d": "c"})
    run1, *_ = run(compiled, guard=halt_when(lambda r: r.level == 2))
    run2, work2, *_ = run(
        compiled, PriorOutcomes.succeeded_from(run1), guard=halt_when(lambda r: r.level == 4)
    )
    assert work2.calls == ["b", "c"] and run2.outcome is RunOutcome.HALTED
    prior2 = PriorOutcomes.succeeded_from(run2)
    assert [o.step_id for o in prior2.outcomes] == ["a", "b", "c"]  # a is carried through run 2
    run3, work3, *_ = run(compiled, prior2)
    assert work3.calls == ["d"] and run3.outcome is RunOutcome.FINISHED


def test_prior_state_does_not_bypass_admission_for_the_nodes_that_do_run():
    compiled = compiled_of({"a": "", "b": "a"})
    result, work, *_ = run(
        compiled, prior_for(compiled, succeeded_result("a")), guard=halt_when(lambda r: True, "no budget")
    )
    assert work.calls == [] and result.outcome is RunOutcome.HALTED
    assert statuses(result) == {"a": "succeeded", "b": "not_reached"}


def test_rank_and_dispatch_counts_ignore_nodes_settled_by_prior_outcomes():
    compiled = compiled_of({"a": "", "b": "", "c": "", "d": "a b c"})
    _, _, _, guard = run(compiled, prior_for(compiled, succeeded_result("a")))
    assert guard.asked() == [("b", 1, 0, 0), ("c", 1, 1, 0), ("d", 2, 0, 2)]


# --- invalid prior state is rejected, never adapted -----------------------------------------------------


@pytest.mark.parametrize(
    "status, kind",
    [
        (S.FAILED, PlanStepKind.AGENT),
        (S.NO_RESULT, PlanStepKind.AGENT),
        (S.SKIPPED, PlanStepKind.AGENT),
        (S.NOT_REACHED, PlanStepKind.AGENT),
        (S.VERIFICATION_FAILED, PlanStepKind.VERIFY),
        (S.VERIFICATION_INCONCLUSIVE, PlanStepKind.VERIFY),
        (S.FAILED, PlanStepKind.VERIFY),
    ],
)
def test_a_prior_outcome_that_is_not_succeeded_is_rejected_not_treated_as_success(status, kind):
    compiled = compiled_of({"a": "", "v": "a"}, verify=("v",))
    step = "v" if kind is PlanStepKind.VERIFY else "a"
    prior = prior_for(compiled, node_result(step, status, kind))
    result, work, verifier, guard = run(compiled, prior)
    assert isinstance(result, RunRejection) and result.code is Code.INVALID_PRIOR_STATE
    assert result.step_ids == (step,) and status.value in result.message
    assert work.calls == [] and verifier.calls == [] and guard.requests == []  # nothing was dispatched


def test_a_prior_outcome_for_an_unknown_step_is_rejected():
    compiled = compiled_of({"a": ""})
    result, work, *_ = run(compiled, prior_for(compiled, succeeded_result("ghost")))
    assert result.code is Code.INVALID_PRIOR_STATE and result.step_ids == ("ghost",)
    assert "not a node of this plan" in result.message and work.calls == []


def test_a_prior_outcome_of_the_wrong_kind_for_its_node_is_rejected():
    compiled = compiled_of({"a": "", "v": "a"}, verify=("v",))
    wrong = succeeded_result("a", verify=True)  # says 'a' was a VERIFY node
    result, *_ = run(compiled, prior_for(compiled, wrong))
    assert result.code is Code.INVALID_PRIOR_STATE and "is of kind 'VERIFY'" in result.message


def test_a_succeeded_node_whose_predecessor_has_no_prior_outcome_is_a_contradiction():
    compiled = compiled_of({"a": "", "b": "a"})
    result, work, *_ = run(compiled, prior_for(compiled, succeeded_result("b")))  # b, but not a
    assert result.code is Code.INVALID_PRIOR_STATE
    assert result.step_ids == ("b", "a")
    assert "predecessor 'a' has no succeeded prior outcome" in result.message
    assert work.calls == []  # not adapted: the run does not quietly re-run a


def test_a_deeper_contradiction_is_found_too():
    compiled = compiled_of({"a": "", "b": "a", "c": "b"})
    result, *_ = run(compiled, prior_for(compiled, succeeded_result("a"), succeeded_result("c")))
    assert result.code is Code.INVALID_PRIOR_STATE and result.step_ids == ("c", "b")


def test_a_prior_naming_a_step_twice_cannot_even_be_constructed():
    compiled = compiled_of({"a": ""})
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="duplicate prior outcome"):
        prior_for(compiled, succeeded_result("a"), succeeded_result("a"))


def test_the_first_invalid_prior_outcome_in_the_given_order_is_the_one_reported():
    compiled = compiled_of({"a": "", "b": ""})
    prior = prior_for(compiled, node_result("b", S.FAILED), node_result("a", S.SKIPPED))
    assert run(compiled, prior)[0].step_ids == ("b",)


# --- the prior must belong to this run ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field, value",
    [
        ("tenant_id", TenantId(UUID(int=901))),
        ("mission_id", MissionId(UUID(int=902))),
        ("execution_id", ExecutionId(UUID(int=903))),
        ("plan_id", PlanId(UUID(int=904))),
        ("plan_version", 77),
    ],
)
def test_a_prior_from_another_tenant_mission_execution_plan_or_version_is_rejected(field, value):
    compiled = compiled_of({"a": "", "b": "a"})
    prior = prior_for(compiled, succeeded_result("a"), **{field: value})
    result, work, *_ = run(compiled, prior)
    assert isinstance(result, RunRejection) and result.code is Code.INVALID_PRIOR_STATE
    assert f"prior outcomes' {field}" in result.message
    assert work.calls == []


def test_a_prior_of_plan_version_one_cannot_seed_a_run_of_version_two():
    v1 = compiled_of({"a": ""}, version=1)
    v2 = compiled_of({"a": "", "b": "a"}, version=2, tenant_id=v1.tenant_id, mission_id=v1.mission_id)
    stale = prior_for(v1, succeeded_result("a"))
    result, work, *_ = run(v2, stale)
    assert result.code is Code.INVALID_PRIOR_STATE and work.calls == []


# --- context preconditions --------------------------------------------------------------------------------------


def test_a_matching_context_and_no_prior_is_accepted():
    compiled = compiled_of({"a": ""})
    assert check_run_preconditions(compiled, context_for(compiled), None) is None


@pytest.mark.parametrize(
    "override, code",
    [
        (dict(tenant_id=TenantId(UUID(int=801))), Code.WRONG_TENANT),
        (dict(mission_id=MissionId(UUID(int=802))), Code.WRONG_MISSION),
        (dict(plan_id=PlanId(UUID(int=803))), Code.WRONG_PLAN),
        (dict(plan_version=9), Code.WRONG_PLAN_VERSION),
    ],
)
def test_a_context_for_another_tenant_mission_plan_or_version_is_rejected(override, code):
    compiled = compiled_of({"a": "", "b": "a"})
    result, work, verifier, guard = run(compiled, context=context_for(compiled, **override))
    assert isinstance(result, RunRejection) and result.code is code
    assert work.calls == [] and verifier.calls == [] and guard.requests == []
    assert result.step_ids == ()


def test_a_run_of_the_wrong_plan_is_refused_not_run_under_the_wrong_context():
    # The replan case: a context built for plan v1 must not silently run v2.
    v1 = compiled_of({"a": ""}, version=1)
    v2 = compiled_of({"a": "", "b": "a"}, version=2, tenant_id=v1.tenant_id, mission_id=v1.mission_id)
    stale_context = context_for(v1)
    result, work, *_ = run(v2, context=stale_context)
    assert result.code is Code.WRONG_PLAN and work.calls == []


def test_preconditions_are_checked_in_a_fixed_order_tenant_then_mission_then_plan_then_version():
    compiled = compiled_of({"a": ""})
    tenant = TenantId(UUID(int=701))
    everything_wrong = context_for(
        compiled,
        tenant_id=tenant,
        mission_id=MissionId(UUID(int=702)),
        plan_id=PlanId(UUID(int=703)),
        plan_version=9,
    )
    assert check_run_preconditions(compiled, everything_wrong, None).code is Code.WRONG_TENANT
    no_tenant_issue = context_for(
        compiled, mission_id=MissionId(UUID(int=702)), plan_id=PlanId(UUID(int=703)), plan_version=9
    )
    assert check_run_preconditions(compiled, no_tenant_issue, None).code is Code.WRONG_MISSION
    no_mission_issue = context_for(compiled, plan_id=PlanId(UUID(int=703)), plan_version=9)
    assert check_run_preconditions(compiled, no_mission_issue, None).code is Code.WRONG_PLAN
    assert check_run_preconditions(compiled, context_for(compiled, plan_version=9), None).code is Code.WRONG_PLAN_VERSION


def test_context_problems_are_reported_before_prior_problems():
    compiled = compiled_of({"a": ""})
    prior = prior_for(compiled, node_result("a", S.FAILED))
    bad_context = context_for(compiled, plan_version=9)
    assert check_run_preconditions(compiled, bad_context, prior).code is Code.WRONG_PLAN_VERSION


def test_a_rejection_is_returned_never_raised_and_names_the_mismatch():
    compiled = compiled_of({"a": ""})
    result = make_executor().run(compiled, context_for(compiled, plan_version=9))  # no exception
    assert result.code is Code.WRONG_PLAN_VERSION
    assert "plan version 9" in result.message and "version 1" in result.message


# --- nothing is mutated ---------------------------------------------------------------------------------------------


def test_running_with_a_prior_never_mutates_the_prior_the_compiled_plan_or_the_context():
    compiled = compiled_of({"a": "", "b": "a", "c": "b"})
    context = context_for(compiled)
    prior = prior_for(compiled, succeeded_result("a"))
    before = (prior.model_dump_json(), compiled.model_dump_json(), context.model_dump_json())
    run(compiled, prior, work=ScriptedWork({"b": WorkResult.failed("x")}), context=context)
    assert (prior.model_dump_json(), compiled.model_dump_json(), context.model_dump_json()) == before


def test_the_same_prior_can_seed_several_runs_with_equal_results():
    compiled = compiled_of({"a": "", "b": "a", "c": "a"})
    prior = prior_for(compiled, succeeded_result("a"))
    results = [run(compiled, prior)[0] for _ in range(3)]
    assert all(r == results[0] for r in results)


def test_a_rejected_run_leaves_everything_untouched_and_a_valid_retry_of_the_same_inputs_works():
    compiled = compiled_of({"a": "", "b": "a"})
    bad = prior_for(compiled, succeeded_result("b"))
    assert isinstance(run(compiled, bad)[0], RunRejection)
    assert isinstance(run(compiled, bad)[0], RunRejection)  # repeatable
    good = prior_for(compiled, succeeded_result("a"), succeeded_result("b"))
    assert run(compiled, good)[0].outcome is RunOutcome.FINISHED


def test_replan_is_a_new_plan_run_from_scratch_not_a_mutation_of_the_first():
    # D-119: a replan is a caller-supplied new Plan, validated, compiled and executed separately.
    v1 = compiled_of({"a": "", "b": "a"}, version=1)
    failed, *_ = run(v1, work=ScriptedWork({"b": WorkResult.failed("insufficient evidence")}))
    snapshot = v1.model_dump_json()

    v2 = compiled_of(
        {"a": "", "c": "a"}, version=2, tenant_id=v1.tenant_id, mission_id=v1.mission_id,
        parent_plan_id=v1.plan_id, replan_reason="insufficient evidence",
    )
    second, work2, *_ = run(v2)
    assert failed.plan_version == 1 and second.plan_version == 2
    assert failed.plan_id != second.plan_id
    assert work2.calls == ["a", "c"]  # a fresh run: nothing carried across plan versions
    assert v1.model_dump_json() == snapshot
    assert statuses(failed)["b"] == "failed" and statuses(second)["c"] == "succeeded"
