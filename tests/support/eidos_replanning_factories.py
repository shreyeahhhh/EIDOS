"""Test-support fixtures for ``eidos.replanning`` (decisions.md D-199; V1.1 Step 4).

Mirrors ``eidos_benchmark_harness.py``'s own discipline: real V0.4 agents over a scripted model (D-136), never a
mock of the orchestration itself. Nothing here reaches a real model, the wall clock or a random source beyond
the deliberately real ``UuidStrategyIds``/``UuidPlanIds``/``UuidEventIds`` (D-182: a replan's own candidates and
plans must draw genuinely fresh identity, exactly like every other V1.0/V1.1 caller).
"""

from eidos.agents import (
    AnalysisAgent,
    InMemoryArtifactStore,
    MeasuredFacts,
    ModelFailure,
    ModelFailureKind,
    ModelResponse,
    ResearchAgent,
    VerificationAgent,
)
from eidos.planning import RuleBasedCandidateGenerator
from eidos.recording import UuidEventIds, UuidPlanIds, UuidStrategyIds
from eidos.replanning import ReplanRun, run_with_replanning
from eidos.runtime import SequentialExecutor, VerificationResult

from eidos_agents_factories import doc, make_settings
from eidos_planning_factories import GENEROUS_LIMITS
from eidos_recording_factories import FixedClock
from eidos_runtime_factories import admit_all
from eidos_v04_registry import ANALYSIS_AGENT_ID, RESEARCH_AGENT_ID, make_registry


class ScriptedPort:
    """A minimal ``ModelPort`` over a plain callable — mirrors ``eidos_benchmark_harness.ScriptedPort`` exactly,
    reused rather than duplicated where the two test-support modules could share (kept separate, unlike ``eidos``
    itself, since ``tests/support`` has no import-boundary discipline forcing a shared home)."""

    def __init__(self, respond):
        self._respond = respond

    def complete(self, request):
        return self._respond(request)


def uniformly_sufficient(request):
    """Every capability cites all three supplied documents — sufficient for min_independent_evidence=3
    regardless of which stage VERIFY ends up seeing. Never fails on its own."""
    text = "Findings [[doc:1]] [[doc:2]] [[doc:3]]." if "Documents:" in request.prompt else "Analysis [[doc:1]] [[doc:2]] [[doc:3]]."
    return ModelResponse(text=text, measured=MeasuredFacts(prompt_tokens=100, output_tokens=200, elapsed_seconds=0.5))


def under_cited(request):
    """One citation only — insufficient for min_independent_evidence=3, whatever capability is asked. Every
    attempt using this response fails verification (never a HALT, never a rejection)."""
    text = "Findings [[doc:1]]." if "Documents:" in request.prompt else "Analysis [[doc:1]]."
    return ModelResponse(text=text, measured=MeasuredFacts(prompt_tokens=100, output_tokens=40, elapsed_seconds=0.2))


def always_fails(request):
    return ModelFailure(kind=ModelFailureKind.UNAVAILABLE, message="injected outage")


def empty_response(request):
    return ModelFailure(kind=ModelFailureKind.EMPTY_RESPONSE, message="injected empty response")


class ScriptedCalls:
    """A response callable answering its first calls from ``first`` (one responder per call, in call order,
    across every capability and every attempt — a single shared counter) and every later call from ``then``.
    ``calls`` counts every call made, so a test can prove a replanned attempt really reached the model.

    The one mechanism that makes an *eligible* outcome land on the candidate ``DeterministicSelector``'s own
    structural bias would otherwise always pick first, without depending on topology (an admission-guard halt is
    never replan-eligible, D-199) or on citation content alone (a parallel shape's own VERIFY always sees at
    least as much evidence as a linear shape's narrower final-stage view, so citation content alone can never
    make parallel fail while linear succeeds — found by direct inspection, not assumed)."""

    def __init__(self, first, *, then=uniformly_sufficient):
        self._first = tuple(first)
        self._then = then
        self.calls = 0

    def __call__(self, request):
        self.calls += 1
        responder = self._first[self.calls - 1] if self.calls <= len(self._first) else self._then
        return responder(request)


def fail_first_n_calls(n: int, *, then=uniformly_sufficient):
    """The first ``n`` calls each fail as an unavailable provider (``EXECUTION_FAILED``); every later call succeeds."""
    return ScriptedCalls((always_fails,) * n, then=then)


def under_cited_first_n_calls(n: int, *, then=uniformly_sufficient):
    """The first ``n`` calls each produce a usable artifact citing too little evidence: every work step
    succeeds and stores its artifact, and only ``VERIFY`` fails (``VERIFICATION_FAILED``)."""
    return ScriptedCalls((under_cited,) * n, then=then)


class InconclusiveOnFirstVerify:
    """Wraps the real ``VerificationAgent``: its first ``VERIFY`` is inconclusive, every later one is the real verdict."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = 0

    def verify(self, context, node, predecessors):
        self.calls += 1
        if self.calls == 1:
            return VerificationResult.inconclusive("test: the first verification could not establish success")
        return self._inner.verify(context, node, predecessors)


def three_docs():
    return tuple(doc(f"doc:{n}", f"Source document {n}.") for n in (1, 2, 3))


def build_agents(state, respond):
    store = InMemoryArtifactStore()
    for document in three_docs():
        store.put_supplied(state.execution_id, document)
    settings = make_settings()
    model = ScriptedPort(respond)
    agents = {
        RESEARCH_AGENT_ID: ResearchAgent(model=model, settings=settings, store=store),
        ANALYSIS_AGENT_ID: AnalysisAgent(model=model, settings=settings, store=store),
    }
    return agents, VerificationAgent(store=store)


def replan_outcome(
    state, *, selector, store, respond=uniformly_sufficient, admission_guard_factory=admit_all,
    max_candidates=3, candidate_generator=None, limits=None, verifier_wrapper=None, log=None,
):
    """One full ``run_with_replanning`` call, returning exactly what it returned (a ``ReplanRun`` or a
    ``ReplanRejection``), with every piece of boilerplate a test does not care about supplied by default — real
    registry, real V0.4 agents over a scripted model, real fresh id sources, a deterministic clock. Only
    ``selector``/``store`` are required: everything else is the thing under test. ``verifier_wrapper``, if
    given, wraps the real ``VerificationAgent`` (never replaces it)."""
    agents, verifier = build_agents(state, respond)
    if verifier_wrapper is not None:
        verifier = verifier_wrapper(verifier)
    return run_with_replanning(
        state=state, limits=limits or GENEROUS_LIMITS, registry=make_registry(), agents=agents, verifier=verifier,
        admission_guard_factory=admission_guard_factory, executor_factory=SequentialExecutor,
        clock=FixedClock(), ids=UuidEventIds(), strategy_ids=UuidStrategyIds(), plan_ids=UuidPlanIds(),
        candidate_generator=candidate_generator or RuleBasedCandidateGenerator(), max_candidates=max_candidates,
        selector=selector, store=store, log=log,
    )


def replan(state, **kwargs):
    """``replan_outcome`` for a mission that is expected to run: fails loudly if it was refused instead."""
    outcome = replan_outcome(state, **kwargs)
    assert isinstance(outcome, ReplanRun), outcome
    return outcome
