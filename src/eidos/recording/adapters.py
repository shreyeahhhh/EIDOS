"""Wrappers over the existing injection points: the model port, the work agents, the verifier and, from V1.2 Step 4, the tool gate
(decisions.md D-158 item 1, D-203).

Each wrapper does what it wraps and returns exactly what it returned. It **observes**: it changes no argument, no result and no exception, so a
recorded run's ``BaselineReport`` is the report an unrecorded run gives. Nothing here holds or writes a ``MissionState``.

A node's model calls are attributed to it without touching an agent: the agent wrapper opens a per-thread collector while the agent runs, and the
model wrapper, called synchronously on that same thread, adds to it. A call made outside any node is not attributed to anything.
The tool gate's wrapper does the same for tool calls: it adds one ``ToolCallFacts`` per call, denials and served duplicates included, to the node's collector.

A node is settled **live**, the moment its work returns, so the log's chronology is the run's — started, then settled, node by node. The
``NodeResult`` recorded live is built by the same three-line mapping the runtime's executor applies to a port's result; the recorder later
checks it against the run's own result and reports any disagreement (``discrepancies``) instead of hiding it. If a port *raises*, the wrapper lets
the exception pass unchanged and records nothing live: the executor's own ``FAILED`` result is recorded after the run, together with what was
observed.
"""

import threading
from types import MappingProxyType

from eidos.agents import (
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
from eidos.contracts import AgentId, PlanStepKind
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
    ToolCallFacts,
    ToolCallOutcome,
    ToolDenialReason,
    VerificationFacts,
)

from .ports import Clock
from .recorder import Recorder


class ModelCallTracker:
    """Collects, per thread, the model calls and the tool calls made while one node runs.

    The tool collection is the additive half (D-203, V1.2 Step 3): ``begin`` opens both, ``end`` closes the model calls exactly as it always
    did, and ``end_tool_calls`` closes the tool calls. Whatever makes a tool call adds its ``ToolCallFacts`` to ``current_tool_calls()`` on the
    thread that is running the node; a call made outside any node is attributed to nothing, as for a model call. Nothing here makes a call.
    """

    def __init__(self) -> None:
        self._local = threading.local()

    def begin(self) -> None:
        self._local.calls = []
        self._local.tool_calls = []

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
            self.recorder.note_observation(node.step_id, self.recorder.duration_ms(started), self.tracker.end())
            raise
        duration_ms, calls = self.recorder.duration_ms(started), self.tracker.end()
        self._note_tool_calls(node)
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
