"""What an agent is, and the pieces the work agents share (decisions.md D-135, D-137, D-140, D-145).

A ``WorkAgent`` performs one work node: it is handed the frozen ``ExecutionContext`` and the compiled ``WorkNode``
(D-122's ``WorkExecutor`` shape, unchanged) and returns a ``WorkResult``. It reads the mission goal from the context and its
inputs from the artifact store, asks a model through ``ModelPort``, and writes exactly one primary artifact. It takes no
action of its own (D-140). The only way an agent reaches a tool is the Research agent's optional, admission-gated ``ToolAccess`` (V1.2, D-203,
D-207); no agent holds a tool port.

Citations. An agent asks the model to cite a source as ``[[ref]]``, where ``ref`` is the exact reference shown in the
prompt. The agent then records **what the model cited** as the artifact's ``source_refs``. Whether those references are real
is not decided here: the verification rules check that each one resolves (D-146).

Fresh step ids (D-147). A step's artifact is ``(execution_id, step_id)`` and ``artifact:<step_id>``, and the store is write-once, so within one
execution a newly executed work step needs a step id no earlier-executed step used, across plan versions. ``refuse_a_reused_step`` enforces that
**before any model call**: an agent that finds the step's artifact already present refuses with a ``FAILED`` result and spends nothing. A resumed run
never trips it: a step with a prior ``SUCCEEDED`` outcome is not dispatched, and a step that failed or produced nothing wrote no artifact.

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

# The stable marker a refusal under D-147 begins with. A work result carries only a status and a reason, so this is the typed failure's name.
STEP_ID_REUSED = "step_id_reused"

_CITATION = re.compile(r"\[\[([^\[\]\n]+)\]\]")


class WorkAgent(Protocol):
    """Performs one work node. Thread-safe: a level's nodes run on worker threads."""

    def run(self, context: ExecutionContext, node: WorkNode) -> WorkResult: ...


def artifact_ref_for(step_id: StepId) -> ArtifactRef:
    """The reference a step's primary artifact is given: deterministic, and unique within an execution."""
    return ArtifactRef(f"artifact:{step_id}")


def refuse_a_reused_step(store: ArtifactStore, context: ExecutionContext, node: WorkNode) -> WorkResult | None:
    """``None`` if the step may run; otherwise the ``FAILED`` result that refuses it (D-147), decided **before** any model call.

    The step is refused when the store already holds its artifact under ``(execution_id, step_id)``, or when the reference ``artifact:<step_id>`` is
    already taken in this execution (for example by a supplied document). The write-once store remains the backstop for a race between this check
    and the write.
    """
    ref = artifact_ref_for(node.step_id)
    if store.get_step_artifact(context.execution_id, node.step_id) is None and store.get(context.execution_id, ref) is None:
        return None
    return WorkResult.failed(
        f"{STEP_ID_REUSED}: step {str(node.step_id)!r} already has an artifact ({str(ref)!r}) in this execution; a newly executed work step "
        "must use a fresh step id across plan versions (D-147). No model call was made."
    )


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
