"""Helpers for V0.4 scenarios: real agents over a scripted model, run through the single-pass runner on both backends.

``drive_baseline`` runs ``eidos.baseline.run_baseline`` once on the reference executor and once on the LangGraph backend, each with its
*own* artifact store and scripted model, and asserts the two ``BaselineReport`` values are identical byte for byte and that both stores
end up holding the same artifacts. A scenario then asserts what the run should have been, written out by hand.

The model is a scripted double (D-136); nothing here reaches a real model, and no number here is a measurement.
"""

from dataclasses import dataclass, field

from eidos.agents import (
    AnalysisAgent,
    InMemoryArtifactStore,
    ModelResponse,
    ResearchAgent,
    VerificationAgent,
)
from eidos.backends.langgraph import LangGraphExecutor
from eidos.baseline import BaselineReport, run_baseline
from eidos.capabilities import CapabilityRegistry
from eidos.contracts import MissionState, Plan
from eidos.runtime import SequentialExecutor
from eidos.validation import SystemLimits

from eidos_agents_factories import ScriptedModel, doc, make_settings
from eidos_backend_factories import locked_admit_all
from eidos_validation_factories import make_system_limits

from eidos_v04_registry import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID, make_registry  # noqa: F401  (re-exported for the scenarios)


def answer_by_task(research="Findings [[doc:1]] [[doc:2]] [[doc:3]].", analysis="Analysis [[artifact:gather]] [[doc:1]]."):
    """A scripted model that answers a research prompt and an analysis prompt differently (a fixed text each)."""

    def respond(request):
        text = research if "Documents:" in request.prompt else analysis
        return text if not isinstance(text, str) else ModelResponse(text=text)

    return respond


def three_documents():
    return tuple(doc(f"doc:{n}", f"Source document {n}.") for n in (1, 2, 3))


@dataclass
class Rig:
    """One executor's world: its own store, its own scripted model, and the agents built over them."""

    store: InMemoryArtifactStore
    model: ScriptedModel
    agents: dict
    verifier: VerificationAgent


def new_rig(state: MissionState, respond, docs, agents_for=None) -> Rig:
    store = InMemoryArtifactStore()
    for document in docs:
        store.put_supplied(state.execution_id, document)
    model = ScriptedModel(respond)
    settings = make_settings()
    agents = {
        RESEARCH_AGENT_ID: ResearchAgent(model=model, settings=settings, store=store),
        ANALYSIS_AGENT_ID: AnalysisAgent(model=model, settings=settings, store=store),
    }
    if agents_for is not None:
        agents.update(agents_for(model, settings, store))
    return Rig(store=store, model=model, agents=agents, verifier=VerificationAgent(store=store))


@dataclass
class V04Attempt:
    report: BaselineReport  # the reference executor's; ``drive_baseline`` has asserted the backend's is identical
    reference: Rig
    backend: Rig
    guards: tuple = field(default_factory=tuple)

    @property
    def rigs(self):
        return (self.reference, self.backend)


def drive_baseline(
    state: MissionState,
    plan: Plan,
    *,
    respond=None,
    docs=None,
    guard=None,
    prior=None,
    limits: SystemLimits | None = None,
    registry: CapabilityRegistry | None = None,
    agents_for=None,
    rigs=None,
) -> V04Attempt:
    """Run ``plan`` on both executors, each over its own rig (or the ``rigs`` of an earlier attempt, to resume)."""
    docs = three_documents() if docs is None else docs
    if rigs is None:
        rigs = tuple(new_rig(state, respond or answer_by_task(), docs, agents_for) for _ in range(2))
    elif respond is not None:
        for rig in rigs:  # continuing an earlier attempt with a different script
            rig.model.script(respond)
    reports, guards = [], []
    for executor_class, rig in zip((SequentialExecutor, LangGraphExecutor), rigs):
        the_guard = guard() if guard else locked_admit_all()
        reports.append(
            run_baseline(
                state=state,
                plan=plan,
                limits=limits or make_system_limits(),
                registry=registry or make_registry(),
                agents=rig.agents,
                verifier=rig.verifier,
                admission_guard=the_guard,
                executor_factory=executor_class,
                prior=prior,
            )
        )
        guards.append(the_guard)
    reference, backend = reports
    assert backend == reference
    assert backend.model_dump_json() == reference.model_dump_json()
    ref_rig, lg_rig = rigs
    assert sorted(r.prompt for r in lg_rig.model.requests) == sorted(r.prompt for r in ref_rig.model.requests)
    for step in _step_ids(plan):
        assert lg_rig.store.get_step_artifact(state.execution_id, step) == ref_rig.store.get_step_artifact(state.execution_id, step)
    return V04Attempt(report=reference, reference=ref_rig, backend=lg_rig, guards=tuple(guards))


def _step_ids(plan: Plan):
    return tuple(step.step_id for step in plan.steps)
