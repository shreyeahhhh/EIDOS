"""The first remote-backed ``WorkAgent`` (decisions.md D-165, D-175; V0.6 Step 5 item 2): dispatches one work node
to a remote A2A system instead of asking a local model.

Bound to exactly one capability at construction (D-175: Research only, in practice — nothing here hardcodes that
name, so the class itself stays capability-agnostic, the same way ``ResearchAgent`` names its own capability rather
than the runtime knowing it, invariant 11). It reuses the same pre-flight and prompt-shaping helpers a local work
agent already has (``refuse_a_reused_step`` — D-147, before anything else; ``render_artifacts`` — the documents, not
a local system prompt: a remote agent is an *independent* system with its own behaviour, so EIDOS sends it the goal
and the documents and nothing dictating how it should answer) — never ``ModelPort``/``ask_model``, since there is no
local model call at all.

``run()`` makes exactly one A2A call and returns **immediately after it**, never waiting for the remote task to
conclude (D-165 rule 5): a successful submission is always ``WorkResult.submitted(...)``, whatever the immediate
response's task state actually was (D-165 rule 5's own wording: the call is *only* about obtaining the task id).
A submission failure of any kind is ``WorkResult.failed(...)`` — the work never started, the same bucket
``ask_model`` already uses for a model call that timed out or could not be reached.

**The one channel beyond ``WorkResult`` (D-165 rule 1 forbids a correlation handle there):** after a successful
submission, ``submitted_task(step_id)`` answers with the ``a2a_task_id``/``a2a_context_id`` a caller needs to build
``A2A_TASK_STARTED`` (D-174) — the same role ``eidos.recording.adapters.ModelCallTracker`` plays for model-call
facts, scoped to this one class rather than a separate injectable, since there is exactly one thing here to track.
Thread-safe (``WorkAgent``'s own contract: a level's nodes run on worker threads), keyed by ``step_id``.
"""

import threading
import uuid
from typing import Mapping

from eidos.agents import ArtifactStore, refuse_a_reused_step
from eidos.agents.base import render_artifacts
from eidos.compiler import WorkNode
from eidos.contracts import CapabilityId, StepId
from eidos.runtime import ExecutionContext, WorkResult

from .client import A2AClient, A2AFailure, Submitted
from .wire import AuthenticationInfo, MessageWire, Part, RoleWire, TaskPushNotificationConfig


class A2AWorkAgent:
    """A ``WorkAgent`` for one capability, dispatched over A2A. Thread-safe."""

    def __init__(
        self,
        *,
        client: A2AClient,
        store: ArtifactStore,
        capability: CapabilityId,
        webhook_url: str,
        webhook_authentication: AuthenticationInfo | None = None,
    ):
        self.client = client
        self.store = store
        self.capability = capability
        self.webhook_url = webhook_url
        self.webhook_authentication = webhook_authentication
        self._lock = threading.Lock()
        self._submitted: dict[StepId, Submitted] = {}

    def run(self, context: ExecutionContext, node: WorkNode) -> WorkResult:
        if node.capability != self.capability:
            return WorkResult.failed(f"this A2A boundary does not serve capability {str(node.capability)!r}")
        refused = refuse_a_reused_step(self.store, context, node)  # D-147: before anything else
        if refused is not None:
            return refused
        documents = self.store.supplied(context.execution_id)
        if not documents:
            return WorkResult.no_result("no documents were supplied, so there is nothing to research")
        prompt = (
            f"Mission goal: {context.task_genome.goal}\n\n"
            f"Documents:\n\n{render_artifacts(documents)}\n\n"
            "Task: extract the findings that bear on the goal, citing each source, in Markdown."
        )
        message = MessageWire(message_id=str(uuid.uuid4()), role=RoleWire.USER, parts=(Part(text=prompt),))
        push = TaskPushNotificationConfig(url=self.webhook_url, authentication=self.webhook_authentication)
        result = self.client.send_message(message, push_notification=push)
        if isinstance(result, A2AFailure):
            return WorkResult.failed(f"the A2A submission failed ({result.kind.value}): {result.message}")
        with self._lock:
            self._submitted[node.step_id] = result
        return WorkResult.submitted("dispatched to a remote A2A task; the outcome is not yet known")

    def submitted_task(self, step_id: StepId) -> Submitted | None:
        """The last successful submission's correlation facts for ``step_id``, or ``None`` if none was recorded."""
        with self._lock:
            return self._submitted.get(step_id)

    def submitted_tasks(self) -> Mapping[StepId, Submitted]:
        """Every step's last successful submission, as a snapshot — never the live dict."""
        with self._lock:
            return dict(self._submitted)


__all__ = ["A2AWorkAgent"]
