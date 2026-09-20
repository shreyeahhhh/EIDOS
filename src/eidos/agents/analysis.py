"""The Analysis Agent (decisions.md D-131, D-137, D-144, D-145, D-140).

Serves ``architecture``, ``security`` and ``cost``. It reads what its predecessors produced from the artifact store, and the
supplied documents, and asks the model for an analysis from the requested capability's point of view, citing every source as
``[[ref]]``. It is handed nothing else: the plan carries no per-step input (D-145).

A predecessor that produced no artifact cannot be analysed and is reported as a failure rather than skipped. At V0.4 an
analysis step's predecessors are therefore work steps.
"""

from dataclasses import dataclass

from eidos.capabilities import ARCHITECTURE, COST, SECURITY
from eidos.compiler import WorkNode
from eidos.runtime import ExecutionContext, WorkResult

from .artifacts import Artifact, ArtifactStore
from .base import ask_model, record_output, refuse_a_reused_step, render_artifacts
from .model import ModelPort, ModelResponse, ModelSettings

SYSTEM_PROMPT = (
    "You are an analysis agent. Use only the material provided. "
    "Cite every claim with the exact reference of its source, written as [[reference]]. "
    "If the material is not enough to support a conclusion, say so plainly."
)

FOCUS = (
    (ARCHITECTURE, "Analyse the architecture: components, dependencies, coupling and constraints."),
    (SECURITY, "Analyse the security position: exposure, data handling and risks."),
    (COST, "Analyse the cost: what it takes, what drives it and what is uncertain."),
)


@dataclass(frozen=True, slots=True, kw_only=True)
class AnalysisAgent:
    model: ModelPort
    settings: ModelSettings
    store: ArtifactStore

    CAPABILITIES = (ARCHITECTURE, SECURITY, COST)

    def run(self, context: ExecutionContext, node: WorkNode) -> WorkResult:
        focus = next((text for capability, text in FOCUS if capability == node.capability), None)
        if focus is None:
            return WorkResult.failed(f"the analysis agent does not serve capability {str(node.capability)!r}")

        refused = refuse_a_reused_step(self.store, context, node)  # D-147: before reading anything, and before any model call
        if refused is not None:
            return refused

        upstream: list[Artifact] = []
        for predecessor in node.predecessors:
            produced = self.store.get_step_artifact(context.execution_id, predecessor)
            if produced is None:
                return WorkResult.failed(f"predecessor {str(predecessor)!r} has no artifact to analyse")
            upstream.append(produced)
        supplied = self.store.supplied(context.execution_id)
        material = tuple(upstream) + supplied
        if not material:
            return WorkResult.no_result("there is no material to analyse: no predecessor artifact and no supplied document")

        prompt = (
            f"Mission goal: {context.task_genome.goal}\n\n"
            f"Material:\n\n{render_artifacts(material)}\n\n"
            f"Task: {focus} Write it in Markdown, citing each source."
        )
        answer = ask_model(self.model, self.settings, prompt, SYSTEM_PROMPT)
        if not isinstance(answer, ModelResponse):
            return answer
        return record_output(self.store, context, node, answer)
