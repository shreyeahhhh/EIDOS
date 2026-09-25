"""The Research Agent (decisions.md D-131, D-137, D-144, D-145, D-140, D-203, D-207).

Serves ``research``. It works from the documents in the artifact store — the ones the caller supplied and, when it was given tool access, the ones a
tool retrieved for it — and asks the model to extract what is relevant to the mission goal, citing each document as ``[[ref]]``. With nothing to work
from there is nothing to research, and it says so rather than asking a model to answer from memory.

**Tool access is optional and is not the agent's business how it is provided (V1.2 Step 4).** An agent built without it behaves exactly as it always
did. An agent built with a ``ToolAccess`` and a tool id asks that one tool, once per run, for documents matching the mission goal: the query is the
goal itself, verbatim, so no limit is invented here (the allowlist entry's own argument bounds decide whether the goal is an acceptable query).
Everything else is the gate's: admission, the budget, duplicates, the port, and turning what came back into artifacts in the store. Research imports
no transport and cannot tell a scripted provider from a real one. A denied, failed or empty answer never stops the run by itself: if documents exist
(supplied, or retrieved earlier in the execution) the agent works from them; if none exist it reports why, typed, and stops.
"""

from dataclasses import dataclass

from eidos.capabilities import RESEARCH
from eidos.compiler import WorkNode
from eidos.runtime import ExecutionContext, WorkResult

from .artifacts import ArtifactStore
from .base import ask_model, record_output, refuse_a_reused_step, render_artifacts
from .model import ModelPort, ModelResponse, ModelSettings
from .tool import ToolFailure, ToolFailureKind
from .tool_gate import ToolAccess, ToolGateKind, ToolGateOutcome

SYSTEM_PROMPT = (
    "You are a research agent. Use only the documents provided. "
    "Cite every claim with the exact reference of its source, written as [[reference]]. "
    "If the documents do not answer the goal, say so plainly."
)

_TOOL_FAILURES_THAT_MEAN_THE_WORK_DID_NOT_COMPLETE = (ToolFailureKind.UNAVAILABLE, ToolFailureKind.TIMEOUT, ToolFailureKind.TOOL_ERROR)


def _nothing_to_research(outcome: ToolGateOutcome | None) -> WorkResult:
    """Why there is no document to work from, typed as the work result it means (mirroring how a model failure is read)."""
    if outcome is None:
        return WorkResult.no_result("no documents were supplied, so there is nothing to research")
    lead = "no documents were supplied and "
    if outcome.kind is ToolGateKind.DENIED:
        denial = outcome.admission.denial
        return WorkResult.no_result(lead + f"the tool call was denied ({denial.code.value}): {denial.message}")
    if isinstance(outcome.result, ToolFailure):
        reason = lead + f"the tool failed ({outcome.result.kind.value}): {outcome.result.message}"
        if outcome.result.kind in _TOOL_FAILURES_THAT_MEAN_THE_WORK_DID_NOT_COMPLETE:
            return WorkResult.failed(reason)  # the retrieval itself did not complete
        return WorkResult.no_result(reason)  # it completed, and produced nothing usable
    return WorkResult.no_result(lead + "the tool found no documents")


@dataclass(frozen=True, slots=True, kw_only=True)
class ResearchAgent:
    model: ModelPort
    settings: ModelSettings
    store: ArtifactStore
    tools: ToolAccess | None = None
    search_tool_id: str | None = None

    CAPABILITIES = (RESEARCH,)

    def __post_init__(self) -> None:
        if (self.tools is None) != (self.search_tool_id is None):
            raise ValueError("tool access and the id of the tool to search with are given together or not at all")

    def run(self, context: ExecutionContext, node: WorkNode) -> WorkResult:
        if node.capability not in self.CAPABILITIES:
            return WorkResult.failed(f"the research agent does not serve capability {str(node.capability)!r}")
        refused = refuse_a_reused_step(self.store, context, node)  # D-147: before anything else, and before any model call
        if refused is not None:
            return refused
        outcome = None
        if self.tools is not None:
            query = context.task_genome.goal.strip()
            if query:
                outcome = self.tools.call(context, self.search_tool_id, {"query": query})
        documents = self.store.supplied(context.execution_id)
        if not documents:
            return _nothing_to_research(outcome)
        prompt = (
            f"Mission goal: {context.task_genome.goal}\n\n"
            f"Documents:\n\n{render_artifacts(documents)}\n\n"
            "Task: extract the findings that bear on the goal, in Markdown, citing each source."
        )
        answer = ask_model(self.model, self.settings, prompt, SYSTEM_PROMPT)
        if not isinstance(answer, ModelResponse):
            return answer
        return record_output(self.store, context, node, answer)
