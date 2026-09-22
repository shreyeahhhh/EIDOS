"""The full Research-Agent-via-A2A boundary, end to end (decisions.md D-165–D-176, V0.6 Steps 2–5; item 12's own
"full Research Agent remote boundary scenario" and "replay equivalence").

The events here are built directly through ``EventLog``/``EventProposal`` rather than ``record_baseline``
(``eidos.recording``): ``eidos.recording.run._finish()`` does not yet have the ``RunOutcome.AWAITING`` branch D-167
itself names as still-needed work (a later, separate step — recording is out of Step 5's scope, which is
``eidos.a2a`` only). This is exactly the sequence a caller drives by hand today, and what a future recording
wrapper would automate — proved here directly against the real runtime, the real reducer and the real A2A boundary,
with only the transport faked.

**A genuine gap found while writing this test, reported rather than silently patched (Step 5's own instruction):**
the *runtime*-level resume works completely — a second ``run_baseline`` pass, given ``PriorOutcomes`` for the
now-known ``gather`` result, correctly finishes the mission (proved below). But the *event-recording* side cannot
actually follow it on the same log: once the D-176 exception accepts the one ``A2A_TASK_COMPLETED`` a ``paused``
mission is allowed, ``MissionState.status`` stays ``paused`` — nothing in the currently Accepted design ever moves
it back to a status where an ordinary event (``NODE_STARTED`` for ``analyse``, eventually ``MISSION_COMPLETED``) is
accepted again. D-167 explicitly describes the opposite: calling ``record_baseline`` again on the same log
"naturally produces the post-hoc ``NODE_SETTLED`` and ... the mission's real terminal event — entirely through
machinery that already exists." That machinery does not, today, exist: the reducer's terminal check (`_TERMINAL`
in ``reducer.py``, D-176's own `_resumable_completion`) exempts only the one ``A2A_TASK_COMPLETED`` and nothing
after it. This is `eidos.state` territory — Step 4's already-committed reducer, or a follow-up decision — never
`eidos.a2a`'s to silently fix, so it is proved and pinned here (not patched) and reported in the Step 5 report.
"""

from uuid import UUID

from eidos.a2a import A2AClient, A2AWorkAgent, WebhookOutcome, notification_to_proposal
from eidos.agents import AnalysisAgent, InMemoryArtifactStore, ModelResponse, VerificationAgent
from eidos.baseline import run_baseline
from eidos.contracts import CapabilityId, EventId, PlanStepKind, StepId
from eidos.recording import ModelCallTracker, RecordingModel
from eidos.runtime import (
    NodeResult,
    NodeStatus,
    PriorOutcomes,
    RunOutcome,
    SequentialExecutor,
)
from eidos.state import (
    A2ATaskStartedPayload,
    EventLog,
    EventProposal,
    MissionCreatedPayload,
    MissionPausedPayload,
    NodeStartedPayload,
    PlanCompiledPayload,
    PlanGeneratedPayload,
    checkpoint_at,
    node_status_for,
    records_after,
    replay,
    resume,
)
from eidos.state.agent_tasks import node_status_for as _node_status_for  # same function; import path pinned once

from eidos_a2a_factories import FakeTransport, push_notification_body, submit_responds_with_task, wire_text_artifact
from eidos_agents_factories import ScriptedModel, make_settings
from eidos_mission_factories import make_mission, make_mission_plan
from eidos_recording_factories import three_docs
from eidos_runtime_factories import admit_all
from eidos_state_factories import at
from eidos_v04_registry import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID, make_registry
from eidos_validation_factories import make_system_limits

assert node_status_for is _node_status_for  # eidos.state re-exports eidos.state.agent_tasks.node_status_for verbatim

LIMITS = make_system_limits()


def _plan():
    state = make_mission(capabilities=("research", "cost"))
    plan = make_mission_plan(
        state, {"gather": "", "analyse": "gather", "check": "analyse"}, verify=("check",),
        capability_of={"gather": "research", "analyse": "cost"},
    )
    return state, plan


def _analysis_rig(store):
    scripted = ScriptedModel(lambda request: ModelResponse(text="Analysis [[artifact:gather]]."))
    model = RecordingModel(scripted, ModelCallTracker())
    return AnalysisAgent(model=model, settings=make_settings(), store=store)


def test_the_full_remote_boundary_scenario_submits_pauses_completes_and_resumes_to_a_finished_mission():
    state, plan = _plan()
    store = InMemoryArtifactStore()
    for document in three_docs():
        store.put_supplied(state.execution_id, document)

    transport = FakeTransport(submit_responds_with_task("remote-task-1", context_id="remote-ctx-1"))
    client = A2AClient(endpoint_url="https://research.example/rpc", transport=transport)
    a2a_agent = A2AWorkAgent(client=client, store=store, capability=CapabilityId("research"), webhook_url="https://eidos.example/webhook")
    agents = {RESEARCH_AGENT_ID: a2a_agent, ANALYSIS_AGENT_ID: _analysis_rig(store)}

    # --- pass 1: submit, then the run pauses AWAITING (Step 3's runtime, exercised for real) ---------------------
    report1 = run_baseline(
        state=state, plan=plan, limits=LIMITS, registry=make_registry(), agents=agents,
        verifier=VerificationAgent(store=store), admission_guard=admit_all(), executor_factory=SequentialExecutor,
    )
    run1 = report1.run
    assert run1.outcome is RunOutcome.AWAITING
    assert [info.step_id for info in run1.awaiting] == [StepId("gather")]
    assert run1.result_for(StepId("analyse")).status is NodeStatus.NOT_REACHED  # blocked by an unresolved predecessor, not skipped
    assert transport.call_count == 1  # exactly one A2A call for the one node that needed it

    submitted = a2a_agent.submitted_task(StepId("gather"))
    assert submitted is not None and submitted.task_id == "remote-task-1"

    # --- record what pass 1 produced, by hand (the D-167 sequence; see module docstring) --------------------------
    log = EventLog()
    n = iter(range(1, 100))

    def accept(payload):
        result = log.accept(EventProposal(
            event_id=EventId(UUID(int=next(n))), tenant_id=state.tenant_id, mission_id=state.mission_id,
            occurred_at=at(next(n)), recorded_at=at(next(n)), payload=payload,
        ))
        assert result.applied, result.reason
        return result

    accept(MissionCreatedPayload(task_genome=state.task_genome, reliability_contract=state.reliability_contract, execution_id=state.execution_id))
    accept(PlanGeneratedPayload(plan=plan))
    accept(PlanCompiledPayload(plan_id=plan.plan_id, plan_version=plan.version))
    accept(NodeStartedPayload(plan_id=plan.plan_id, step_id=StepId("gather"), kind=PlanStepKind.AGENT, capability=CapabilityId("research"), agent_id=RESEARCH_AGENT_ID))
    accept(A2ATaskStartedPayload(plan_id=plan.plan_id, step_id=StepId("gather"), agent_id=RESEARCH_AGENT_ID, a2a_task_id=submitted.task_id, a2a_context_id=submitted.context_id))
    accept(MissionPausedPayload(plan_id=plan.plan_id, awaiting=run1.awaiting))
    assert log.state.status.value == "paused"

    # --- the remote task concludes; a webhook delivers the news ----------------------------------------------------
    body = push_notification_body(
        task_id="remote-task-1", context_id="remote-ctx-1", state="TASK_STATE_COMPLETED",
        artifacts=[wire_text_artifact("a1", "Remote findings: [[doc:1]] [[doc:2]] [[doc:3]] confirm this.")],
    )
    result = notification_to_proposal(
        body, agent_tasks=log.state.agent_tasks, store=store, execution_id=state.execution_id,
        tenant_id=state.tenant_id, mission_id=state.mission_id, event_id=EventId(UUID(int=next(n))),
        occurred_at=at(next(n)), recorded_at=at(next(n)),
    )
    assert result.outcome is WebhookOutcome.PROPOSED

    intake = log.accept(result.proposal)
    assert intake.applied, intake.reason  # D-176's own exception, exercised for real: PAUSED still took this one event
    assert log.state.status.value == "paused"  # never auto-resumed (D-170)
    assert log.state.agent_tasks[0].status.value == "COMPLETED"

    # --- the caller resumes: PriorOutcomes carries the newly-known result, the runtime is asked again ---------------
    artifact_ref = log.state.agent_tasks[0].latest_artifact
    node_status = node_status_for(log.state.agent_tasks[0].status, artifact=artifact_ref)
    assert node_status is NodeStatus.SUCCEEDED
    prior = PriorOutcomes(
        tenant_id=state.tenant_id, mission_id=state.mission_id, execution_id=state.execution_id,
        plan_id=plan.plan_id, plan_version=plan.version,
        outcomes=(NodeResult(step_id=StepId("gather"), kind=PlanStepKind.AGENT, status=node_status, artifact=artifact_ref),),
    )
    report2 = run_baseline(
        state=state, plan=plan, limits=LIMITS, registry=make_registry(), agents=agents,
        verifier=VerificationAgent(store=store), admission_guard=admit_all(), executor_factory=SequentialExecutor, prior=prior,
    )
    run2 = report2.run
    assert run2.outcome is RunOutcome.FINISHED  # the runtime-level resume works completely (see the module docstring)
    assert transport.call_count == 1  # gather was carried over, not resubmitted (D-120)
    assert run2.result_for(StepId("gather")).status is NodeStatus.SUCCEEDED
    assert run2.result_for(StepId("analyse")).status is NodeStatus.SUCCEEDED
    assert run2.result_for(StepId("check")).status is NodeStatus.SUCCEEDED

    # --- the discovered gap, pinned as a fact rather than left as prose (see the module docstring) --------------------
    # D-167 says recording pass 2's events onto the same log "naturally produces the post-hoc NODE_SETTLED and ...
    # the mission's real terminal event". It does not: MissionState.status is still `paused`, and the reducer's
    # only exemption (D-176) is for the one A2A_TASK_COMPLETED already accepted above — an ordinary event after it
    # is refused exactly as any event after any other terminal status would be.
    blocked = log.accept(EventProposal(
        event_id=EventId(UUID(int=next(n))), tenant_id=state.tenant_id, mission_id=state.mission_id,
        occurred_at=at(next(n)), recorded_at=at(next(n)),
        payload=NodeStartedPayload(plan_id=plan.plan_id, step_id=StepId("analyse"), kind=PlanStepKind.AGENT, capability=CapabilityId("cost"), agent_id=ANALYSIS_AGENT_ID),
    ))
    assert not blocked.applied and blocked.reason == "the mission is paused, so it takes no further events"

    # --- replay equivalence (item 12), over the part of the log this step actually builds -------------------------------
    records = log.records
    assert replay(records).state == log.state
    for sequence in range(1, len(records) + 1):
        checkpoint = checkpoint_at(records, sequence)
        assert resume(checkpoint, records_after(records, checkpoint)).state == log.state
