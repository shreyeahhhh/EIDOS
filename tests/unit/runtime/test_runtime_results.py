"""Runtime result types (decisions.md D-117, D-118, D-119, D-120, D-121, D-123)."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from eidos.contracts import ExecutionId, MissionId, PlanId, PlanStepKind, StepId, TenantId
from eidos.runtime import (
    HaltInfo,
    NodeResult,
    NodeStatus,
    PriorOutcomes,
    RunOutcome,
    RunRejection,
    RunRejectionCode,
    RunResult,
)

WORK, VERIFY = PlanStepKind.AGENT, PlanStepKind.VERIFY
IDS = dict(
    tenant_id=TenantId(UUID(int=1)),
    mission_id=MissionId(UUID(int=2)),
    execution_id=ExecutionId(UUID(int=3)),
    plan_id=PlanId(UUID(int=4)),
    plan_version=1,
)


def node(step_id, status, kind=WORK, **fields) -> NodeResult:
    if status is NodeStatus.SUCCEEDED:
        fields.setdefault("artifact" if kind is WORK else "reason", f"art:{step_id}" if kind is WORK else "verified")
    elif "reason" not in fields:
        fields["reason"] = "because"
    return NodeResult(step_id=StepId(step_id), kind=kind, status=status, **fields)


def run(results, *, outcome=None, halt=None, dispatched=None, **overrides) -> RunResult:
    """A RunResult; unspecified outcome/dispatched are derived the honest way."""
    results = tuple(results)
    if outcome is None:
        if halt is not None:
            outcome = RunOutcome.HALTED
        elif all(r.status is NodeStatus.SUCCEEDED for r in results):
            outcome = RunOutcome.FINISHED
        else:
            outcome = RunOutcome.FAILED
    if dispatched is None:
        dispatched = tuple(
            r.step_id for r in results if r.status not in (NodeStatus.SKIPPED, NodeStatus.NOT_REACHED)
        )
    return RunResult(**{**IDS, "outcome": outcome, "halt": halt, "results": results,
                        "dispatched": tuple(dispatched), **overrides})


# --- the vocabularies ---------------------------------------------------------------


def test_node_statuses_are_exactly_the_seven_of_d118():
    assert [s.value for s in NodeStatus] == [
        "succeeded",
        "failed",
        "no_result",
        "verification_failed",
        "verification_inconclusive",
        "skipped",
        "not_reached",
    ]


def test_run_outcomes_are_exactly_the_three_of_d118():
    assert [o.value for o in RunOutcome] == ["finished", "failed", "halted"]


def test_no_status_or_outcome_is_named_success_or_completed():
    # D-118: FINISHED is not verified success, and nothing here may suggest it is.
    names = {s.name for s in NodeStatus} | {o.name for o in RunOutcome}
    assert not names & {"SUCCESS", "COMPLETED", "VERIFIED", "OK", "DONE"}


# --- NodeResult ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind, status, fields",
    [
        (WORK, NodeStatus.SUCCEEDED, dict(artifact="art:a")),
        (VERIFY, NodeStatus.SUCCEEDED, dict(reason="all claims supported")),
        (WORK, NodeStatus.FAILED, dict(reason="executor failed")),
        (VERIFY, NodeStatus.FAILED, dict(reason="verifier raised")),
        (WORK, NodeStatus.NO_RESULT, dict(reason="nothing produced")),
        (VERIFY, NodeStatus.VERIFICATION_FAILED, dict(reason="claim unsupported")),
        (VERIFY, NodeStatus.VERIFICATION_INCONCLUSIVE, dict(reason="evidence insufficient")),
        (WORK, NodeStatus.SKIPPED, dict(reason="predecessor did not succeed")),
        (VERIFY, NodeStatus.SKIPPED, dict(reason="predecessor did not succeed")),
        (WORK, NodeStatus.NOT_REACHED, dict(reason="run halted")),
        (VERIFY, NodeStatus.NOT_REACHED, dict(reason="run halted")),
    ],
)
def test_every_status_has_a_valid_shape(kind, status, fields):
    result = NodeResult(step_id=StepId("a"), kind=kind, status=status, **fields)
    assert (result.step_id, result.kind, result.status) == ("a", kind, status)


@pytest.mark.parametrize(
    "kind, status, fields, why",
    [
        (WORK, NodeStatus.SUCCEEDED, dict(), "artifact"),  # a usable result needs an artifact
        (WORK, NodeStatus.SUCCEEDED, dict(artifact="a", reason="r"), "artifact"),
        (VERIFY, NodeStatus.SUCCEEDED, dict(), "reason"),
        (VERIFY, NodeStatus.SUCCEEDED, dict(artifact="a", reason="r"), "reason"),
        (WORK, NodeStatus.FAILED, dict(), "state why"),
        (WORK, NodeStatus.FAILED, dict(artifact="a", reason="r"), "no artifact"),
        (WORK, NodeStatus.NO_RESULT, dict(), "state why"),
        (VERIFY, NodeStatus.NO_RESULT, dict(reason="r"), "belongs to a work node"),
        (WORK, NodeStatus.VERIFICATION_FAILED, dict(reason="r"), "belongs to a verify node"),
        (WORK, NodeStatus.VERIFICATION_INCONCLUSIVE, dict(reason="r"), "belongs to a verify node"),
        (VERIFY, NodeStatus.VERIFICATION_FAILED, dict(), "state why"),
        (WORK, NodeStatus.SKIPPED, dict(), "state why"),
        (WORK, NodeStatus.NOT_REACHED, dict(), "state why"),
        (WORK, NodeStatus.SKIPPED, dict(artifact="a", reason="r"), "no artifact"),
    ],
)
def test_an_ill_shaped_node_result_is_rejected(kind, status, fields, why):
    with pytest.raises(ValidationError, match=why):
        NodeResult(step_id=StepId("a"), kind=kind, status=status, **fields)


@pytest.mark.parametrize("kind", [k for k in PlanStepKind if k not in (WORK, VERIFY)])
def test_only_kinds_v03_executes_may_have_a_result(kind):
    with pytest.raises(ValidationError, match="not a kind V0.3 executes"):
        NodeResult(step_id=StepId("a"), kind=kind, status=NodeStatus.SKIPPED, reason="r")


@pytest.mark.parametrize("field", ["artifact", "reason"])
def test_empty_strings_are_not_a_usable_artifact_or_a_stated_reason(field):
    with pytest.raises(ValidationError):
        NodeResult(step_id=StepId("a"), kind=WORK, status=NodeStatus.SUCCEEDED, **{field: ""})


def test_a_node_result_is_frozen_strict_and_closed():
    result = node("a", NodeStatus.SUCCEEDED)
    with pytest.raises(ValidationError):
        result.status = NodeStatus.FAILED
    with pytest.raises(ValidationError):
        NodeResult(step_id="a", kind="agent", status="succeeded", artifact="x")  # str, not the types
    with pytest.raises(ValidationError):
        node("a", NodeStatus.SUCCEEDED, score=0.9)  # no scalar score anywhere (D-121)


def test_a_node_result_carries_exactly_these_fields():
    assert list(NodeResult.model_fields) == ["step_id", "kind", "status", "artifact", "reason"]


def test_a_node_result_round_trips_through_json_and_is_deterministic():
    result = node("a", NodeStatus.FAILED, reason="boom")
    text = result.model_dump_json()
    assert text == node("a", NodeStatus.FAILED, reason="boom").model_dump_json()
    assert NodeResult.model_validate_json(text) == result


# --- HaltInfo -------------------------------------------------------------------------


def test_halt_info_needs_a_level_of_at_least_one_and_a_reason():
    assert HaltInfo(step_id=StepId("a"), level=2, reason="stop").level == 2
    with pytest.raises(ValidationError):
        HaltInfo(step_id=StepId("a"), level=0, reason="stop")
    with pytest.raises(ValidationError):
        HaltInfo(step_id=StepId("a"), level=1, reason="")


# --- RunResult: the three outcomes ----------------------------------------------------------


def test_a_finished_run():
    result = run([node("a", NodeStatus.SUCCEEDED), node("b", NodeStatus.SUCCEEDED)])
    assert result.outcome is RunOutcome.FINISHED and result.halt is None
    assert result.dispatched == ("a", "b")


def test_a_failed_run():
    result = run([node("a", NodeStatus.FAILED), node("b", NodeStatus.SKIPPED)])
    assert result.outcome is RunOutcome.FAILED


def test_a_halted_run():
    halt = HaltInfo(step_id=StepId("b"), level=2, reason="budget")
    result = run([node("a", NodeStatus.SUCCEEDED), node("b", NodeStatus.NOT_REACHED)], halt=halt)
    assert result.outcome is RunOutcome.HALTED and result.halt == halt


def test_halted_takes_precedence_over_failed():
    halt = HaltInfo(step_id=StepId("c"), level=2, reason="budget")
    results = [node("a", NodeStatus.FAILED), node("b", NodeStatus.SKIPPED), node("c", NodeStatus.NOT_REACHED)]
    assert run(results, halt=halt).outcome is RunOutcome.HALTED
    with pytest.raises(ValidationError, match="outcome must be 'halted'"):
        run(results, halt=halt, outcome=RunOutcome.FAILED)


def test_the_outcome_must_agree_with_the_results():
    finished = [node("a", NodeStatus.SUCCEEDED)]
    failed = [node("a", NodeStatus.FAILED)]
    with pytest.raises(ValidationError, match="outcome must be 'failed'"):
        run(failed, outcome=RunOutcome.FINISHED)
    with pytest.raises(ValidationError, match="outcome must be 'finished'"):
        run(finished, outcome=RunOutcome.FAILED)
    with pytest.raises(ValidationError, match="outcome must be 'finished'"):
        run(finished, outcome=RunOutcome.HALTED)  # halted needs a halt


def test_an_empty_run_finishes_vacuously_and_is_unverified():
    result = run([])
    assert result.outcome is RunOutcome.FINISHED
    assert result.results == () and result.dispatched == () and result.verified is False


# --- RunResult: internal consistency ----------------------------------------------------------


def test_duplicate_results_are_rejected():
    with pytest.raises(ValidationError, match="duplicate result"):
        run([node("a", NodeStatus.SUCCEEDED), node("a", NodeStatus.SUCCEEDED)])


def test_a_dispatched_step_must_have_a_result_and_appear_once():
    with pytest.raises(ValidationError, match="has no result"):
        run([node("a", NodeStatus.SUCCEEDED)], dispatched=("a", "ghost"))
    with pytest.raises(ValidationError, match="more than once"):
        run([node("a", NodeStatus.SUCCEEDED)], dispatched=("a", "a"))


@pytest.mark.parametrize("status", [NodeStatus.SKIPPED, NodeStatus.NOT_REACHED])
def test_an_undispatched_status_cannot_be_dispatched(status):
    halt = HaltInfo(step_id=StepId("a"), level=1, reason="r")
    with pytest.raises(ValidationError, match="was dispatched but is"):
        run([node("a", status)], dispatched=("a",), halt=halt if status is NodeStatus.NOT_REACHED else None)


@pytest.mark.parametrize("status", [NodeStatus.FAILED, NodeStatus.NO_RESULT])
def test_a_status_only_a_dispatch_can_produce_must_be_dispatched(status):
    with pytest.raises(ValidationError, match="was never dispatched"):
        run([node("a", status)], dispatched=())


def test_a_verification_status_must_be_dispatched():
    with pytest.raises(ValidationError, match="was never dispatched"):
        run([node("v", NodeStatus.VERIFICATION_FAILED, VERIFY)], dispatched=())


def test_a_succeeded_node_that_was_not_dispatched_is_a_carried_over_one():
    result = run([node("a", NodeStatus.SUCCEEDED), node("b", NodeStatus.SUCCEEDED)], dispatched=("b",))
    assert result.dispatched == ("b",) and result.settled == ("a", "b")


def test_not_reached_requires_a_halt_and_the_halt_must_name_a_not_reached_node():
    with pytest.raises(ValidationError, match="requires the run to have halted"):
        run([node("a", NodeStatus.NOT_REACHED)])
    halt = HaltInfo(step_id=StepId("a"), level=1, reason="r")
    with pytest.raises(ValidationError, match="must be not_reached"):
        run([node("a", NodeStatus.SUCCEEDED)], halt=halt)
    ghost = HaltInfo(step_id=StepId("ghost"), level=1, reason="r")
    with pytest.raises(ValidationError, match="must be not_reached"):
        run([node("a", NodeStatus.NOT_REACHED)], halt=ghost)


def test_a_run_result_carries_exactly_these_fields():
    assert list(RunResult.model_fields) == [
        "tenant_id", "mission_id", "execution_id", "plan_id", "plan_version",
        "outcome", "halt", "results", "dispatched",
    ]


# --- RunResult: verified versus unverified -------------------------------------------------------


def test_a_finished_run_with_a_succeeded_verify_node_is_verified():
    result = run([node("a", NodeStatus.SUCCEEDED), node("v", NodeStatus.SUCCEEDED, VERIFY)])
    assert result.outcome is RunOutcome.FINISHED and result.verified is True


def test_a_finished_run_with_no_verify_node_is_explicitly_unverified():
    result = run([node("a", NodeStatus.SUCCEEDED), node("b", NodeStatus.SUCCEEDED)])
    assert result.outcome is RunOutcome.FINISHED
    assert result.verified is False


def test_a_failed_run_is_never_verified_even_if_a_verify_node_succeeded():
    result = run([node("v", NodeStatus.SUCCEEDED, VERIFY), node("b", NodeStatus.FAILED)])
    assert result.outcome is RunOutcome.FAILED and result.verified is False


def test_a_halted_run_is_never_verified():
    halt = HaltInfo(step_id=StepId("b"), level=2, reason="r")
    result = run([node("v", NodeStatus.SUCCEEDED, VERIFY), node("b", NodeStatus.NOT_REACHED)], halt=halt)
    assert result.verified is False


@pytest.mark.parametrize("status", [NodeStatus.VERIFICATION_FAILED, NodeStatus.VERIFICATION_INCONCLUSIVE])
def test_a_run_with_a_verification_that_did_not_pass_is_not_verified(status):
    result = run([node("v", status, VERIFY)])
    assert result.outcome is RunOutcome.FAILED and result.verified is False


# --- RunResult: accessors -------------------------------------------------------------------------


def test_settled_is_everything_but_not_reached_in_plan_order():
    halt = HaltInfo(step_id=StepId("c"), level=2, reason="r")
    result = run(
        [node("a", NodeStatus.SUCCEEDED), node("b", NodeStatus.SKIPPED), node("c", NodeStatus.NOT_REACHED)],
        halt=halt,
    )
    assert result.settled == ("a", "b")


def test_result_for_finds_a_step_and_raises_key_error_for_an_unknown_one():
    result = run([node("a", NodeStatus.SUCCEEDED)])
    assert result.result_for(StepId("a")).status is NodeStatus.SUCCEEDED
    with pytest.raises(KeyError):
        result.result_for(StepId("ghost"))


def test_a_run_result_is_frozen_and_deterministic_in_json():
    result = run([node("a", NodeStatus.SUCCEEDED), node("v", NodeStatus.SUCCEEDED, VERIFY)])
    with pytest.raises(ValidationError):
        result.outcome = RunOutcome.FAILED
    same = run([node("a", NodeStatus.SUCCEEDED), node("v", NodeStatus.SUCCEEDED, VERIFY)])
    assert result == same and result.model_dump_json() == same.model_dump_json()
    assert RunResult.model_validate_json(result.model_dump_json()) == result


def test_results_keep_the_order_they_were_given_which_is_plan_order():
    result = run([node("z", NodeStatus.SUCCEEDED), node("a", NodeStatus.SUCCEEDED)])
    assert [r.step_id for r in result.results] == ["z", "a"]


# --- PriorOutcomes ----------------------------------------------------------------------------------


def prior_of(*outcomes, **overrides) -> PriorOutcomes:
    return PriorOutcomes(**{**IDS, "outcomes": tuple(outcomes), **overrides})


def test_prior_outcomes_hold_each_step_once():
    assert prior_of(node("a", NodeStatus.SUCCEEDED)).outcomes[0].step_id == "a"
    with pytest.raises(ValidationError, match="duplicate prior outcome"):
        prior_of(node("a", NodeStatus.SUCCEEDED), node("a", NodeStatus.SUCCEEDED))


def test_prior_outcomes_can_hold_any_status_so_the_executor_can_reject_it():
    # The type does not filter: rejecting invalid prior state is the run's job (D-120).
    assert prior_of(node("a", NodeStatus.FAILED)).outcomes[0].status is NodeStatus.FAILED


def test_succeeded_from_selects_only_succeeded_outcomes_in_plan_order_with_the_runs_identity():
    result = run(
        [node("a", NodeStatus.SUCCEEDED), node("b", NodeStatus.FAILED), node("c", NodeStatus.SKIPPED),
         node("d", NodeStatus.SUCCEEDED)]
    )
    prior = PriorOutcomes.succeeded_from(result)
    assert [o.step_id for o in prior.outcomes] == ["a", "d"]
    assert (prior.tenant_id, prior.mission_id, prior.execution_id, prior.plan_id, prior.plan_version) == (
        IDS["tenant_id"], IDS["mission_id"], IDS["execution_id"], IDS["plan_id"], IDS["plan_version"],
    )


def test_succeeded_from_a_halted_run_drops_the_not_reached_nodes():
    halt = HaltInfo(step_id=StepId("b"), level=2, reason="r")
    result = run([node("a", NodeStatus.SUCCEEDED), node("b", NodeStatus.NOT_REACHED)], halt=halt)
    assert [o.step_id for o in PriorOutcomes.succeeded_from(result).outcomes] == ["a"]


def test_prior_outcomes_are_frozen():
    prior = prior_of(node("a", NodeStatus.SUCCEEDED))
    with pytest.raises(ValidationError):
        prior.outcomes = ()


# --- RunRejection ------------------------------------------------------------------------------------


def test_the_rejection_codes_are_exactly_these_five():
    assert [c.value for c in RunRejectionCode] == [
        "wrong_tenant", "wrong_mission", "wrong_plan", "wrong_plan_version", "invalid_prior_state",
    ]


def test_only_a_prior_state_rejection_names_steps():
    assert RunRejection(
        code=RunRejectionCode.INVALID_PRIOR_STATE, message="m", step_ids=(StepId("a"),)
    ).step_ids == ("a",)
    for code in RunRejectionCode:
        if code is not RunRejectionCode.INVALID_PRIOR_STATE:
            with pytest.raises(ValidationError, match="about the context"):
                RunRejection(code=code, message="m", step_ids=(StepId("a"),))


def test_a_rejection_needs_a_message_and_is_frozen():
    with pytest.raises(ValidationError):
        RunRejection(code=RunRejectionCode.WRONG_PLAN, message="")
    rejection = RunRejection(code=RunRejectionCode.WRONG_PLAN, message="m")
    with pytest.raises(ValidationError):
        rejection.message = "changed"
