"""Scenarios: the V0.4 baseline workflow with real agents over a scripted model (decisions.md D-131, D-133, D-138, D-140, D-144 to D-146).

A real ``MissionState``, a supplied plan (Research, Analysis, ``VERIFY``), supplied documents, the real Research, Analysis and Verification
agents, and a *scripted* model, run once through validate, compile, bind and execute on **both** executors. ``drive_baseline`` asserts the two
give byte-identical reports; each scenario then asserts what the run should have been. No real model is involved and no number here is a
measurement (D-136).

V0.4 emits no events (D-123), so the scenarios assert on the ``RunResult`` (every node's status and reason, the dispatch order), on the artifact
store, and on what the model was asked.
"""

import pytest

from eidos.baseline import BaselineStage
from eidos.contracts import StepId
from eidos.runtime import NodeStatus, RunOutcome

from eidos_agents_factories import doc
from eidos_backend_factories import locked_halt_when
from eidos_scenario_factories import make_mission, make_mission_plan
from eidos_v04_factories import answer_by_task, drive_baseline, three_documents

SPEC = {"gather": "", "analyse": "gather", "check": "analyse"}
CAPABILITY_OF = {"gather": "research", "analyse": "cost"}


def mission(**contract_overrides):
    return make_mission(capabilities=("research", "cost"), **contract_overrides)


def baseline_plan(state, **kwargs):
    return make_mission_plan(state, SPEC, verify=("check",), capability_of=CAPABILITY_OF, **kwargs)


# --- the baseline finishes, and what "verified" means -------------------------------------------------------------------------


def test_the_baseline_runs_from_supplied_documents_to_a_verified_finished_run_on_both_backends():
    state = mission()
    attempt = drive_baseline(state, baseline_plan(state))
    report, run = attempt.report, attempt.report.run

    assert report.stopped_at is None and report.validation.accepted and report.compilation.succeeded and report.binding.succeeded
    assert run.outcome is RunOutcome.FINISHED and run.verified is True
    assert run.dispatched == ("gather", "analyse", "check")
    assert [(r.step_id, r.status) for r in run.results] == [
        ("gather", NodeStatus.SUCCEEDED), ("analyse", NodeStatus.SUCCEEDED), ("check", NodeStatus.SUCCEEDED),
    ]
    assert [r.artifact for r in run.results[:2]] == ["artifact:gather", "artifact:analyse"]
    # Each agent's output is in the store as a four-field artifact citing what the model cited.
    gather = attempt.reference.store.get_step_artifact(state.execution_id, StepId("gather"))
    analyse = attempt.reference.store.get_step_artifact(state.execution_id, StepId("analyse"))
    assert gather.source_refs == ("doc:1", "doc:2", "doc:3") and analyse.source_refs == ("artifact:gather", "doc:1")
    assert gather.content_type == analyse.content_type == "text/markdown"
    # Two model calls: research and analysis. Verification asked nothing of a model.
    assert attempt.reference.model.calls == 2


def test_a_pass_says_what_was_not_evaluated_and_does_not_claim_the_contract_is_satisfied():
    state = mission()
    reason = drive_baseline(state, baseline_plan(state)).report.run.result_for(StepId("check")).reason

    assert "schema_validity satisfied" in reason and "citation_coverage satisfied" in reason
    assert "minimum_distinct_sources satisfied (3 distinct supplied source(s) reached, 3 required)" in reason
    assert "NOT_EVALUATED: min_quality, max_risk_level" in reason
    assert "not a claim that the reliability contract is satisfied" in reason


def test_the_mission_state_is_read_and_never_written_and_the_run_is_bound_to_its_execution():
    state = mission()
    before = state.model_dump_json()

    run = drive_baseline(state, baseline_plan(state)).report.run

    assert state.model_dump_json() == before
    assert (run.tenant_id, run.mission_id, run.execution_id) == (state.tenant_id, state.mission_id, state.execution_id)


def test_the_agents_are_asked_about_the_mission_goal_and_the_documents_they_may_cite():
    state = mission()
    attempt = drive_baseline(state, baseline_plan(state))
    prompts = {("Documents:" in r.prompt): r.prompt for r in attempt.reference.model.requests}

    assert state.task_genome.goal in prompts[True] and state.task_genome.goal in prompts[False]
    for n in (1, 2, 3):
        assert f"[[doc:{n}]]" in prompts[True] and f"Source document {n}." in prompts[True]
    assert "[[artifact:gather]]" in prompts[False]  # the analysis reads the research output
    assert all(r.settings.model == "test-model" and r.settings.timeout_seconds == 5.0 for r in attempt.reference.model.requests)


# --- well-formed output that fails verification (invariant 12) -------------------------------------------------------------------


def test_well_formed_output_that_cites_a_source_that_does_not_exist_fails_verification_and_fails_the_run():
    state = mission()
    respond = answer_by_task(analysis="A confident, well-formed analysis [[artifact:gather]] [[ghost]].")

    attempt = drive_baseline(state, baseline_plan(state), respond=respond)
    run = attempt.report.run

    assert run.outcome is RunOutcome.FAILED and run.verified is False
    assert run.result_for(StepId("analyse")).status is NodeStatus.SUCCEEDED  # the agent "returned output"
    check = run.result_for(StepId("check"))
    assert check.status is NodeStatus.VERIFICATION_FAILED
    assert "'ghost', which does not exist" in check.reason
    assert "NOT_EVALUATED: min_quality, max_risk_level" in check.reason


def test_too_few_distinct_sources_for_the_contract_fails_verification():
    state = mission(min_independent_evidence=4)  # three documents were supplied

    check = drive_baseline(state, baseline_plan(state)).report.run.result_for(StepId("check"))

    assert check.status is NodeStatus.VERIFICATION_FAILED
    assert "3 distinct supplied source(s) reached, 4 required" in check.reason


def test_min_quality_changes_nothing_because_no_quality_is_measured():
    for min_quality in (0.0, 0.99):
        state = mission(min_quality=min_quality)
        check = drive_baseline(state, baseline_plan(state)).report.run.result_for(StepId("check"))
        assert check.status is NodeStatus.SUCCEEDED and "NOT_EVALUATED: min_quality" in check.reason


def test_an_analysis_that_cites_nothing_fails_verification():
    state = mission()

    run = drive_baseline(state, baseline_plan(state), respond=answer_by_task(analysis="An analysis with no citations.")).report.run

    assert run.result_for(StepId("check")).status is NodeStatus.VERIFICATION_FAILED
    assert "cites no source" in run.result_for(StepId("check")).reason


def test_a_failed_verification_gates_what_follows_it():
    state = mission()
    spec = {"gather": "", "analyse": "gather", "check": "analyse", "publish": "check"}
    plan = make_mission_plan(state, spec, verify=("check",), capability_of={**CAPABILITY_OF, "publish": "cost"})

    attempt = drive_baseline(state, plan, respond=answer_by_task(analysis="Uncited."))
    run = attempt.report.run

    assert run.result_for(StepId("publish")).status is NodeStatus.SKIPPED
    assert attempt.reference.model.calls == 2  # the publish step's agent was never asked


# --- failures are contained -----------------------------------------------------------------------------------------------------


def test_a_model_outage_fails_the_step_it_hit_and_everything_behind_it_is_skipped():
    from eidos.agents import ModelFailure, ModelFailureKind

    state = mission()
    respond = lambda request: ModelFailure(kind=ModelFailureKind.TIMEOUT, message="the local model did not answer in time")

    attempt = drive_baseline(state, baseline_plan(state), respond=respond)
    run = attempt.report.run

    assert run.outcome is RunOutcome.FAILED
    assert [(r.step_id, r.status) for r in run.results] == [
        ("gather", NodeStatus.FAILED), ("analyse", NodeStatus.SKIPPED), ("check", NodeStatus.SKIPPED),
    ]
    assert "timeout" in run.result_for(StepId("gather")).reason
    assert attempt.reference.store.get_step_artifact(state.execution_id, StepId("gather")) is None


def test_a_model_that_answers_nothing_is_no_result_not_a_success():
    from eidos.agents import ModelFailure, ModelFailureKind

    state = mission()
    respond = lambda request: ModelFailure(kind=ModelFailureKind.EMPTY_RESPONSE, message="the model returned no text")

    run = drive_baseline(state, baseline_plan(state), respond=respond).report.run

    assert run.result_for(StepId("gather")).status is NodeStatus.NO_RESULT
    assert run.verified is False


def test_a_model_adapter_that_raises_is_contained_as_a_failed_node():
    def broken(request):
        raise RuntimeError("adapter bug")

    state = mission()
    run = drive_baseline(state, baseline_plan(state), respond=broken).report.run

    assert run.result_for(StepId("gather")).status is NodeStatus.FAILED
    assert "adapter bug" in run.result_for(StepId("gather")).reason


def test_nothing_supplied_means_nothing_to_research():
    state = mission()

    attempt = drive_baseline(state, baseline_plan(state), docs=())

    assert attempt.report.run.result_for(StepId("gather")).status is NodeStatus.NO_RESULT
    assert attempt.reference.model.calls == 0  # the model is never asked to answer from memory


# --- the gates before execution ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("capability", ["verification", "security_analysis", "Research", "billing"])
def test_an_unbound_capability_stops_the_run_at_binding_before_anything_is_dispatched(capability):
    state = make_mission(capabilities=("research", capability))
    plan = make_mission_plan(state, {"gather": "", "analyse": "gather"}, capability_of={"gather": "research", "analyse": capability})

    attempt = drive_baseline(state, plan)

    assert attempt.report.validation.accepted and attempt.report.compilation.succeeded  # V0.2 and the compiler have no quarrel
    assert attempt.report.stopped_at is BaselineStage.BINDING and attempt.report.run is None
    assert [(v.step_id, v.capability) for v in attempt.report.binding.violations] == [("analyse", capability)]
    assert attempt.reference.model.calls == 0 and attempt.backend.model.calls == 0
    assert attempt.reference.store.get_step_artifact(state.execution_id, StepId("gather")) is None  # not even research ran


def test_an_invalid_plan_stops_at_validation_and_nothing_else_runs():
    state = mission()
    plan = make_mission_plan(state, {"a": "b", "b": "a"}, capability_of={"a": "research", "b": "research"})  # a cycle

    attempt = drive_baseline(state, plan)

    assert attempt.report.stopped_at is BaselineStage.VALIDATION
    assert attempt.report.compilation is None and attempt.report.binding is None and attempt.report.run is None
    assert attempt.reference.model.calls == 0


def test_a_step_kind_v04_does_not_execute_stops_at_compilation():
    from eidos.contracts import PlanStepKind

    state = mission()
    plan = make_mission_plan(state, {"gather": "", "route": "gather"}, capability_of={"gather": "research"}, controls={"route": PlanStepKind.ROUTE})

    attempt = drive_baseline(state, plan)

    assert attempt.report.stopped_at is BaselineStage.COMPILATION
    assert attempt.report.binding is None and attempt.report.run is None and attempt.reference.model.calls == 0


# --- halting and resuming -------------------------------------------------------------------------------------------------------


def test_a_halt_pauses_the_run_before_the_analysis_and_a_resume_finishes_it_without_asking_the_research_model_again():
    from eidos.runtime import PriorOutcomes

    state = mission()
    plan = baseline_plan(state)
    halt_analysis = lambda: locked_halt_when(lambda request: request.step_id == "analyse", "held for review")

    paused = drive_baseline(state, plan, guard=halt_analysis)
    assert paused.report.run.outcome is RunOutcome.HALTED and paused.report.run.halt.step_id == "analyse"
    assert paused.reference.model.calls == 1  # research only
    assert paused.report.run.result_for(StepId("gather")).status is NodeStatus.SUCCEEDED

    resumed = drive_baseline(state, plan, prior=PriorOutcomes.succeeded_from(paused.report.run), rigs=paused.rigs)
    run = resumed.report.run
    assert run.outcome is RunOutcome.FINISHED and run.verified is True
    assert run.dispatched == ("analyse", "check")
    assert resumed.reference.model.calls == 2  # research once, analysis once: never research again
    assert resumed.reference.store.get_step_artifact(state.execution_id, StepId("gather")).content.startswith("Findings")


def test_a_replan_is_a_new_plan_run_again_and_the_old_artifacts_are_not_overwritten():
    # D-119: a replan is a caller-supplied new plan. Its steps have their own ids, because a step's primary artifact is
    # write-once within an execution (D-137); reusing an id would be refused rather than overwrite.
    state = mission()
    v1 = baseline_plan(state)
    failed = drive_baseline(state, v1, respond=answer_by_task(analysis="Uncited."))
    assert failed.report.run.outcome is RunOutcome.FAILED

    spec_v2 = {"gather2": "", "analyse2": "gather2", "check2": "analyse2"}
    v2 = make_mission_plan(state, spec_v2, verify=("check2",), capability_of={"gather2": "research", "analyse2": "cost"},
                           version=2, parent=v1, reason="verification failed: the analysis cited no source")
    respond = answer_by_task(research="R [[doc:1]] [[doc:2]] [[doc:3]]", analysis="A [[artifact:gather2]] [[doc:1]]")
    second = drive_baseline(state, v2, respond=respond, rigs=failed.rigs)

    assert second.report.run.outcome is RunOutcome.FINISHED and second.report.run.verified is True
    assert second.report.run.plan_version == 2
    store = second.reference.store
    assert store.get_step_artifact(state.execution_id, StepId("analyse")).content == "Uncited."  # v1's record is intact
    assert store.get_step_artifact(state.execution_id, StepId("analyse2")) is not None


def test_reusing_a_step_id_across_plan_versions_in_one_execution_is_refused_not_overwritten():
    state = mission()
    plan = baseline_plan(state)
    first = drive_baseline(state, plan)
    assert first.report.run.outcome is RunOutcome.FINISHED
    v2 = make_mission_plan(state, SPEC, verify=("check",), capability_of=CAPABILITY_OF, version=2, parent=plan, reason="run again")

    again = drive_baseline(state, v2, rigs=first.rigs)

    gather = again.report.run.result_for(StepId("gather"))
    assert gather.status is NodeStatus.FAILED and "could not be recorded" in gather.reason
    assert again.report.run.outcome is RunOutcome.FAILED


# --- the agents can be swapped without touching the core (invariant 9) and the runner is not tied to a domain (invariant 10) ---------


def test_a_different_research_implementation_serves_the_same_capability_without_any_change_to_the_core():
    from eidos.agents import Artifact, artifact_ref_for
    from eidos.runtime import WorkResult

    class ArchiveResearcher:
        """A research agent that never asks a model: it summarises the supplied documents itself."""

        def __init__(self, store):
            self.store = store

        def run(self, context, node):
            documents = self.store.supplied(context.execution_id)
            ref = artifact_ref_for(node.step_id)
            body = "Archive summary. " + " ".join(f"[[{d.ref}]]" for d in documents)
            self.store.put_step_artifact(context.execution_id, node.step_id, Artifact(
                ref=ref, content_type="text/markdown", content=body, source_refs=tuple(d.ref for d in documents)))
            return WorkResult.produced(ref)

    from eidos_v04_factories import RESEARCH_AGENT_ID

    state = mission()
    attempt = drive_baseline(state, baseline_plan(state), agents_for=lambda model, settings, store: {RESEARCH_AGENT_ID: ArchiveResearcher(store)})

    run = attempt.report.run
    assert run.outcome is RunOutcome.FINISHED and run.verified is True
    assert attempt.reference.model.calls == 1  # only the analysis asked a model; the substitute research did not
    assert attempt.reference.store.get_step_artifact(state.execution_id, StepId("gather")).content.startswith("Archive summary.")


def test_the_same_pipeline_runs_a_mission_in_an_unrelated_domain():
    from eidos_factories import make_mission_state, make_task_genome

    state = mission()
    contract = state.reliability_contract
    genome = make_task_genome(contract=contract, goal="Decide whether the harbour bridge needs its bearings replaced",
                              required_capabilities=state.task_genome.required_capabilities)

    bridge = make_mission_state(
        tenant_id=state.tenant_id, mission_id=state.mission_id, execution_id=state.execution_id,
        reliability_contract=contract, task_genome=genome, plans=(), active_plan_id=None,
    )
    docs = tuple(doc(f"inspection:{n}", f"Inspection report {n}: bearing wear noted.") for n in (1, 2, 3))
    respond = answer_by_task(research="Wear [[inspection:1]] [[inspection:2]] [[inspection:3]].", analysis="Replace [[artifact:gather]] [[inspection:1]].")

    attempt = drive_baseline(bridge, baseline_plan(bridge), respond=respond, docs=docs)

    assert attempt.report.run.outcome is RunOutcome.FINISHED and attempt.report.run.verified is True
    assert all("harbour bridge" in r.prompt for r in attempt.reference.model.requests)
