"""``eidos.replanning``'s own pure helper functions (decisions.md D-199; V1.1 Step 4).

White-box, hand-built payloads — no real execution. Directly pins the eligibility table exactly as approved,
including the two causes (``PLAN_REJECTED``/``RUN_REJECTED``) the full orchestrator can never actually produce
through its own normal path (``expand_strategy``'s own output always passes `validate_plan`, D-183; ``record_
attempt`` never supplies a mismatched context or a `prior`) — tested here directly rather than left uncovered,
mirroring V1.0 Step 6's own honest treatment of a similarly unreachable case.
"""

import pytest
from pydantic import ValidationError

from eidos.contracts import MissionStatus, StepId
from eidos.planning import SelectionOutcome
from eidos.replanning import (
    ReplanRejection,
    ReplanRejectionCode,
    _effective_max_replans,
    _is_replan_eligible,
    _outcome_fields,
    _replan_cause_and_reason,
)
from eidos.runtime import AwaitingInfo, HaltInfo, RunOutcome
from eidos.state import MissionCompletedPayload, MissionFailedPayload, MissionFailureCause, MissionPausedPayload

from eidos_expansion_factories import make_plan_id
from eidos_mission_factories import make_mission


def failed(cause: MissionFailureCause, reason: str = "x") -> MissionFailedPayload:
    return MissionFailedPayload(plan_id=make_plan_id(1), cause=cause, reason=reason)


def completed(verified: bool) -> MissionCompletedPayload:
    return MissionCompletedPayload(plan_id=make_plan_id(1), verified=verified)


def halted() -> MissionPausedPayload:
    return MissionPausedPayload(plan_id=make_plan_id(1), halt=HaltInfo(step_id=StepId("gather"), level=1, reason="held"))


def awaiting() -> MissionPausedPayload:
    return MissionPausedPayload(plan_id=make_plan_id(1), awaiting=(AwaitingInfo(step_id=StepId("gather"), level=1, reason="awaiting"),))


# --- eligibility (D-199 ruling 1) — exactly the approved table, nothing more, nothing less -------------------


@pytest.mark.parametrize("cause", [
    MissionFailureCause.EXECUTION_FAILED, MissionFailureCause.NO_RESULT,
    MissionFailureCause.VERIFICATION_FAILED, MissionFailureCause.VERIFICATION_INCONCLUSIVE,
])
def test_the_four_eligible_failure_causes_are_replan_eligible(cause):
    assert _is_replan_eligible(failed(cause)) is True


def test_finished_unverified_is_replan_eligible():
    assert _is_replan_eligible(completed(verified=False)) is True


def test_a_verified_completion_is_never_replan_eligible():
    assert _is_replan_eligible(completed(verified=True)) is False


@pytest.mark.parametrize("cause", [MissionFailureCause.PLAN_REJECTED, MissionFailureCause.RUN_REJECTED])
def test_plan_rejected_and_run_rejected_are_never_replan_eligible(cause):
    # Structurally unreachable through the real orchestrator (expand_strategy's own output always validates,
    # D-183; record_attempt never supplies a mismatched context or a `prior`) — tested here directly, honestly,
    # rather than left silently uncovered by the integration suite that cannot reach it either.
    assert _is_replan_eligible(failed(cause)) is False


def test_an_admission_guard_halt_is_never_replan_eligible():
    assert _is_replan_eligible(halted()) is False


def test_an_awaiting_remote_pause_is_never_replan_eligible():
    assert _is_replan_eligible(awaiting()) is False


# --- _outcome_fields: the four TelemetryRecord fields a real terminal payload would have produced -------------


def test_outcome_fields_for_a_verified_completion():
    fields = _outcome_fields(completed(verified=True))
    assert fields == {"mission_status": MissionStatus.COMPLETED, "run_outcome": RunOutcome.FINISHED, "verified": True, "failure_cause": None}


def test_outcome_fields_for_an_unverified_completion():
    fields = _outcome_fields(completed(verified=False))
    assert fields == {"mission_status": MissionStatus.COMPLETED, "run_outcome": RunOutcome.FINISHED, "verified": False, "failure_cause": None}


def test_outcome_fields_for_a_halt():
    fields = _outcome_fields(halted())
    assert fields == {"mission_status": MissionStatus.PAUSED, "run_outcome": RunOutcome.HALTED, "verified": None, "failure_cause": None}


def test_outcome_fields_for_an_awaiting_pause():
    fields = _outcome_fields(awaiting())
    assert fields == {"mission_status": MissionStatus.PAUSED, "run_outcome": RunOutcome.AWAITING, "verified": None, "failure_cause": None}


def test_outcome_fields_for_an_eligible_failure():
    fields = _outcome_fields(failed(MissionFailureCause.VERIFICATION_FAILED, "insufficient evidence"))
    assert fields == {
        "mission_status": MissionStatus.FAILED, "run_outcome": RunOutcome.FAILED, "verified": None,
        "failure_cause": MissionFailureCause.VERIFICATION_FAILED,
    }


@pytest.mark.parametrize("cause", [MissionFailureCause.PLAN_REJECTED, MissionFailureCause.RUN_REJECTED])
def test_outcome_fields_for_a_never_ran_failure_has_no_run_outcome(cause):
    fields = _outcome_fields(failed(cause, "never ran"))
    assert fields == {"mission_status": MissionStatus.FAILED, "run_outcome": None, "verified": None, "failure_cause": cause}


# --- _replan_cause_and_reason: one pair, used both for ReplanTriggeredPayload and the next plan's own reason --


def test_replan_cause_and_reason_for_a_failure_is_the_failures_own_cause_and_reason():
    payload = failed(MissionFailureCause.EXECUTION_FAILED, "the agent call failed")
    assert _replan_cause_and_reason(payload) == (MissionFailureCause.EXECUTION_FAILED, "the agent call failed")


def test_replan_cause_and_reason_for_an_unverified_completion_reuses_verification_inconclusive():
    # The one genuine gap in the existing six-member taxonomy: nothing means "finished, but nothing verified
    # it." Reuses the closest existing member rather than inventing a seventh, per the owner's own instruction.
    cause, reason = _replan_cause_and_reason(completed(verified=False))
    assert cause is MissionFailureCause.VERIFICATION_INCONCLUSIVE  # accepted as D-201 item 1: no seventh cause, cause never optional
    assert reason == "finished without a successful VERIFY (verified is false)"


# --- _effective_max_replans: D-065's own precedent, applied to max_replans, no new precedence rule ------------


def test_effective_max_replans_is_the_system_ceiling_when_the_contract_sets_none():
    state = make_mission(capabilities=("research",))
    assert state.reliability_contract.max_replans is None
    limits = _limits(max_replans=5)
    assert _effective_max_replans(state, limits) == 5


def test_effective_max_replans_is_the_lesser_of_contract_and_ceiling():
    state = make_mission(capabilities=("research",), max_replans=2)
    limits = _limits(max_replans=5)
    assert _effective_max_replans(state, limits) == 2


def test_effective_max_replans_never_exceeds_the_system_ceiling_even_if_asked():
    # check_resources (V0.2) already refuses a contract exceeding the ceiling before this is ever reached in
    # practice (D-065) — this pins the formula's own behavior directly, independent of that upstream guarantee.
    state = make_mission(capabilities=("research",), max_replans=99)
    limits = _limits(max_replans=3)
    assert _effective_max_replans(state, limits) == 3


def _limits(**overrides):
    from eidos_validation_factories import make_system_limits
    return make_system_limits(**overrides)


# --- D-201: a mission refused before anything ran is a typed rejection, with no new failure vocabulary -------------


_REFUSALS = [outcome for outcome in SelectionOutcome if outcome is not SelectionOutcome.SELECTED]


@pytest.mark.parametrize("outcome", _REFUSALS)
def test_every_refused_selection_outcome_can_be_carried_and_round_trips(outcome):
    rejection = ReplanRejection(code=ReplanRejectionCode.NO_SELECTABLE_STRATEGY, outcome=outcome, reason="nothing was selected")
    assert ReplanRejection.model_validate_json(rejection.model_dump_json()) == rejection


def test_a_rejection_can_never_claim_the_selection_succeeded():
    with pytest.raises(ValidationError):
        ReplanRejection(code=ReplanRejectionCode.NO_SELECTABLE_STRATEGY, outcome=SelectionOutcome.SELECTED, reason="x")


def test_a_rejection_must_state_its_reason():
    with pytest.raises(ValidationError):
        ReplanRejection(code=ReplanRejectionCode.NO_SELECTABLE_STRATEGY, outcome=SelectionOutcome.SELECTOR_FAILED, reason="")


def test_the_rejection_adds_no_failure_vocabulary():
    # D-201: no seventh MissionFailureCause, no optional cause, no new failure taxonomy — the rejection carries the
    # existing selection vocabulary and one code, and nothing that reads as the cause of a failed mission.
    from eidos.state import MissionFailureCause

    assert len(MissionFailureCause) == 6
    assert set(ReplanRejection.model_fields) == {"code", "outcome", "reason"}
    assert [code.value for code in ReplanRejectionCode] == ["no_selectable_strategy"]
