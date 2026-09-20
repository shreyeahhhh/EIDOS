"""What an agent is, and the pieces the work agents share (decisions.md D-135, D-137, D-140, D-145).

A ``WorkAgent`` performs one work node: it is handed the frozen ``ExecutionContext`` and the compiled ``WorkNode``
(D-122's ``WorkExecutor`` shape, unchanged) and returns a ``WorkResult``. It reads the mission goal from the context and its
inputs from the artifact store, asks a model through ``ModelPort``, and writes exactly one primary artifact. It takes no
action and has no tools (D-140).

Citations. An agent asks the model to cite a source as ``[[ref]]``, where ``ref`` is the exact reference shown in the
prompt. The agent then records **what the model cited** as the artifact's ``source_refs``. Whether those references are real
is not decided here: the verification rules check that each one resolves (D-146).

Nothing here parses a model's output into anything executable (invariant 3): the output is text, stored as text.
"""

import re
from typing import Protocol

from eidos.compiler import WorkNode
from eidos.contracts import ArtifactRef, StepId
from eidos.runtime import ExecutionContext, WorkResult

from .artifacts import Artifact, ArtifactConflict, ArtifactStore
from .model import ModelFailure, ModelFailureKind, ModelPort, ModelRequest, ModelResponse, ModelSettings

CONTENT_TYPE_MARKDOWN = "text/markdown"
CONTENT_TYPE_PLAIN = "text/plain"
SUPPORTED_CONTENT_TYPES: tuple[str, ...] = (CONTENT_TYPE_MARKDOWN, CONTENT_TYPE_PLAIN)

_CITATION = re.compile(r"\[\[([^\[\]\n]+)\]\]")


class WorkAgent(Protocol):
    """Performs one work node. Thread-safe: a level's nodes run on worker threads."""

    def run(self, context: ExecutionContext, node: WorkNode) -> WorkResult: ...


def artifact_ref_for(step_id: StepId) -> ArtifactRef:
    """The reference a step's primary artifact is given: deterministic, and unique within an execution."""
    return ArtifactRef(f"artifact:{step_id}")


def cited_refs(text: str) -> tuple[ArtifactRef, ...]:
    """Every distinct ``[[ref]]`` a text cites, in order of first appearance."""
    seen: dict[ArtifactRef, None] = {}
    for match in _CITATION.finditer(text):
        ref = ArtifactRef(match.group(1).strip())
        if ref:
            seen.setdefault(ref, None)
    return tuple(seen)


def render_artifacts(artifacts: tuple[Artifact, ...]) -> str:
    """The artifacts as a prompt section, each headed by the exact reference the model must cite."""
    return "\n\n".join(f"[[{artifact.ref}]] ({artifact.content_type})\n{artifact.content}" for artifact in artifacts)


def ask_model(model: ModelPort, settings: ModelSettings, prompt: str, system: str) -> ModelResponse | WorkResult:
    """Call the model. A usable response comes back as itself; a failure comes back as the ``WorkResult`` it means."""
    result = model.complete(ModelRequest(settings=settings, prompt=prompt, system=system))
    if isinstance(result, ModelResponse):
        return result
    assert isinstance(result, ModelFailure), type(result)
    reason = f"the model call failed ({result.kind.value}): {result.message}"
    if result.kind in (ModelFailureKind.TIMEOUT, ModelFailureKind.UNAVAILABLE):
        return WorkResult.failed(reason)  # the work itself did not complete
    return WorkResult.no_result(reason)  # it completed, and produced nothing usable


def record_output(
    store: ArtifactStore, context: ExecutionContext, node: WorkNode, response: ModelResponse
) -> WorkResult:
    """Store the model's text as this step's one primary artifact and name it in the result."""
    ref = artifact_ref_for(node.step_id)
    artifact = Artifact(
        ref=ref,
        content_type=CONTENT_TYPE_MARKDOWN,
        content=response.text,
        source_refs=tuple(cited for cited in cited_refs(response.text) if cited != ref),
    )
    try:
        store.put_step_artifact(context.execution_id, node.step_id, artifact)
    except ArtifactConflict as error:
        return WorkResult.failed(f"the output could not be recorded: {error}")
    return WorkResult.produced(ref)
