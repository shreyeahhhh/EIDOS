"""Scenarios: verification fails, and the mission is replanned (V0.3).

Invariant 12: "an agent returned output" is never success. Verification is separate from completion, and a
verification that fails or cannot conclude makes the run FAILED — however much work succeeded.

Invariant 6 and D-119: a replan is a caller-supplied *new* plan (version N+1, with lineage and a reason),
separately validated, compiled and executed. The runtime never patches a plan and never replans by itself,
and nothing from an earlier plan's run is carried into the new one (D-120: prior outcomes belong to one plan).

Work, verification and admission are scripted test doubles; no scenario here says anything about an agent's
quality. V0.3 keeps no events, so the ``RunResult`` is the record asserted on.
"""

import pytest
from pydantic import ValidationError

from eidos.compiler import CompileFailureCode
from eidos.contracts import StepId
from eidos.runtime import (
    NodeStatus,
    PriorOutcomes,
    RunOutcome,
    RunRejection,
    RunRejectionCode,
    VerificationResult,
    WorkResult,
)

from eidos_factories import make_mission_state
from eidos_scenario_factories import drive, make_mission, make_mission_plan

CAPABILITY_OF = {"analyse": "analysis", "publish": "analysis"}
# gather -> analyse -> check (verify) -> publish: publishing is only allowed once the analysis is verified.
SPEC_V1 = {"gather": "", "analyse": "gather", "check": "analyse", "publish": "check"}
FINDING = "the analysis contradicts its own sources"


def v1_plan(state):
    return make_mission_plan(state, SPEC_V1, verify=("check",), capability_of=CAPABILITY_OF)


def failing_check(verdict=VerificationResult.failed):
    return lambda: {"check": verdict(FINDING)}


# --- verification is separate from completion (invariant 12) --------------------------------------------------------


def test_a_failed_verification_fails_the_run_however_much_work_succeeded():
    state = make_mission()
    attempt = drive(state, v1_plan(state), verifier=failing_check())
    result = attempt.result

    assert result.outcome is RunOutcome.FAILED
    assert result.verified is False
    assert [(r.step_id, r.status) for r in result.results] == [
        ("gather", NodeStatus.SUCCEEDED),
        ("analyse", NodeStatus.SUCCEEDED),
        ("check", NodeStatus.VERIFICATION_FAILED),
        ("publish", NodeStatus.SKIPPED),
    ]
    assert result.result_for(StepId("check")).reason == FINDING
    # What was gated behind verification never ran, and was never even asked about.
    assert result.dispatched == ("gather", "analyse", "check")
    assert attempt.work.calls == ["gather", "analyse"]
    assert sorted(step for step, *_ in attempt.guard.asked()) == ["analyse", "check", "gather"]


def test_an_inconclusive_verification_is_not_a_pass():
    state = make_mission()
    attempt = drive(state, v1_plan(state), verifier=failing_check(VerificationResult.inconclusive))
    result = attempt.result

    assert result.outcome is RunOutcome.FAILED
    assert result.verified is False
    assert result.result_for(StepId("check")).status is NodeStatus.VERIFICATION_INCONCLUSIVE
    assert result.result_for(StepId("publish")).status is NodeStatus.SKIPPED
    assert attempt.work.calls == ["gather", "analyse"]


def test_a_verifier_that_crashes_is_a_failed_node_and_never_a_verdict():
    state = make_mission()
    attempt = drive(state, v1_plan(state), verifier=lambda: {"check": RuntimeError("verifier down")})
    result = attempt.result

    check = result.result_for(StepId("check"))
    assert check.status is NodeStatus.FAILED
    assert "verifier down" in check.reason
    assert result.outcome is RunOutcome.FAILED and result.verified is False
    assert result.result_for(StepId("publish")).status is NodeStatus.SKIPPED


def test_work_that_returns_no_usable_result_stops_everything_behind_it():
    state = make_mission()
    attempt = drive(
        state,
        v1_plan(state),
        work=lambda: {"analyse": WorkResult.no_result("the source was unreachable")},
    )
    result = attempt.result

    assert result.result_for(StepId("analyse")).status is NodeStatus.NO_RESULT
    assert result.result_for(StepId("analyse")).reason == "the source was unreachable"
    assert result.result_for(StepId("check")).status is NodeStatus.SKIPPED  # nothing to verify
    assert result.result_for(StepId("publish")).status is NodeStatus.SKIPPED
    assert result.outcome is RunOutcome.FAILED
    assert attempt.verifier.calls == []  # the verifier was never asked to verify nothing


def test_a_crashing_agent_is_contained_and_independent_branches_still_run():
    state = make_mission()
    spec = {
        "gather_a": "", "gather_b": "",
        "analyse_a": "gather_a", "analyse_b": "gather_b",
        "check": "analyse_a analyse_b",
    }
    plan = make_mission_plan(state, spec, verify=("check",))

    attempt = drive(state, plan, work=lambda: {"gather_b": RuntimeError("agent crashed")})
    result = attempt.result  # nothing was raised out of the run

    assert [(r.step_id, r.status) for r in result.results] == [
        ("gather_a", NodeStatus.SUCCEEDED),
        ("gather_b", NodeStatus.FAILED),
        ("analyse_a", NodeStatus.SUCCEEDED),  # the healthy branch carried on
        ("analyse_b", NodeStatus.SKIPPED),
        ("check", NodeStatus.SKIPPED),  # a join is never verified over a broken branch
    ]
    assert "agent crashed" in result.result_for(StepId("gather_b")).reason
    assert result.outcome is RunOutcome.FAILED
    # Every step is accounted for: nothing was dropped to make the run look shorter.
    assert len(result.results) == len(plan.steps)
    assert attempt.verifier.calls == []


# --- replanning: a new plan version, not a patched one (invariant 6, D-119) ------------------------------------------


def replanned(state, v1):
    """Version 2 of the mission's plan: more evidence is gathered before the analysis, as verification asked."""
    spec_v2 = {"gather": "", "gather_more": "", "analyse": "gather gather_more", "check": "analyse", "publish": "check"}
    return make_mission_plan(
        state,
        spec_v2,
        verify=("check",),
        capability_of=CAPABILITY_OF,
        version=2,
        parent=v1,
        reason=f"verification failed at 'check': {FINDING}",
    )


def test_verification_fails_the_mission_is_replanned_and_the_new_plan_verifies():
    state = make_mission()
    v1 = v1_plan(state)
    failed = drive(state, v1, verifier=failing_check())
    assert failed.result.outcome is RunOutcome.FAILED

    v2 = replanned(state, v1)
    second = drive(state, v2)  # the default verifier passes: the extra evidence settled the question

    # The replan is a new plan with recorded lineage and a recorded reason (§15, §43).
    assert v2.plan_id != v1.plan_id
    assert (v2.version, v2.parent_plan_id) == (v1.version + 1, v1.plan_id)
    assert v2.replan_reason == f"verification failed at 'check': {FINDING}"

    # It was validated on its own evidence, compiled on its own, and run as its own plan version.
    assert second.report.plan_id == v2.plan_id and second.report.accepted
    result = second.result
    assert (result.plan_id, result.plan_version) == (v2.plan_id, 2)
    assert result.execution_id == failed.result.execution_id  # same mission, same execution (D-085)
    assert result.outcome is RunOutcome.FINISHED
    assert result.verified is True
    assert result.dispatched == ("gather", "gather_more", "analyse", "check", "publish")
    # Nothing was carried over from version 1: the earlier `gather` ran again, inside plan v2.
    assert sorted(second.work.calls) == ["analyse", "gather", "gather_more", "publish"]


def test_the_failed_plan_and_its_run_are_untouched_by_the_replan():
    state = make_mission()
    v1 = v1_plan(state)
    failed = drive(state, v1, verifier=failing_check())
    plan_before, run_before = v1.model_dump_json(), failed.result.model_dump_json()

    drive(state, replanned(state, v1))

    assert v1.model_dump_json() == plan_before
    assert failed.result.model_dump_json() == run_before
    assert failed.result.plan_version == 1  # the record of what happened stays what happened
    with pytest.raises(ValidationError):  # a plan is immutable: a live plan is never edited in place
        v1.version = 2


def test_the_two_plan_versions_form_a_valid_lineage_in_the_mission_state():
    # V0.3 records nothing in MissionState (D-123); this is the shape a later reducer would record.
    state = make_mission()
    v1 = v1_plan(state)
    v2 = replanned(state, v1)

    recorded = make_mission_state(
        tenant_id=state.tenant_id,
        mission_id=state.mission_id,
        execution_id=state.execution_id,
        task_genome=state.task_genome,
        reliability_contract=state.reliability_contract,
        plans=(v1, v2),
        active_plan_id=v2.plan_id,
    )

    assert [plan.version for plan in recorded.plans] == [1, 2]
    assert recorded.plans[1].parent_plan_id == recorded.plans[0].plan_id


def test_a_replanned_plan_cannot_ride_on_the_earlier_plans_validation():
    state = make_mission()
    v1 = v1_plan(state)
    v1_report = drive(state, v1).report
    v2 = replanned(state, v1)

    attempt = drive(state, v2, report=v1_report)

    assert not attempt.ran and attempt.compiled is None
    assert [v.code for v in attempt.compile_report.violations] == [CompileFailureCode.VALIDATION_PLAN_MISMATCH]
    assert attempt.work.calls == [] and attempt.verifier.calls == []


def test_a_context_for_the_old_plan_cannot_run_the_new_one():
    state = make_mission()
    v1 = v1_plan(state)
    old = drive(state, v1)

    attempt = drive(state, replanned(state, v1), context=old.context)

    assert isinstance(attempt.result, RunRejection)
    assert attempt.result.code is RunRejectionCode.WRONG_PLAN
    assert attempt.work.calls == [] and attempt.verifier.calls == [] and attempt.guard.requests == []


def test_outcomes_of_the_old_plan_are_rejected_not_adapted_for_the_new_one():
    state = make_mission()
    v1 = v1_plan(state)
    failed = drive(state, v1, verifier=failing_check())
    carried = PriorOutcomes.succeeded_from(failed.result)
    assert [o.step_id for o in carried.outcomes] == ["gather", "analyse"]  # they did succeed, in plan v1

    attempt = drive(state, replanned(state, v1), prior=carried)

    assert isinstance(attempt.result, RunRejection)
    assert attempt.result.code is RunRejectionCode.INVALID_PRIOR_STATE
    assert "plan_id" in attempt.result.message
    assert attempt.work.calls == []  # nothing ran, so nothing was quietly half-honoured
