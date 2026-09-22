"""Factories and doubles for V0.6 Step 5's A2A boundary tests.

``FakeTransport`` is the fake at the transport seam (D-171, mirroring D-136's own precedent for ``ScriptedModel``):
the default suite never reaches a real network. It answers as a test scripted, records every call, and is
thread-safe. Nothing here names a real A2A server.
"""

import json
import threading
from uuid import UUID

from eidos.a2a.transport import TransportFailure, TransportFailureKind, TransportResponse, TransportResult
from eidos.contracts import CapabilityId, ReliabilityContractId, StepId
from eidos.compiler import CompiledPlan, compile_plan
from eidos.runtime import ExecutionContext

from eidos_compiler_factories import forged_accepted_report
from eidos_factories import make_agent_step, make_plan, make_reliability_contract, make_task_genome

EXECUTION_ID = UUID(int=41)
RESEARCH = CapabilityId("research")


class FakeTransport:
    """A ``Transport`` that answers with ``respond(url, body, headers) -> TransportResult``. Records every call."""

    def __init__(self, respond=None):
        self._respond = respond or (lambda url, body, headers: TransportFailure(kind=TransportFailureKind.NETWORK, message="no script"))
        self._lock = threading.Lock()
        self.calls: list[tuple[str, str, dict]] = []

    def post_json(self, url: str, body: str, *, headers) -> TransportResult:
        with self._lock:
            self.calls.append((url, body, dict(headers)))
            respond = self._respond
        return respond(url, body, dict(headers))

    def script(self, respond) -> None:
        with self._lock:
            self._respond = respond

    @property
    def call_count(self) -> int:
        with self._lock:
            return len(self.calls)


def _request_id(body: str) -> str:
    return json.loads(body)["id"]


def json_rpc_result(body: str, result: dict) -> TransportResponse:
    """A well-formed JSON-RPC success envelope echoing ``body``'s own request id (spec §9.3)."""
    return TransportResponse(status_code=200, text=json.dumps({"jsonrpc": "2.0", "id": _request_id(body), "result": result}))


def json_rpc_error(body: str, code: int, message: str) -> TransportResponse:
    return TransportResponse(
        status_code=200, text=json.dumps({"jsonrpc": "2.0", "id": _request_id(body), "error": {"code": code, "message": message}})
    )


def wire_task(task_id: str, *, context_id: str = "ctx-1", state: str = "TASK_STATE_SUBMITTED", artifacts: list | None = None) -> dict:
    task = {"id": task_id, "contextId": context_id, "status": {"state": state}}
    if artifacts is not None:
        task["artifacts"] = artifacts
    return task


def wire_text_artifact(artifact_id: str, text: str, *, media_type: str = "text/markdown") -> dict:
    return {"artifactId": artifact_id, "parts": [{"text": text, "mediaType": media_type}]}


def submit_responds_with_task(task_id: str, *, context_id: str = "ctx-1", state: str = "TASK_STATE_SUBMITTED"):
    """A transport script: every ``SendMessage`` call succeeds, returning a fixed task id/context id/state."""

    def respond(url, body, headers):
        return json_rpc_result(body, {"task": wire_task(task_id, context_id=context_id, state=state)})

    return respond


def push_notification_body(*, task_id: str, context_id: str = "ctx-1", state: str, artifacts: list | None = None) -> str:
    """A webhook POST body: a ``StreamResponse`` carrying one ``statusUpdate`` (spec §4.3.3's own example shape)."""
    status = {"state": state}
    body = {"statusUpdate": {"taskId": task_id, "contextId": context_id, "status": status}}
    if artifacts is not None:
        # The spec's TaskStatusUpdateEvent carries no artifacts field; a server that wants to deliver one in the
        # same push sends a full `task` payload instead (both are handled identically by notification_to_proposal).
        body = {"task": wire_task(task_id, context_id=context_id, state=state, artifacts=artifacts)}
    return json.dumps(body)


# --- plans, contexts and nodes for A2AWorkAgent tests ----------------------------------------------------------------


def compiled_research(**plan_overrides) -> CompiledPlan:
    plan = make_plan(steps=(make_agent_step(step_id=StepId("gather"), capability=RESEARCH),), **plan_overrides)
    report = compile_plan(plan, forged_accepted_report(plan))
    assert report.succeeded, [v.message for v in report.violations]
    return report.compiled


def node_of(compiled: CompiledPlan, step_id: str):
    return next(node for node in compiled.nodes if node.step_id == StepId(step_id))


def context_for(compiled: CompiledPlan, **overrides) -> ExecutionContext:
    contract = make_reliability_contract(
        tenant_id=overrides.get("tenant_id", compiled.tenant_id), contract_id=ReliabilityContractId(UUID(int=21))
    )
    fields = dict(
        tenant_id=compiled.tenant_id,
        mission_id=compiled.mission_id,
        execution_id=EXECUTION_ID,
        plan_id=compiled.plan_id,
        plan_version=compiled.plan_version,
        task_genome=make_task_genome(contract=contract),
        reliability_contract=contract,
    )
    fields.update(overrides)
    return ExecutionContext(**fields)
