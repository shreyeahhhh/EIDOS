"""The optional recording tracker of ``run_with_replanning`` (decisions.md D-204 item 1, D-231; V1.4-B).

One additive, keyword-only, optional parameter, forwarded to every attempt's ``record_attempt``. With no tracker nothing changes (the default is what every earlier
caller got, and it is still recorded without model facts); with one, the model, tool, retrieval and citation facts of the wrappers that share it are recorded on
the settled nodes of every attempt, replan attempts included. Real orchestration, real agents, a scripted model.
"""

import pytest

import eidos.replanning as replanning_module
from eidos.agents import AnalysisAgent, EvidenceLedger, InMemoryArtifactStore, KnowledgeGate, ResearchAgent, VerificationAgent
from eidos.knowledge import LexicalKnowledgePort
from eidos.memory import JsonlExperienceStore
from eidos.planning import DeterministicSelector, RuleBasedCandidateGenerator
from eidos.recording import (
    ModelCallTracker,
    RecordingCitations,
    RecordingKnowledgePort,
    RecordingModel,
    UuidEventIds,
    UuidPlanIds,
    UuidStrategyIds,
)
from eidos.replanning import ReplanRun, run_with_replanning
from eidos.runtime import SequentialExecutor
from eidos.service.views import whole_execution_record
from eidos.state import CitationKind, RetrievalOutcome, audit_evidence, execution_record

from eidos_agents_factories import ScriptedModel, make_settings
from eidos_knowledge_gate_fixture import KB, SNAPSHOT, descriptor_for, make_rag_mission
from eidos_mission_factories import make_mission
from eidos_planning_factories import GENEROUS_LIMITS
from eidos_recording_factories import FixedClock
from eidos_replanning_factories import ScriptedCalls, always_fails, fail_first_n_calls, replan
from eidos_runtime_factories import admit_all
from eidos_search_fixture import cite_every_document
from eidos_v04_registry import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID, make_registry

TWO = ("research", "cost")


def run_tracked(state, respond, tracker, tmp_path, *, knowledge=None, model_tracker=None):
    """A real replanning run whose model (and, when given, knowledge access) is recorded through ``model_tracker`` and whose orchestrator is handed ``tracker``."""
    store = InMemoryArtifactStore()
    if knowledge is None:
        for number in (1, 2, 3):
            from eidos_agents_factories import doc

            store.put_supplied(state.execution_id, doc(f"doc:{number}", f"Source document {number}."))
    scripted = ScriptedModel(respond)
    shared = model_tracker if model_tracker is not None else tracker
    model = RecordingModel(scripted, shared) if shared is not None else scripted
    research = ResearchAgent(model=model, settings=make_settings(), store=store, **({} if knowledge is None else {"knowledge": knowledge(store, shared)}))
    analysis = AnalysisAgent(model=model, settings=make_settings(), store=store)
    agents = {RESEARCH_AGENT_ID: research, ANALYSIS_AGENT_ID: analysis}
    if shared is not None and knowledge is not None:
        agents = {agent_id: RecordingCitations(agent, shared, store) for agent_id, agent in agents.items()}
    run = run_with_replanning(
        state=state, limits=GENEROUS_LIMITS, registry=make_registry(), agents=agents, verifier=VerificationAgent(store=store),
        admission_guard_factory=admit_all, executor_factory=SequentialExecutor, clock=FixedClock(), ids=UuidEventIds(),
        strategy_ids=UuidStrategyIds(), plan_ids=UuidPlanIds(), candidate_generator=RuleBasedCandidateGenerator(), max_candidates=3,
        selector=DeterministicSelector(), store=JsonlExperienceStore.open(tmp_path / "experience.jsonl"), tracker=tracker,
    )
    assert isinstance(run, ReplanRun), run
    return run, scripted


def facts_by_plan(run):
    """``{plan_version: every settled step's model-call facts}`` from the recorded log alone."""
    result = {}
    for plan in run.plans:
        record = execution_record(run.log.records, plan_id=plan.plan_id)
        result[plan.version] = [call for step in record.steps for call in step.model_calls]
    return result


def test_without_a_tracker_nothing_about_model_calls_is_recorded_under_replanning_exactly_as_before(tmp_path):
    state = make_mission(capabilities=TWO, seed=2)
    run = replan(state, selector=DeterministicSelector(), store=JsonlExperienceStore.open(tmp_path / "e.jsonl"), respond=fail_first_n_calls(1))
    assert len(run.plans) == 2 and run.telemetry.model_call_count == 0
    assert all(not step.model_calls for plan in run.plans for step in execution_record(run.log.records, plan_id=plan.plan_id).steps)


def test_with_a_tracker_every_attempt_records_its_model_calls_and_the_replanned_mission_still_completes(tmp_path):
    tracker = ModelCallTracker()
    state = make_mission(capabilities=TWO, seed=2)
    run, scripted = run_tracked(state, fail_first_n_calls(1), tracker, tmp_path)
    assert len(run.plans) == 2 and run.replans_used == 1 and run.refused == () and run.discrepancies == ()
    per_plan = facts_by_plan(run)
    assert all(per_plan[version] for version in (1, 2))  # both attempts, the replan included
    assert sum(len(calls) for calls in per_plan.values()) == len(scripted.requests)  # every call the model saw, once, on the node that made it
    first_outcomes = {call.outcome.value for call in per_plan[1]}
    assert first_outcomes & {"unavailable"} and {call.outcome.value for call in per_plan[2]} == {"response"}  # the outage is attempt one's, the answers attempt two's
    assert run.telemetry.model_call_count == len(per_plan[2]) and run.telemetry.tokens_used > 0  # the final attempt's own scoped projection
    assert run.telemetry.mission_status.value == "completed" and run.telemetry.verified is True
    assert all(experience.model_call_count > 0 for experience in run.experiences)  # the experiences now carry the real counts


def test_supplying_a_tracker_changes_no_event_and_no_outcome_only_the_facts_it_makes_recordable(tmp_path):
    def shape(run):
        return [(record.event.type.value, getattr(record.payload, "result", None) and record.payload.result.status.value) for record in run.log.records]

    plain = replan(make_mission(capabilities=TWO, seed=2), selector=DeterministicSelector(), store=JsonlExperienceStore.open(tmp_path / "a.jsonl"), respond=fail_first_n_calls(1))
    tracked, _ = run_tracked(make_mission(capabilities=TWO, seed=2), fail_first_n_calls(1), ModelCallTracker(), tmp_path)
    assert shape(tracked) == shape(plain)


@pytest.mark.parametrize("supplied", [False, True], ids=["default", "supplied"])
def test_the_tracker_is_forwarded_untouched_to_every_attempt_and_the_default_is_none(supplied, tmp_path, monkeypatch):
    seen = []
    real = replanning_module.record_attempt

    def spy(**kwargs):
        seen.append(kwargs["tracker"])
        return real(**kwargs)

    monkeypatch.setattr(replanning_module, "record_attempt", spy)
    tracker = ModelCallTracker() if supplied else None
    run, _ = run_tracked(make_mission(capabilities=TWO, seed=2), fail_first_n_calls(1), tracker, tmp_path, model_tracker=tracker)
    assert len(seen) == len(run.plans) == 2
    assert all(item is tracker for item in seen)  # the same object for every attempt when supplied; None for every attempt when not


def test_retrieval_and_citation_facts_are_recorded_across_a_replan_and_the_audit_resolves_them_from_the_log_alone(tmp_path):
    state = make_rag_mission()
    tracker = ModelCallTracker()
    clock = FixedClock()

    def knowledge(store, shared):
        port = RecordingKnowledgePort(LexicalKnowledgePort(SNAPSHOT, kb_id=KB), shared, clock)
        return KnowledgeGate(descriptor=descriptor_for(), port=port, ledger=EvidenceLedger(), store=store)

    # research answers and cites, analysis fails (so the mission replans), then everything succeeds
    respond = ScriptedCalls((cite_every_document, always_fails), then=cite_every_document)
    run, _ = run_tracked(state, respond, tracker, tmp_path, knowledge=knowledge)
    assert len(run.plans) == 2 and run.refused == () and run.discrepancies == ()
    first, second = (execution_record(run.log.records, plan_id=plan.plan_id) for plan in run.plans)
    research_one = next(step for step in first.steps if step.retrievals)
    assert [facts.outcome for facts in research_one.retrievals] == [RetrievalOutcome.RESULT] and len(research_one.citations) == 4
    assert all(not step.retrievals for step in second.steps)  # the repeated question is served by the gate, so the replan attempt records no retrieval of its own
    assert any(step.citations for step in second.steps)  # and it still cites what it was shown
    # The default execution record is the last plan's steps only, and the retrieval fact is on the first attempt's node, so an audit over it alone cannot resolve the second attempt's
    # evidence citations. The whole-execution view (every plan's steps, laid into one validated record) does: that is the view the product backend audits (D-234).
    kinds_of_last_plan = {trace.kind for trace in audit_evidence(execution_record(run.log.records)).traces}
    assert CitationKind.UNRESOLVED in kinds_of_last_plan
    kinds = {trace.kind for trace in audit_evidence(whole_execution_record(run.log.records)).traces}
    assert CitationKind.RESOLVED in kinds and CitationKind.UNRESOLVED not in kinds and CitationKind.AMBIGUOUS not in kinds
