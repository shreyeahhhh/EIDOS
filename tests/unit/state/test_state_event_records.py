"""The typed event payloads and ``EventRecord`` (decisions.md D-153, D-154, D-160, D-199; V0.5 Step 2, V1.1 Step 3).

A record is an unchanged V0.1 envelope plus one typed payload chosen by its type. These tests pin what that means: every type this package
emits forms a record and round-trips strictly; a payload for another type is refused; the four types this package does not emit —
``VERIFICATION_FAILED`` included — cannot form a record; identity must agree across the two halves; and a payload holds only facts, with no
stop reason. ``REPLAN_TRIGGERED`` (V1.1 Step 3, D-199) moved from the not-emitted set to the emitted one — see ``ReplanTriggeredPayload``.
"""

import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from eidos.agents import ModelFailureKind
from eidos.contracts import (
    AgentId,
    AgentTaskStatus,
    CapabilityId,
    MissionEvent,
    MissionEventType,
    PlanId,
    PlanStepKind,
    StepId,
)
from eidos.runtime import AwaitingInfo, HaltInfo, NodeResult, NodeStatus
from eidos.state import (
    PAYLOAD_TYPES,
    A2ATaskCompletedPayload,
    A2ATaskStartedPayload,
    EventRecord,
    MissionCompletedPayload,
    MissionFailedPayload,
    MissionFailureCause,
    MissionPausedPayload,
    ModelCallFacts,
    ModelCallOutcome,
    NodeSettledPayload,
    NodeStartedPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    PlanRejectedPayload,
    PlanRejectionStage,
    ReplanTriggeredPayload,
    VerificationFacts,
)

from eidos_mission_factories import make_mission, make_mission_plan
from eidos_state_factories import (
    a2a_task_id,
    at,
    baseline_state_and_plan,
    event_id,
    make_record,
    response_call,
    verified_baseline,
    verify_result,
    work_result,
)

EMITTED = (
    MissionEventType.MISSION_CREATED,
    MissionEventType.PLAN_GENERATED,
    MissionEventType.PLAN_REJECTED,
    MissionEventType.PLAN_COMPILED,
    MissionEventType.NODE_STARTED,
    MissionEventType.NODE_SETTLED,
    MissionEventType.A2A_TASK_STARTED,
    MissionEventType.A2A_TASK_COMPLETED,
    MissionEventType.MISSION_PAUSED,
    MissionEventType.MISSION_COMPLETED,
    MissionEventType.MISSION_FAILED,
    MissionEventType.REPLAN_TRIGGERED,
)
NOT_EMITTED = tuple(t for t in MissionEventType if t not in EMITTED)


def one_record_of_every_emitted_type() -> dict:
    log = verified_baseline()
    by_type = {}
    for record in log.records:
        by_type.setdefault(record.event.type, record)
    by_type[MissionEventType.PLAN_REJECTED] = make_record(
        PlanRejectedPayload(plan_id=log.plan.plan_id, stage=PlanRejectionStage.BINDING, reasons=()), state=log.state, sequence=4
    )
    by_type[MissionEventType.MISSION_PAUSED] = make_record(
        MissionPausedPayload(plan_id=log.plan.plan_id, halt=HaltInfo(step_id=StepId("analyse"), level=2, reason="held")), state=log.state, sequence=5
    )
    by_type[MissionEventType.MISSION_FAILED] = make_record(
        MissionFailedPayload(plan_id=log.plan.plan_id, cause=MissionFailureCause.NO_RESULT, reason="no text"), state=log.state, sequence=6
    )
    by_type[MissionEventType.A2A_TASK_STARTED] = make_record(
        A2ATaskStartedPayload(plan_id=log.plan.plan_id, step_id=StepId("gather"), agent_id=AgentId(UUID(int=501)), a2a_task_id=a2a_task_id(1)),
        state=log.state, sequence=7,
    )
    by_type[MissionEventType.A2A_TASK_COMPLETED] = make_record(
        A2ATaskCompletedPayload(
            plan_id=log.plan.plan_id, step_id=StepId("gather"), a2a_task_id=a2a_task_id(1),
            outcome=AgentTaskStatus.COMPLETED, artifact=None, reason="the remote task concluded",
        ),
        state=log.state, sequence=8,
    )
    by_type[MissionEventType.REPLAN_TRIGGERED] = make_record(
        ReplanTriggeredPayload(
            failed_plan_id=log.plan.plan_id, cause=MissionFailureCause.VERIFICATION_FAILED,
            reason="a rule was violated", next_plan_id=PlanId(UUID(int=900_002)),
        ),
        state=log.state, sequence=9,
    )
    return by_type


RECORDS = one_record_of_every_emitted_type()


# --- the vocabulary is exactly what V0.5 emits -----------------------------------------------------------------------------------


def test_payload_classes_exist_for_exactly_the_twelve_types_this_package_emits_and_each_names_its_own_type():
    assert set(PAYLOAD_TYPES) == set(EMITTED)
    for event_type, payload_class in PAYLOAD_TYPES.items():
        assert payload_class.model_fields["event_type"].default is event_type


def test_the_four_types_this_package_does_not_emit_are_exactly_these():
    # REPLAN_TRIGGERED moved from here to EMITTED at V1.1 Step 3 (D-199) — it is no longer merely declared.
    assert {t.value for t in NOT_EMITTED} == {
        "MCP_TOOL_CALLED", "RAG_SEARCH", "EVIDENCE_REJECTED", "VERIFICATION_FAILED",
    }


def test_the_payload_table_cannot_be_changed():
    with pytest.raises(TypeError):
        PAYLOAD_TYPES[MissionEventType.RAG_SEARCH] = MissionCompletedPayload  # type: ignore[index]


# --- every emitted type forms a record and round-trips strictly ------------------------------------------------------------------


@pytest.mark.parametrize("event_type", EMITTED, ids=lambda t: t.value)
def test_every_emitted_type_forms_a_record_that_round_trips_to_an_equal_record_and_identical_json(event_type):
    record = RECORDS[event_type]
    text = record.model_dump_json()
    parsed = EventRecord.model_validate_json(text)
    assert parsed == record
    assert parsed.model_dump_json() == text
    assert type(parsed.payload) is PAYLOAD_TYPES[event_type]


def test_a_record_is_exactly_an_envelope_and_a_payload_and_the_envelope_still_has_no_payload_field():
    assert set(EventRecord.model_fields) == {"event", "payload"}
    assert "payload" not in MissionEvent.model_fields  # D-067: the V0.1 envelope is unchanged


def test_records_are_frozen_and_reject_unknown_fields():
    record = RECORDS[MissionEventType.PLAN_COMPILED]
    with pytest.raises(ValidationError):
        record.payload = record.payload  # type: ignore[misc]
    document = json.loads(record.model_dump_json())
    document["extra"] = 1
    with pytest.raises(ValidationError):
        EventRecord.model_validate(document)
    document = json.loads(record.model_dump_json())
    document["payload"]["invented"] = 1
    with pytest.raises(ValidationError):
        EventRecord.model_validate(document)


# --- a payload for another type is refused ---------------------------------------------------------------------------------------

PAIRS = [(a, b) for a in EMITTED for b in EMITTED if a is not b]


@pytest.mark.parametrize("envelope_type, payload_type", PAIRS, ids=lambda t: t.value if hasattr(t, "value") else str(t))
def test_a_payload_for_a_different_type_than_the_envelope_is_refused(envelope_type, payload_type):
    donor = RECORDS[payload_type]
    envelope = RECORDS[envelope_type].event
    with pytest.raises(ValidationError, match="the payload is for"):
        EventRecord(event=envelope, payload=donor.payload)


@pytest.mark.parametrize("event_type", NOT_EMITTED, ids=lambda t: t.value)
def test_a_type_v05_does_not_emit_cannot_form_a_record(event_type):
    state, plan = baseline_state_and_plan()
    envelope = MissionEvent(
        event_id=event_id(1), tenant_id=state.tenant_id, mission_id=state.mission_id, sequence=1, occurred_at=at(1), recorded_at=at(1), type=event_type
    )
    with pytest.raises(ValidationError):  # every payload we have is for some other type
        EventRecord(event=envelope, payload=PlanGeneratedPayload(plan=plan))
    document = json.loads(RECORDS[MissionEventType.PLAN_COMPILED].model_dump_json())
    document["event"]["type"] = event_type.value
    document["payload"] = {"event_type": event_type.value}
    with pytest.raises(ValidationError):  # and there is no class a payload of this type could be
        EventRecord.model_validate(document)


def test_verification_failed_is_not_emitted_and_has_no_payload_class_d160_item_2():
    assert MissionEventType.VERIFICATION_FAILED not in PAYLOAD_TYPES
    assert MissionEventType.VERIFICATION_FAILED in MissionEventType  # retained for future use


# --- identity must agree across the two halves -----------------------------------------------------------------------------------


def test_a_created_payload_whose_genome_or_contract_belongs_to_another_tenant_is_refused():
    other = make_mission(seed=2)
    created = RECORDS[MissionEventType.MISSION_CREATED]
    for payload in (
        created.payload.model_copy(update={"task_genome": other.task_genome}),
        created.payload.model_copy(update={"reliability_contract": other.reliability_contract}),
    ):
        with pytest.raises(ValidationError, match="tenant"):
            EventRecord(event=created.event, payload=type(created.payload).model_validate(payload.model_dump()))


def test_a_plan_of_another_mission_or_tenant_is_refused():
    state, _ = baseline_state_and_plan()
    other = make_mission(seed=2)
    generated = RECORDS[MissionEventType.PLAN_GENERATED]
    for foreign in (
        make_mission_plan(other, {"a": ""}),  # another tenant and mission
        make_mission_plan(state, {"a": ""}).model_copy(update={"mission_id": other.mission_id}),  # the right tenant, another mission
        make_mission_plan(state, {"a": ""}).model_copy(update={"tenant_id": other.tenant_id}),  # the right mission, another tenant
    ):
        with pytest.raises(ValidationError):
            EventRecord(event=generated.event, payload=PlanGeneratedPayload.model_validate({"plan": foreign.model_dump()}))


# --- what a payload may hold -----------------------------------------------------------------------------------------------------


def started(**kw):
    fields = dict(plan_id=PlanId(UUID(int=1)), step_id=StepId("gather"), kind=PlanStepKind.AGENT,
                  capability=CapabilityId("research"), agent_id=AgentId(UUID(int=501)))
    fields.update(kw)
    return NodeStartedPayload(**fields)


def test_a_started_work_node_names_its_capability_and_agent_and_a_verify_node_names_neither():
    started()
    started(kind=PlanStepKind.VERIFY, capability=None, agent_id=None)
    for bad in (dict(agent_id=None), dict(capability=None), dict(kind=PlanStepKind.VERIFY)):
        with pytest.raises(ValidationError):
            started(**bad)
    with pytest.raises(ValidationError, match="only agent and VERIFY"):
        started(kind=PlanStepKind.ROUTE, capability=None, agent_id=None)


def settled(result, **kw):
    fields = dict(plan_id=PlanId(UUID(int=1)), result=result, dispatched=True)
    fields.update(kw)
    return NodeSettledPayload(**fields)


def test_a_node_that_was_not_dispatched_has_no_observations_and_a_skipped_node_was_never_dispatched():
    skipped = NodeResult(step_id=StepId("analyse"), kind=PlanStepKind.AGENT, status=NodeStatus.SKIPPED, reason="not dispatched: predecessor(s) did not succeed")
    settled(skipped, dispatched=False)
    for bad in (dict(duration_ms=1), dict(model_calls=(response_call(),))):
        with pytest.raises(ValidationError, match="no observations"):
            settled(skipped, dispatched=False, **bad)
    with pytest.raises(ValidationError, match="was not dispatched"):
        settled(skipped, dispatched=True)
    settled(work_result("gather"), dispatched=False)  # carried over from prior outcomes (D-120): succeeded, not dispatched


def test_only_a_work_node_has_model_calls_and_only_a_verify_node_has_a_verdict():
    from eidos.runtime import VerificationVerdict

    with pytest.raises(ValidationError, match="only a work node"):
        settled(verify_result("check"), model_calls=(response_call(),))
    with pytest.raises(ValidationError, match="only a VERIFY node"):
        settled(work_result("gather"), verification=VerificationFacts(verdict=VerificationVerdict.PASS, reason="ok"))
    settled(verify_result("check"), verification=VerificationFacts(verdict=VerificationVerdict.PASS, reason="ok"))


def test_a_failed_model_call_carries_no_provider_facts_and_a_response_may_lack_any_it_was_not_given():
    for outcome in ModelCallOutcome:
        if outcome is ModelCallOutcome.RESPONSE:
            continue
        ModelCallFacts(outcome=outcome)
        for extra in (dict(prompt_tokens=1), dict(output_tokens=1), dict(elapsed_seconds=0.5)):
            with pytest.raises(ValidationError, match="no provider facts"):
                ModelCallFacts(outcome=outcome, **extra)
    ModelCallFacts(outcome=ModelCallOutcome.RESPONSE)  # a provider that reported nothing: every fact stays None, never a guess
    for bad in (dict(prompt_tokens=-1), dict(output_tokens=-1), dict(elapsed_seconds=-0.1)):
        with pytest.raises(ValidationError):
            ModelCallFacts(outcome=ModelCallOutcome.RESPONSE, **bad)


def test_a_model_call_records_only_what_measured_facts_carries_and_no_stop_reason_d151_d158():
    assert set(ModelCallFacts.model_fields) == {"outcome", "prompt_tokens", "output_tokens", "elapsed_seconds"}
    assert not any("stop" in name or "reason" in name or "done" in name for name in ModelCallFacts.model_fields)


def test_the_recorded_model_call_outcomes_are_the_agents_failure_kinds_plus_response():
    assert {o.value for o in ModelCallOutcome} == {"response"} | {k.value for k in ModelFailureKind}


def test_a_payload_holds_no_quality_confidence_score_or_rate_d159():
    forbidden = ("quality", "confidence", "score", "rate", "signature")
    for payload_class in PAYLOAD_TYPES.values():
        for name in payload_class.model_fields:
            assert not any(word in name for word in forbidden), (payload_class.__name__, name)


def test_a_paused_payload_carries_the_runs_own_halt_and_a_failure_names_a_typed_cause_and_a_reason():
    with pytest.raises(ValidationError):
        MissionFailedPayload(cause=MissionFailureCause.NO_RESULT, reason="")
    with pytest.raises(ValidationError):
        MissionFailedPayload(cause="a made-up cause", reason="x")  # type: ignore[arg-type]
    MissionFailedPayload(cause=MissionFailureCause.PLAN_REJECTED, reason="the plan was refused")  # no plan accepted: plan_id absent
    with pytest.raises(ValidationError):
        MissionCompletedPayload(plan_id=PlanId(UUID(int=1)), verified="yes")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        PlanCompiledPayload(plan_id=PlanId(UUID(int=1)), plan_version=0)


# --- V0.6 Step 4: A2A_TASK_STARTED / A2A_TASK_COMPLETED and the paused payload's two causes (D-166, D-169, D-174) --------------------------------


def test_a_mission_pauses_for_exactly_one_cause_never_both_and_never_neither():
    halt = HaltInfo(step_id=StepId("analyse"), level=2, reason="held")
    with pytest.raises(ValidationError, match="exactly one reason"):
        MissionPausedPayload(plan_id=PlanId(UUID(int=1)))  # neither
    with pytest.raises(ValidationError, match="exactly one reason"):
        MissionPausedPayload(
            plan_id=PlanId(UUID(int=1)), halt=halt, awaiting=(AwaitingInfo(step_id=StepId("gather"), level=1, reason="awaiting"),)
        )  # both
    MissionPausedPayload(plan_id=PlanId(UUID(int=1)), halt=halt)  # halt alone: fine
    MissionPausedPayload(
        plan_id=PlanId(UUID(int=1)), awaiting=(AwaitingInfo(step_id=StepId("gather"), level=1, reason="awaiting"),)
    )  # awaiting alone: fine


def test_an_a2a_task_started_payload_names_its_agent_and_remote_task_and_the_context_is_optional():
    started = A2ATaskStartedPayload(
        plan_id=PlanId(UUID(int=1)), step_id=StepId("gather"), agent_id=AgentId(UUID(int=501)), a2a_task_id=a2a_task_id(1)
    )
    assert started.a2a_context_id is None
    with_context = A2ATaskStartedPayload(
        plan_id=PlanId(UUID(int=1)), step_id=StepId("gather"), agent_id=AgentId(UUID(int=501)),
        a2a_task_id=a2a_task_id(1), a2a_context_id="remote-context-1",  # type: ignore[arg-type]
    )
    assert with_context.a2a_context_id == "remote-context-1"


def test_an_a2a_task_completed_payloads_outcome_must_conclude_the_task_and_only_completed_carries_an_artifact():
    for non_concluding in (AgentTaskStatus.SUBMITTED, AgentTaskStatus.WORKING, AgentTaskStatus.UNSPECIFIED):
        with pytest.raises(ValidationError, match="never concludes a task"):
            A2ATaskCompletedPayload(
                plan_id=PlanId(UUID(int=1)), step_id=StepId("gather"), a2a_task_id=a2a_task_id(1), outcome=non_concluding, reason="x"
            )
    for concluding in (
        AgentTaskStatus.COMPLETED, AgentTaskStatus.FAILED, AgentTaskStatus.CANCELED, AgentTaskStatus.REJECTED,
        AgentTaskStatus.INPUT_REQUIRED, AgentTaskStatus.AUTH_REQUIRED, AgentTaskStatus.TIMED_OUT,
    ):
        A2ATaskCompletedPayload(
            plan_id=PlanId(UUID(int=1)), step_id=StepId("gather"), a2a_task_id=a2a_task_id(1), outcome=concluding, reason="x"
        )
    A2ATaskCompletedPayload(
        plan_id=PlanId(UUID(int=1)), step_id=StepId("gather"), a2a_task_id=a2a_task_id(1),
        outcome=AgentTaskStatus.COMPLETED, artifact="artifact:gather", reason="x",  # type: ignore[arg-type]
    )
    with pytest.raises(ValidationError, match="carries no artifact"):
        A2ATaskCompletedPayload(
            plan_id=PlanId(UUID(int=1)), step_id=StepId("gather"), a2a_task_id=a2a_task_id(1),
            outcome=AgentTaskStatus.FAILED, artifact="artifact:gather", reason="x",  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        A2ATaskCompletedPayload(plan_id=PlanId(UUID(int=1)), step_id=StepId("gather"), a2a_task_id=a2a_task_id(1), outcome=AgentTaskStatus.FAILED, reason="")
