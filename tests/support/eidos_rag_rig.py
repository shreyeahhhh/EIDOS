"""The rig that composes one whole retrieval-augmented mission and records it (decisions.md D-228; V1.3 Step 7).

Mission -> Research -> knowledge gate -> a retriever -> evidence ledger -> cited research result -> Analysis -> the existing verification -> the mission's result, as one recorded pass. Every part
is the real one except the model, which is scripted (nothing here is a measurement), and, in the tests that ask for it, the semantic worker behind the process boundary, which is the real worker
program over a stub model. What sits between the retriever and the recorded log is exactly what production composition would put there: the counting wrapper (a test's own), the recording wrapper
(``RecordingKnowledgePort``), the knowledge gate, and the agents wrapped by ``RecordingCitations``. Nothing here does I/O of its own.
"""

from dataclasses import dataclass

from eidos.agents import AnalysisAgent, EvidenceLedger, InMemoryArtifactStore, KnowledgeGate, MeasuredFacts, ModelResponse, ResearchAgent, VerificationAgent
from eidos.contracts import MissionState, Plan
from eidos.knowledge import KnowledgeSnapshot
from eidos.recording import ModelCallTracker, RecordedRun, RecordingCitations, RecordingKnowledgePort, RecordingModel
from eidos.runtime import RunResult
from eidos_agents_factories import ScriptedModel, make_settings
from eidos_knowledge_gate_fixture import GOAL, KB, SNAPSHOT, ScriptedKnowledgePort, descriptor_for, make_rag_mission, tool_mission_plan
from eidos_recording_factories import FixedClock, Rig, record
from eidos_search_fixture import cite_every_document
from eidos_v04_registry import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID


@dataclass
class RagRun:
    """One recorded retrieval-augmented pass and every part it ran through, so a test can look at the log and at what produced it."""

    state: MissionState
    plan: Plan
    run: RecordedRun
    rig: Rig
    ledger: EvidenceLedger
    gate: KnowledgeGate
    port: ScriptedKnowledgePort  # what reached the retriever
    clock: FixedClock

    @property
    def result(self) -> RunResult:
        assert isinstance(self.run.report.run, RunResult), self.run.report.run
        return self.run.report.run


def run_rag(
    retriever,
    *,
    snapshot: KnowledgeSnapshot = SNAPSHOT,
    goal: str = GOAL,
    kb_id: str = KB,
    scheme_id: str | None = None,
    top_k: int = 4,
    min_independent_evidence: int = 2,
    respond=cite_every_document,
    plan_of=tool_mission_plan,
    seed: int = 1,
) -> RagRun:
    """Record one pass of a mission whose Research node asks ``retriever`` (anything with ``retrieve``, or a scripted answer) about the mission goal.

    ``respond`` scripts the model; by default it cites every reference the prompt shows. ``plan_of`` makes the plan from the mission, so a test can shape it.
    """
    state = make_rag_mission(goal=goal, seed=seed, min_independent_evidence=min_independent_evidence)
    plan = plan_of(state)
    store = InMemoryArtifactStore()
    tracker, clock, ledger = ModelCallTracker(), FixedClock(), EvidenceLedger()
    counted = ScriptedKnowledgePort(retriever.retrieve)
    recorded_port = RecordingKnowledgePort(counted, tracker, clock)
    descriptor = descriptor_for(snapshot, top_k=top_k, kb_id=kb_id, **({} if scheme_id is None else {"scheme_id": scheme_id}))
    gate = KnowledgeGate(descriptor=descriptor, port=recorded_port, ledger=ledger, store=store)
    scripted = ScriptedModel(respond)
    model = RecordingModel(scripted, tracker)
    settings = make_settings()
    agents = {
        RESEARCH_AGENT_ID: RecordingCitations(ResearchAgent(model=model, settings=settings, store=store, knowledge=gate), tracker, store),
        ANALYSIS_AGENT_ID: RecordingCitations(AnalysisAgent(model=model, settings=settings, store=store), tracker, store),
    }
    rig = Rig(store=store, scripted=scripted, tracker=tracker, agents=agents, verifier=VerificationAgent(store=store))
    run, _ = record(state, plan, rig, clock=clock)
    return RagRun(state=state, plan=plan, run=run, rig=rig, ledger=ledger, gate=gate, port=counted, clock=clock)


FABRICATED = "[[evidence:0000000000000000]]"


def _with_a_fabricated_citation_where(answering_research: bool):
    def respond(request):
        answer = cite_every_document(request)
        if ("Documents:" in request.prompt) is not answering_research:
            return answer
        return ModelResponse(text=f"{answer.text} {FABRICATED}", measured=MeasuredFacts(prompt_tokens=100, output_tokens=50, elapsed_seconds=0.5))

    return respond


# A scripted model that also cites an evidence reference no retrieval ever produced, in its analysis only, or in its research only.
cite_a_reference_nobody_retrieved = _with_a_fabricated_citation_where(False)
cite_a_reference_nobody_retrieved_in_research = _with_a_fabricated_citation_where(True)
