"""Test-support fixtures for tool-call facts (decisions.md D-203; V1.2 Step 3).

Builders for one ``ToolCallFacts`` of each kind, a helper that settles a node with tool calls in a hand-built log, and a work agent that adds tool
facts through the tracker the way a recording tool port will. Nothing here invokes a tool, reads a clock or touches the file system: a fact built
here is a fixed test value, never a measurement.
"""

from collections.abc import Mapping

from eidos.contracts import ArtifactRef
from eidos.state import NodeSettledPayload, ToolCallFacts, ToolCallOutcome, ToolDenialReason

TOOL_ID = "docs/search_documents"


def digest(number: int = 1) -> str:
    """A well-formed request digest (64 lowercase hex characters), distinct for each ``number``."""
    return f"{number:064x}"


def artifact_refs(number: int, documents: int) -> tuple[ArtifactRef, ...]:
    return tuple(ArtifactRef(f"artifact:tool-doc:{number}:{n}") for n in range(documents))


def result_call(*, number: int = 1, documents: int = 2, result_bytes: int | None = 512, elapsed_ms: int | None = 40, tool_id: str = TOOL_ID) -> ToolCallFacts:
    return ToolCallFacts(
        tool_id=tool_id, outcome=ToolCallOutcome.RESULT, args_digest=digest(number), result_refs=artifact_refs(number, documents),
        result_bytes=result_bytes, elapsed_ms=elapsed_ms,
    )


def failed_call(outcome: ToolCallOutcome = ToolCallOutcome.TIMEOUT, *, number: int = 1, elapsed_ms: int | None = 5000, tool_id: str = TOOL_ID) -> ToolCallFacts:
    return ToolCallFacts(tool_id=tool_id, outcome=outcome, args_digest=digest(number), elapsed_ms=elapsed_ms)


def served_call(*, number: int = 1, documents: int = 2, result_bytes: int | None = 512, tool_id: str = TOOL_ID) -> ToolCallFacts:
    """A duplicate of ``result_call(number=number, ...)``, answered from the stored result: the same digest and the same references, nothing invoked."""
    return ToolCallFacts(
        tool_id=tool_id, outcome=ToolCallOutcome.SERVED_STORED, args_digest=digest(number), result_refs=artifact_refs(number, documents),
        result_bytes=result_bytes,
    )


def denied_call(reason: ToolDenialReason = ToolDenialReason.BUDGET_EXHAUSTED, *, tool_id: str = TOOL_ID) -> ToolCallFacts:
    return ToolCallFacts(tool_id=tool_id, outcome=ToolCallOutcome.DENIED, denial=reason)


INVOCATIONS = (
    result_call(number=1),
    failed_call(ToolCallOutcome.TIMEOUT, number=2),
    failed_call(ToolCallOutcome.UNAVAILABLE, number=3, elapsed_ms=None),
    failed_call(ToolCallOutcome.TOOL_ERROR, number=4),
    failed_call(ToolCallOutcome.MALFORMED_RESULT, number=5),
    failed_call(ToolCallOutcome.RESULT_TOO_LARGE, number=6),
)
NOT_INVOCATIONS = (served_call(number=1), denied_call(ToolDenialReason.BUDGET_EXHAUSTED), denied_call(ToolDenialReason.BUDGET_UNRESOLVED))


def settle_with_tools(log, result, tool_calls, *, dispatched: bool = True, duration_ms: int | None = 1000, model_calls=(), verification=None):
    """Settle ``result`` in a hand-built ``LogBuilder`` log, carrying ``tool_calls``, without touching the shared builder."""
    return log.add(NodeSettledPayload(
        plan_id=log.plan.plan_id, result=result, dispatched=dispatched, duration_ms=duration_ms if dispatched else None,
        model_calls=tuple(model_calls), tool_calls=tuple(tool_calls), verification=verification,
    ))


class ToolFactsInjector:
    """A work agent that does exactly what the agent it wraps does, and adds ``ToolCallFacts`` to the node it is running through the tracker, the
    way a recording tool port will. It makes no tool call: the facts are handed to it. ``raise_after`` makes it raise once they are added."""

    def __init__(self, inner, tracker, facts_by_step: Mapping[str, tuple[ToolCallFacts, ...]], *, raise_after: BaseException | None = None):
        self.inner, self.tracker, self.facts_by_step, self.raise_after = inner, tracker, facts_by_step, raise_after

    def run(self, context, node):
        collector = self.tracker.current_tool_calls()
        if collector is not None:
            collector.extend(self.facts_by_step.get(str(node.step_id), ()))
        if self.raise_after is not None:
            raise self.raise_after
        return self.inner.run(context, node)
