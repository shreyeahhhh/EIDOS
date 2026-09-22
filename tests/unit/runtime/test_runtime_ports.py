"""Execution ports and their typed results (decisions.md D-119, D-121, D-122)."""

import inspect

import pytest
from pydantic import ValidationError

from eidos.compiler import VerifyNode, WorkNode
from eidos.contracts import StepId
from eidos.runtime import (
    AdmissionDecision,
    AdmissionGuard,
    AdmissionOutcome,
    AdmissionRequest,
    VerificationResult,
    VerificationVerdict,
    Verifier,
    WorkExecutor,
    WorkResult,
    WorkStatus,
)


# --- WorkResult: what "usable" means ----------------------------------------------------------


def test_a_produced_result_is_usable_because_it_names_an_artifact():
    result = WorkResult.produced("artifact:1")
    assert result.status is WorkStatus.PRODUCED
    assert result.artifact == "artifact:1" and result.reason is None


def test_a_failed_result_carries_no_artifact_and_says_why():
    result = WorkResult.failed("timed out upstream")
    assert result.status is WorkStatus.FAILED
    assert result.artifact is None and result.reason == "timed out upstream"


def test_a_no_result_completed_without_a_usable_artifact_and_says_why():
    result = WorkResult.no_result("the search returned nothing")
    assert result.status is WorkStatus.NO_RESULT
    assert result.artifact is None and result.reason == "the search returned nothing"


def test_a_submitted_result_carries_no_artifact_and_a_generic_reason_d165():
    result = WorkResult.submitted("dispatched; outcome pending")
    assert result.status is WorkStatus.SUBMITTED
    assert result.artifact is None and result.reason == "dispatched; outcome pending"


def test_the_work_statuses_are_exactly_these_the_three_of_d118_plus_submitted_from_d165():
    assert [s.value for s in WorkStatus] == ["produced", "failed", "no_result", "submitted"]


@pytest.mark.parametrize(
    "fields",
    [
        dict(status=WorkStatus.PRODUCED),  # produced with nothing is not usable
        dict(status=WorkStatus.PRODUCED, artifact="a", reason="r"),
        dict(status=WorkStatus.FAILED),
        dict(status=WorkStatus.FAILED, artifact="a", reason="r"),
        dict(status=WorkStatus.NO_RESULT),
        dict(status=WorkStatus.NO_RESULT, artifact="a", reason="r"),
        dict(status=WorkStatus.SUBMITTED),  # D-165: must say why, same as failed/no_result
        dict(status=WorkStatus.SUBMITTED, artifact="a", reason="r"),
    ],
)
def test_an_ill_shaped_work_result_is_rejected(fields):
    with pytest.raises(ValidationError):
        WorkResult(**fields)


@pytest.mark.parametrize("field", ["artifact", "reason"])
def test_empty_strings_are_not_an_artifact_or_a_reason(field):
    base = dict(status=WorkStatus.PRODUCED, artifact="a") if field == "artifact" else dict(status=WorkStatus.FAILED)
    with pytest.raises(ValidationError):
        WorkResult(**{**base, field: ""})


def test_a_work_result_is_frozen_strict_and_closed_and_carries_no_score():
    result = WorkResult.produced("a")
    with pytest.raises(ValidationError):
        result.artifact = "b"
    with pytest.raises(ValidationError):
        WorkResult(status="produced", artifact="a")  # a str is not the enum
    with pytest.raises(ValidationError):
        WorkResult(status=WorkStatus.PRODUCED, artifact="a", confidence=0.9)
    assert list(WorkResult.model_fields) == ["status", "artifact", "reason"]


# --- VerificationResult: PASS / FAIL / INCONCLUSIVE, a reason, no scalar ----------------------------


def test_the_three_verdicts_are_exactly_these():
    assert [v.value for v in VerificationVerdict] == ["pass", "fail", "inconclusive"]


@pytest.mark.parametrize(
    "build, verdict",
    [
        (VerificationResult.passed, VerificationVerdict.PASS),
        (VerificationResult.failed, VerificationVerdict.FAIL),
        (VerificationResult.inconclusive, VerificationVerdict.INCONCLUSIVE),
    ],
)
def test_every_verdict_carries_its_reason(build, verdict):
    result = build("why")
    assert result.verdict is verdict and result.reason == "why"


@pytest.mark.parametrize("verdict", list(VerificationVerdict))
def test_a_verdict_without_a_reason_is_rejected(verdict):
    with pytest.raises(ValidationError):
        VerificationResult(verdict=verdict)
    with pytest.raises(ValidationError):
        VerificationResult(verdict=verdict, reason="")


def test_no_scalar_quality_or_confidence_score_exists_anywhere_in_a_verification_result():
    assert list(VerificationResult.model_fields) == ["verdict", "reason"]
    for score in ("score", "confidence", "quality", "probability"):
        with pytest.raises(ValidationError):
            VerificationResult(verdict=VerificationVerdict.PASS, reason="r", **{score: 0.9})


def test_a_verification_result_is_frozen_and_strict():
    result = VerificationResult.passed("r")
    with pytest.raises(ValidationError):
        result.reason = "changed"
    with pytest.raises(ValidationError):
        VerificationResult(verdict="pass", reason="r")


# --- admission ---------------------------------------------------------------------------------


def test_an_admission_request_carries_only_deterministic_execution_facts():
    assert list(AdmissionRequest.model_fields) == [
        "step_id", "level", "rank_in_level", "dispatched_before_level",
    ]
    request = AdmissionRequest(step_id=StepId("a"), level=2, rank_in_level=0, dispatched_before_level=3)
    assert (request.level, request.rank_in_level, request.dispatched_before_level) == (2, 0, 3)


@pytest.mark.parametrize(
    "field, bad", [("level", 0), ("rank_in_level", -1), ("dispatched_before_level", -1), ("level", "1"), ("level", True)]
)
def test_admission_request_numbers_are_strict_and_in_range(field, bad):
    fields = dict(step_id=StepId("a"), level=1, rank_in_level=0, dispatched_before_level=0)
    fields[field] = bad
    with pytest.raises(ValidationError):
        AdmissionRequest(**fields)


def test_admission_outcomes_are_exactly_admit_and_halt():
    assert [o.value for o in AdmissionOutcome] == ["admit", "halt"]


def test_admit_carries_no_reason_and_halt_must_state_one():
    assert AdmissionDecision.admit().outcome is AdmissionOutcome.ADMIT
    assert AdmissionDecision.admit().reason is None
    halt = AdmissionDecision.halt("budget exhausted")
    assert halt.outcome is AdmissionOutcome.HALT and halt.reason == "budget exhausted"
    with pytest.raises(ValidationError, match="must state why"):
        AdmissionDecision(outcome=AdmissionOutcome.HALT)
    with pytest.raises(ValidationError, match="carries no reason"):
        AdmissionDecision(outcome=AdmissionOutcome.ADMIT, reason="r")
    with pytest.raises(ValidationError):
        AdmissionDecision.halt("")


def test_admission_types_are_frozen():
    with pytest.raises(ValidationError):
        AdmissionDecision.admit().reason = "x"
    with pytest.raises(ValidationError):
        AdmissionRequest(step_id=StepId("a"), level=1, rank_in_level=0, dispatched_before_level=0).level = 2


# --- the ports themselves --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "port, method",
    [(WorkExecutor, "execute"), (Verifier, "verify"), (AdmissionGuard, "admit")],
)
def test_every_port_method_is_synchronous(port, method):
    # D-122: V0.3's execution ports are synchronous; async interfaces stay deferred.
    assert not inspect.iscoroutinefunction(getattr(port, method))


def test_the_ports_have_exactly_one_method_each():
    def public(port):
        return [n for n in vars(port) if not n.startswith("_")]

    assert public(WorkExecutor) == ["execute"]
    assert public(Verifier) == ["verify"]
    assert public(AdmissionGuard) == ["admit"]


def test_port_signatures_are_narrow_and_take_compiled_nodes_not_agents():
    assert list(inspect.signature(WorkExecutor.execute).parameters) == ["self", "context", "node"]
    assert list(inspect.signature(Verifier.verify).parameters) == ["self", "context", "node", "predecessors"]
    assert list(inspect.signature(AdmissionGuard.admit).parameters) == ["self", "request"]
    hints = inspect.get_annotations(WorkExecutor.execute, eval_str=True)
    assert hints["node"] is WorkNode and hints["return"] is WorkResult
    hints = inspect.get_annotations(Verifier.verify, eval_str=True)
    assert hints["node"] is VerifyNode and hints["return"] is VerificationResult


def test_a_plain_class_satisfies_a_port_structurally_with_no_base_class():
    class Work:
        def execute(self, context, node):
            return WorkResult.produced("a")

    class Guard:
        def admit(self, request):
            return AdmissionDecision.admit()

    work: WorkExecutor = Work()
    guard: AdmissionGuard = Guard()
    assert work.execute(None, None).status is WorkStatus.PRODUCED
    assert guard.admit(None).outcome is AdmissionOutcome.ADMIT
