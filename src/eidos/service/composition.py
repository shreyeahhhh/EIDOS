"""The per-run composition: everything one ``run_with_replanning`` call is handed (decisions.md D-231, D-234; ``docs/13`` section 6).

Nothing is shared between runs except the model port and the optional knowledge port, both thread-safe by contract: every store, gate, ledger, tracker, log and experience store is built
for the run and dropped with it, so per-execution memory is freed and nothing leaks between missions or tenants.

What the composition supplies, and what it does not:

- the two work agents and ``VerificationAgent`` (exactly three logical agents, D-131), wrapped with the recording adapters that share one tracker, so the run records model, retrieval and
  citation facts on every node (D-231);
- a ``DurableEventLog`` and a write-through artifact store over the run's outbox (D-230);
- the deterministic reference candidate generator and selector, the sequential reference executor, ``SystemLimits`` from configuration (D-103, provisional), the system clock and UUID id sources;
- a per-mission in-memory experience store: nothing is learned across missions and nothing leaks across tenants (strategy memory persistence is a later decision);
- **an always-admit admission guard that enforces no budget** (D-127, D-156). It exists because ``run_with_replanning`` needs one and none ships; it is not budget enforcement and nothing
  here claims it is;
- **no tool and no MCP server** (deferred). **Knowledge is optional** (D-234, D-227): when a ``KnowledgeProvision`` is given, Research reaches it through the existing ``KnowledgeGate``; the
  service ships no loader and makes no production knowledge-base choice.
"""

import threading
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from eidos.agents import (
    AnalysisAgent,
    Artifact,
    EvidenceLedger,
    KnowledgeBaseDescriptor,
    KnowledgeGate,
    ModelPort,
    ResearchAgent,
    VerificationAgent,
)
from eidos.capabilities import AgentDescriptor, CapabilityRegistry
from eidos.memory import ExecutionExperience
from eidos.planning import DeterministicSelector, RuleBasedCandidateGenerator
from eidos.recording import (
    Clock,
    ModelCallTracker,
    RecordingCitations,
    RecordingKnowledgePort,
    RecordingModel,
    SystemClock,
    UuidEventIds,
    UuidPlanIds,
    UuidStrategyIds,
)
from eidos.runtime import AdmissionDecision, AdmissionRequest, SequentialExecutor

from .config import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID, ServiceConfig
from .durable import DurableEventLog, RunPersistence, WriteThroughArtifactStore
from .ports import EventStore, MissionRecord
from .spec import contract_and_genome, initial_state


class AlwaysAdmit:
    """An admission guard that admits every node. **It enforces no budget** (D-127, D-156): the contract's budgets are recorded, not enforced, and this guard does not change that."""

    def admit(self, request: AdmissionRequest) -> AdmissionDecision:
        return AdmissionDecision.admit()


class InMemoryExperienceStore:
    """A per-mission ``ExperienceStore``. Thread-safe; holds only what its one mission's attempts appended."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._held: tuple[ExecutionExperience, ...] = ()

    def append(self, experience: ExecutionExperience) -> None:
        with self._lock:
            self._held = self._held + (experience,)

    def all(self) -> tuple[ExecutionExperience, ...]:
        with self._lock:
            return self._held


class RetrievalPort(Protocol):
    """A retriever: structurally an ``eidos.knowledge.KnowledgePort`` (one synchronous, thread-safe, total ``retrieve``; see ``eidos.knowledge.retrieval``). It is declared here and not imported because the knowledge package
    is imported by three boundary modules only (its guard); this module only hands the object to the recording adapter, which is one of them."""

    def retrieve(self, request): ...


@dataclass(frozen=True, slots=True)
class KnowledgeProvision:
    """An optional knowledge base a deployer supplies: its descriptor and a retriever behind the knowledge port. The service makes no choice of knowledge base (D-234)."""

    descriptor: KnowledgeBaseDescriptor
    port: RetrievalPort


@dataclass(slots=True)
class PreparedRun:
    """What one run needs: the keyword arguments of ``run_with_replanning``, and the outbox and store the caller finishes and reads afterwards."""

    run_arguments: dict
    persistence: RunPersistence
    store: WriteThroughArtifactStore
    tracker: ModelCallTracker


class Composition:
    def __init__(
        self, *, config: ServiceConfig, model: ModelPort, events: EventStore, knowledge: KnowledgeProvision | None = None, clock: Clock | None = None, sleep=None
    ) -> None:
        self._config, self._model, self._events, self._knowledge = config, model, events, knowledge
        self._clock = clock if clock is not None else SystemClock()
        self._sleep = sleep
        self.registry = CapabilityRegistry(
            agents=(
                AgentDescriptor(agent_id=RESEARCH_AGENT_ID, version="1", capabilities=ResearchAgent.CAPABILITIES),
                AgentDescriptor(agent_id=ANALYSIS_AGENT_ID, version="1", capabilities=AnalysisAgent.CAPABILITIES),
            )
        )

    @property
    def capabilities(self) -> tuple[str, ...]:
        """The capabilities some agent here serves: what a mission may require."""
        return tuple(sorted({str(name) for agent in self.registry.agents for name in agent.capabilities}))

    def prepare(self, mission: MissionRecord, documents: Sequence[Artifact]) -> PreparedRun:
        config, clock = self._config, self._clock
        contract, genome = contract_and_genome(mission.spec, tenant_id=mission.tenant_id, contract_id=mission.contract_id)
        ids = UuidEventIds()
        carrier = initial_state(
            genome, contract, tenant_id=mission.tenant_id, mission_id=mission.mission_id, execution_id=mission.execution_id, at=clock.now(), event_id=ids.next_event_id()
        )
        persistence = RunPersistence(
            events=self._events, tenant_id=mission.tenant_id, mission_id=mission.mission_id, execution_id=mission.execution_id,
            attempts=config.runner.flush_attempts, backoff_seconds=config.runner.flush_backoff_seconds, **({} if self._sleep is None else {"sleep": self._sleep}),
        )
        store = WriteThroughArtifactStore(persistence)
        store.preload(mission.execution_id, tuple(documents))
        tracker = ModelCallTracker()
        knowledge = None
        if self._knowledge is not None:
            port = RecordingKnowledgePort(self._knowledge.port, tracker, clock)
            knowledge = KnowledgeGate(descriptor=self._knowledge.descriptor, port=port, ledger=EvidenceLedger(), store=store)
        model = RecordingModel(self._model, tracker)
        research = ResearchAgent(model=model, settings=config.model_settings, store=store, **({} if knowledge is None else {"knowledge": knowledge}))
        analysis = AnalysisAgent(model=model, settings=config.model_settings, store=store)
        agents = {
            RESEARCH_AGENT_ID: RecordingCitations(research, tracker, store),
            ANALYSIS_AGENT_ID: RecordingCitations(analysis, tracker, store),
        }
        run_arguments = dict(
            state=carrier, limits=config.limits, registry=self.registry, agents=agents, verifier=VerificationAgent(store=store),
            admission_guard_factory=AlwaysAdmit, executor_factory=SequentialExecutor, clock=clock, ids=ids,
            strategy_ids=UuidStrategyIds(), plan_ids=UuidPlanIds(), candidate_generator=RuleBasedCandidateGenerator(),
            max_candidates=config.max_candidates, selector=DeterministicSelector(), store=InMemoryExperienceStore(),
            log=DurableEventLog(persistence), tracker=tracker,
        )
        return PreparedRun(run_arguments=run_arguments, persistence=persistence, store=store, tracker=tracker)
