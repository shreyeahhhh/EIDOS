"""Wrappers over the existing injection points: the model port, the work agents, the verifier and, from V1.2 Step 4, the tool gate
(decisions.md D-158 item 1, D-203) and, from V1.3 Step 4, a knowledge port (D-218, D-225).

Each wrapper does what it wraps and returns exactly what it returned. It **observes**: it changes no argument, no result and no exception, so a
recorded run's ``BaselineReport`` is the report an unrecorded run gives. Nothing here holds or writes a ``MissionState``.

A node's model calls are attributed to it without touching an agent: the agent wrapper opens a per-thread collector while the agent runs, and the
model wrapper, called synchronously on that same thread, adds to it. A call made outside any node is not attributed to anything.
The tool gate's wrapper does the same for tool calls: it adds one ``ToolCallFacts`` per call, denials and served duplicates included, to the node's collector.
The knowledge port's wrapper does the same for retrievals: it adds one ``RetrievalFacts`` per call. It wraps the port now; when a gate exists (V1.3 Step 7) the seam moves to the gate, as
it did for tools. A node's citations are what its artifact's ``source_refs`` say: a wrapper around the work agent that the caller composes with an artifact store reads them and adds them to
the node's collector, so nothing is read without one and no existing signature changes.

A node is settled **live**, the moment its work returns, so the log's chronology is the run's — started, then settled, node by node. The
``NodeResult`` recorded live is built by the same three-line mapping the runtime's executor applies to a port's result; the recorder later
checks it against the run's own result and reports any disagreement (``discrepancies``) instead of hiding it. If a port *raises*, the wrapper lets
the exception pass unchanged and records nothing live: the executor's own ``FAILED`` result is recorded after the run, together with what was
observed.
"""

import threading
from types import MappingProxyType

from eidos.agents import (
    ArtifactStore,
    ModelFailure,
    ModelPort,
    ModelRequest,
    ModelResponse,
    ModelResult,
    ToolAccess,
    ToolFailure,
    ToolGateKind,
    ToolGateOutcome,
    WorkAgent,
)
from eidos.compiler import VerifyNode, WorkNode
from eidos.contracts import AgentId, ArtifactRef, PlanStepKind
from eidos.knowledge import KnowledgePort, RetrievalFailure, RetrievalRequest, RetrievalResult, result_problem
from eidos.runtime import (
    ExecutionContext,
    NodeResult,
    NodeStatus,
    VerificationResult,
    VerificationVerdict,
    Verifier,
    WorkResult,
    WorkStatus,
)
from eidos.state import (
    ModelCallFacts,
    ModelCallOutcome,
    NodeStartedPayload,
    RetrievalFacts,
    RetrievalHitFacts,
    RetrievalOutcome,
    ToolCallFacts,
    ToolCallOutcome,
    ToolDenialReason,
    VerificationFacts,
)

from .ports import Clock
from .recorder import Recorder


class ModelCallTracker:
    """Collects, per thread, the model calls, the tool calls, the knowledge retrievals and the citations made while one node runs.

    The tool collection is the additive half (D-203, V1.2 Step 3): ``begin`` opens both, ``end`` closes the model calls exactly as it always
    did, and ``end_tool_calls`` closes the tool calls. Whatever makes a tool call adds its ``ToolCallFacts`` to ``current_tool_calls()`` on the
    thread that is running the node; a call made outside any node is attributed to nothing, as for a model call. Retrievals are the same again (D-218, V1.3 Step 4): ``begin`` opens
    the collector, ``current_retrievals`` is where a ``RetrievalFacts`` is added, and ``end_retrievals`` closes it; ``current_citations`` and ``end_citations`` do the same for the references a
    node's artifact cited. Nothing here makes a call.
    """

    def __init__(self) -> None:
        self._local = threading.local()

    def begin(self) -> None:
        self._local.calls = []
        self._local.tool_calls = []
        self._local.retrievals = []
        self._local.citations = []

    def current(self) -> list[ModelCallFacts] | None:
        return getattr(self._local, "calls", None)

    def end(self) -> tuple[ModelCallFacts, ...]:
        calls = getattr(self._local, "calls", None) or []
        self._local.calls = None
        return tuple(calls)

    def current_tool_calls(self) -> list[ToolCallFacts] | None:
        return getattr(self._local, "tool_calls", None)

    def end_tool_calls(self) -> tuple[ToolCallFacts, ...]:
        calls = getattr(self._local, "tool_calls", None) or []
        self._local.tool_calls = None
        return tuple(calls)

    def current_retrievals(self) -> list[RetrievalFacts] | None:
        return getattr(self._local, "retrievals", None)

    def end_retrievals(self) -> tuple[RetrievalFacts, ...]:
        retrievals = getattr(self._local, "retrievals", None) or []
        self._local.retrievals = None
        return tuple(retrievals)

    def current_citations(self) -> list[ArtifactRef] | None:
        return getattr(self._local, "citations", None)

    def end_citations(self) -> tuple[ArtifactRef, ...]:
        citations = getattr(self._local, "citations", None) or []
        self._local.citations = None
        return tuple(citations)


def facts_of(result: ModelResult) -> ModelCallFacts | None:
    """What one model call came to, in the recorded vocabulary. ``None`` for anything that is neither a response nor a typed failure."""
    if isinstance(result, ModelResponse):
        measured = result.measured
        return ModelCallFacts(
            outcome=ModelCallOutcome.RESPONSE,
            prompt_tokens=measured.prompt_tokens,
            output_tokens=measured.output_tokens,
            elapsed_seconds=measured.elapsed_seconds,
        )
    if isinstance(result, ModelFailure):
        return ModelCallFacts(outcome=ModelCallOutcome(result.kind.value))  # a failed call has no provider facts (D-150)
    return None


class RecordingModel:
    """A ``ModelPort`` that passes every call through and notes what it came to, for the node being run on this thread."""

    def __init__(self, inner: ModelPort, tracker: ModelCallTracker):
        self.inner, self.tracker = inner, tracker

    def complete(self, request: ModelRequest) -> ModelResult:
        result = self.inner.complete(request)  # an exception from the port passes through untouched, and records nothing
        collector = self.tracker.current()
        if collector is not None:
            facts = facts_of(result)
            if facts is not None:
                collector.append(facts)
        return result


def tool_facts_of(outcome: ToolGateOutcome, elapsed_ms: int | None) -> ToolCallFacts:
    """What one call to the tool gate came to, in the recorded vocabulary (D-203, D-206). ``elapsed_ms`` is what the recorder's clock measured
    around an invocation; a denial and a served duplicate reached no tool, so they carry none whatever is passed."""
    if outcome.kind is ToolGateKind.DENIED:
        return ToolCallFacts(tool_id=outcome.tool_id, outcome=ToolCallOutcome.DENIED, denial=ToolDenialReason(outcome.admission.denial.code.value))
    digest = outcome.admission.args_digest
    if outcome.kind is ToolGateKind.SERVED:
        return ToolCallFacts(
            tool_id=outcome.tool_id, outcome=ToolCallOutcome.SERVED_STORED, args_digest=digest, result_refs=outcome.refs,
            result_bytes=outcome.result.size_bytes,
        )
    result = outcome.result
    if isinstance(result, ToolFailure):
        return ToolCallFacts(tool_id=outcome.tool_id, outcome=ToolCallOutcome(result.kind.value), args_digest=digest, elapsed_ms=elapsed_ms)
    return ToolCallFacts(
        tool_id=outcome.tool_id, outcome=ToolCallOutcome.RESULT, args_digest=digest, result_refs=outcome.refs, result_bytes=result.size_bytes,
        elapsed_ms=elapsed_ms,
    )


class RecordingToolAccess:
    """A ``ToolAccess`` that passes every call through and notes what it came to, for the node being run on this thread (D-203, V1.2 Step 4).

    It returns exactly what it wrapped and changes no argument and no exception: an exception from the wrapped access passes through untouched and
    records nothing. The elapsed time of an invocation is the time between the two readings of the injected monotonic clock around the call, the
    same clock the recorder measures a node with, so it is an observed fact and never an estimate.
    """

    def __init__(self, inner: ToolAccess, tracker: ModelCallTracker, clock: Clock):
        self.inner, self.tracker, self.clock = inner, tracker, clock

    def call(self, context, tool_id, arguments) -> ToolGateOutcome:
        started = self.clock.monotonic_ns()
        outcome = self.inner.call(context, tool_id, arguments)
        elapsed_ms = max(0, (self.clock.monotonic_ns() - started) // 1_000_000)
        collector = self.tracker.current_tool_calls()
        if collector is not None:
            collector.append(tool_facts_of(outcome, elapsed_ms))
        return outcome


def retrieval_facts_of(request: RetrievalRequest, outcome: RetrievalResult | RetrievalFailure, elapsed_ms: int | None) -> RetrievalFacts:
    """What one call to a knowledge port came to, in the recorded vocabulary (D-218, D-225). The identity fields are what was asked. An answer that does not answer its request
    (``result_problem``), or is neither a result nor a failure, is recorded as ``malformed_result`` and carries nothing: it is never dropped and never trusted."""
    asked = dict(kb_id=request.kb_id, snapshot_id=request.snapshot_id, scheme_id=request.scheme_id, query_id=request.query_id, top_k=request.top_k)
    if isinstance(outcome, RetrievalFailure):
        return RetrievalFacts(**asked, outcome=RetrievalOutcome(outcome.kind.value), elapsed_ms=elapsed_ms)
    if not isinstance(outcome, RetrievalResult) or result_problem(request, outcome) is not None:
        return RetrievalFacts(**asked, outcome=RetrievalOutcome.MALFORMED_RESULT, elapsed_ms=elapsed_ms)
    hits = tuple(
        RetrievalHitFacts(
            rank=hit.rank,
            chunk_id=hit.chunk.chunk_id,
            document_id=hit.chunk.document_id,
            source_id=hit.chunk.source_id,
            content_digest=hit.content_digest,
            score=hit.score,
        )
        for hit in outcome.hits
    )
    return RetrievalFacts(**asked, outcome=RetrievalOutcome.RESULT, score_kind=outcome.score_kind, hits=hits, result_bytes=outcome.result_bytes, elapsed_ms=elapsed_ms)


class RecordingKnowledgePort:
    """A ``KnowledgePort`` that passes every call through and notes what it came to, for the node being run on this thread (D-218, V1.3 Step 4).

    It returns exactly what it wrapped and changes no argument and no exception: an exception from the wrapped port passes through untouched and records nothing. The elapsed time is
    the time between two readings of the injected monotonic clock around the call, the same clock the recorder measures a node with, so it is an observed fact and never an estimate.
    """

    def __init__(self, inner: KnowledgePort, tracker: ModelCallTracker, clock: Clock):
        self.inner, self.tracker, self.clock = inner, tracker, clock

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult | RetrievalFailure:
        started = self.clock.monotonic_ns()
        outcome = self.inner.retrieve(request)
        elapsed_ms = max(0, (self.clock.monotonic_ns() - started) // 1_000_000)
        collector = self.tracker.current_retrievals()
        if collector is not None:
            collector.append(retrieval_facts_of(request, outcome, elapsed_ms))
        return outcome


class RecordingCitations:
    """A ``WorkAgent`` that does exactly what the agent it wraps does, and then notes the references the artifact it produced cited (its ``source_refs``, verbatim), for the node being run on
    this thread (D-218, V1.3 Step 4). It reads the artifact store and writes nothing; it changes no result and no exception, and a node that produced no artifact, or one that cited nothing,
    adds nothing. It is composed inside ``RecordingAgent``, which hands the collected references to the recorder."""

    def __init__(self, inner: WorkAgent, tracker: ModelCallTracker, artifacts: ArtifactStore):
        self.inner, self.tracker, self.artifacts = inner, tracker, artifacts

    def run(self, context: ExecutionContext, node: WorkNode) -> WorkResult:
        result = self.inner.run(context, node)  # an exception passes through untouched, and records nothing
        collector = self.tracker.current_citations()
        if collector is not None and isinstance(result, WorkResult) and result.artifact is not None:  # only a produced result names an artifact
            artifact = self.artifacts.get(context.execution_id, result.artifact)
            if artifact is not None:
                collector.extend(artifact.source_refs)
        return result


def node_result_of_work(node: WorkNode, result: WorkResult) -> NodeResult:
    """The runtime's mapping of a work port's result to a node's, restated. The recorder checks it against the run's own result."""
    if result.status is WorkStatus.PRODUCED:
        return NodeResult(step_id=node.step_id, kind=node.kind, status=NodeStatus.SUCCEEDED, artifact=result.artifact)
    status = NodeStatus.FAILED if result.status is WorkStatus.FAILED else NodeStatus.NO_RESULT
    return NodeResult(step_id=node.step_id, kind=node.kind, status=status, reason=result.reason)


_VERDICT_STATUS = MappingProxyType({
    VerificationVerdict.PASS: NodeStatus.SUCCEEDED,
    VerificationVerdict.FAIL: NodeStatus.VERIFICATION_FAILED,
    VerificationVerdict.INCONCLUSIVE: NodeStatus.VERIFICATION_INCONCLUSIVE,
})


def node_result_of_verification(node: VerifyNode, result: VerificationResult) -> NodeResult:
    return NodeResult(step_id=node.step_id, kind=node.kind, status=_VERDICT_STATUS[result.verdict], reason=result.reason)


class RecordingAgent:
    """A ``WorkAgent`` that records the node starting, runs the agent it wraps, and records the node settling."""

    def __init__(self, agent_id: AgentId, agent: WorkAgent, recorder: Recorder, tracker: ModelCallTracker):
        self.agent_id, self.agent, self.recorder, self.tracker = agent_id, agent, recorder, tracker

    def run(self, context: ExecutionContext, node: WorkNode) -> WorkResult:
        self.recorder.record(
            NodeStartedPayload(
                plan_id=context.plan_id, step_id=node.step_id, kind=PlanStepKind.AGENT, capability=node.capability, agent_id=self.agent_id
            )
        )
        self.tracker.begin()
        started = self.recorder.monotonic_ns()
        try:
            result = self.agent.run(context, node)
        except BaseException:
            self._note_tool_calls(node)
            self._note_retrievals(node)
            self._note_citations(node)
            self.recorder.note_observation(node.step_id, self.recorder.duration_ms(started), self.tracker.end())
            raise
        duration_ms, calls = self.recorder.duration_ms(started), self.tracker.end()
        self._note_tool_calls(node)
        self._note_retrievals(node)
        self._note_citations(node)
        self.recorder.note_observation(node.step_id, duration_ms, calls)
        if isinstance(result, WorkResult):
            self.recorder.settle_live(context.plan_id, node_result_of_work(node, result), duration_ms, calls, None)
        return result

    def _note_tool_calls(self, node: WorkNode) -> None:
        """Hand the node's tool calls to the recorder, before it settles the node; a node that made none says nothing, so a run without tools
        makes exactly the recorder calls it always made."""
        tool_calls = self.tracker.end_tool_calls()
        if tool_calls:
            self.recorder.note_tool_calls(node.step_id, tool_calls)

    def _note_retrievals(self, node: WorkNode) -> None:
        """The same for the node's knowledge retrievals (D-218): a node that made none says nothing."""
        retrievals = self.tracker.end_retrievals()
        if retrievals:
            self.recorder.note_retrievals(node.step_id, retrievals)

    def _note_citations(self, node: WorkNode) -> None:
        """The references the node's artifact cited, as ``RecordingCitations`` collected them (D-218): a node that cited nothing says nothing."""
        citations = self.tracker.end_citations()
        if citations:
            self.recorder.note_citations(node.step_id, citations)


class RecordingVerifier:
    """A ``Verifier`` that records the ``VERIFY`` node starting and settling, with the verdict and its reason as the verifier returned them."""

    def __init__(self, verifier: Verifier, recorder: Recorder):
        self.verifier, self.recorder = verifier, recorder

    def verify(self, context: ExecutionContext, node: VerifyNode, predecessors: tuple[NodeResult, ...]) -> VerificationResult:
        self.recorder.record(NodeStartedPayload(plan_id=context.plan_id, step_id=node.step_id, kind=PlanStepKind.VERIFY))
        started = self.recorder.monotonic_ns()
        try:
            result = self.verifier.verify(context, node, predecessors)
        except BaseException:
            self.recorder.note_observation(node.step_id, self.recorder.duration_ms(started), ())
            raise
        duration_ms = self.recorder.duration_ms(started)
        self.recorder.note_observation(node.step_id, duration_ms, ())
        if isinstance(result, VerificationResult):
            self.recorder.settle_live(
                context.plan_id,
                node_result_of_verification(node, result),
                duration_ms,
                (),
                VerificationFacts(verdict=result.verdict, reason=result.reason),
            )
        return result
