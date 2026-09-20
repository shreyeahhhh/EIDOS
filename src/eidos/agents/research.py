"""The Research Agent (decisions.md D-131, D-137, D-144, D-145, D-140).

Serves ``research``. It works only from the documents the caller supplied to the artifact store — no file access, no
tools and no retrieval (those arrive at later milestones) — and asks the model to extract what is relevant to the mission goal, citing each
supplied document as ``[[ref]]``. With nothing supplied there is nothing to research, and it says so rather than asking a model to
answer from memory.
"""

from dataclasses import dataclass

from eidos.capabilities import RESEARCH
from eidos.compiler import WorkNode
from eidos.runtime import ExecutionContext, WorkResult

from .artifacts import ArtifactStore
from .base import ask_model, record_output, refuse_a_reused_step, render_artifacts
from .model import ModelPort, ModelResponse, ModelSettings

SYSTEM_PROMPT = (
    "You are a research agent. Use only the documents provided. "
    "Cite every claim with the exact reference of its source, written as [[reference]]. "
    "If the documents do not answer the goal, say so plainly."
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ResearchAgent:
    model: ModelPort
    settings: ModelSettings
    store: ArtifactStore

    CAPABILITIES = (RESEARCH,)

    def run(self, context: ExecutionContext, node: WorkNode) -> WorkResult:
        if node.capability not in self.CAPABILITIES:
            return WorkResult.failed(f"the research agent does not serve capability {str(node.capability)!r}")
        refused = refuse_a_reused_step(self.store, context, node)  # D-147: before anything else, and before any model call
        if refused is not None:
            return refused
        documents = self.store.supplied(context.execution_id)
        if not documents:
            return WorkResult.no_result("no documents were supplied, so there is nothing to research")
        prompt = (
            f"Mission goal: {context.task_genome.goal}\n\n"
            f"Documents:\n\n{render_artifacts(documents)}\n\n"
            "Task: extract the findings that bear on the goal, in Markdown, citing each source."
        )
        answer = ask_model(self.model, self.settings, prompt, SYSTEM_PROMPT)
        if not isinstance(answer, ModelResponse):
            return answer
        return record_output(self.store, context, node, answer)

