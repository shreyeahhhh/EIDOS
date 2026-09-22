"""The hand-rolled A2A v1.0 JSON-RPC client (decisions.md D-171, D-165 rule 5).

Two operations only (D-171 item 2): ``send_message`` (submission — the only call the A2A spec requires to return a
task id synchronously) and ``get_task`` (an optional reconciliation read, never called automatically — D-170: nothing
here decides *when* to poll). No streaming, no ``tasks/cancel``, no push-notification-config management RPCs.

**Four failure boundaries, never collapsed into one (item 7 of the Step 5 scope):**

1. **transport/network failure** — ``TransportFailureKind.NETWORK``, from ``transport.py``, surfaced here as
   ``A2AFailureKind.NETWORK``.
2. **a transport-level timeout** (D-173 item 1 — *this* HTTP call did not answer inside the transport's own
   configured deadline) — ``A2AFailureKind.TRANSPORT_TIMEOUT``.
3. **a malformed A2A response** — the body was not valid JSON, or did not match the shape the spec defines —
   ``A2AFailureKind.MALFORMED_RESPONSE``.
4. **a well-formed JSON-RPC error** the peer sent on purpose (``TaskNotFoundError`` and the like) —
   ``A2AFailureKind.PROTOCOL_ERROR``, carrying the peer's own ``code``.

The **fourth boundary item 7 names — "EIDOS-observed timeout"** — is deliberately *not* a member of this client's
failure taxonomy at all: D-173 item 2's ``TIMED_OUT`` is the adapter's own conclusion that an outstanding *task* (not
one HTTP call) has gone unheard from for too long, computed from ``AgentTask.started_at`` versus now — a wholly
separate mechanism, ``deadline.py``, that never touches the network.

``send_message`` **always** sends ``return_immediately: true`` (never omitted, never left to the wire default,
which is ``false`` and would make a spec-compliant server *block the HTTP call* until the task is terminal — the
one detail that would silently defeat D-165 rule 5's non-blocking design if missed) and, when a webhook is given,
the inline ``task_push_notification_config`` — never the separate ``CreateTaskPushNotificationConfig`` RPC.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from eidos.contracts import A2AContextId, A2ATaskId

from .transport import Transport, TransportFailure, TransportFailureKind
from .wire import (
    Artifact,
    GetTaskRequest,
    JsonRpcRequest,
    JsonRpcResponse,
    MessageWire,
    SendMessageConfiguration,
    SendMessageRequest,
    SendMessageResponse,
    Task,
    TaskPushNotificationConfig,
    TaskStateWire,
    WireModel,
)


class A2AFailureKind(StrEnum):
    NETWORK = "network"
    TRANSPORT_TIMEOUT = "transport_timeout"
    MALFORMED_RESPONSE = "malformed_response"
    PROTOCOL_ERROR = "protocol_error"


@dataclass(frozen=True, slots=True)
class A2AFailure:
    kind: A2AFailureKind
    message: str
    code: int | None = None  # the JSON-RPC error code; present only for PROTOCOL_ERROR


@dataclass(frozen=True, slots=True)
class Submitted:
    """What ``send_message`` reports on success. ``state`` is whatever the peer's immediate response carried — D-165
    rule 5 means the caller never branches on it: any successful submission is treated as SUBMITTED, full stop; the
    task's real conclusion is learned later, only from a webhook delivery or a later ``get_task``."""

    task_id: A2ATaskId
    context_id: A2AContextId | None
    state: TaskStateWire
    artifacts: tuple[Artifact, ...]  # rarely non-empty this early; carried for fidelity, never required


SubmitResult = Submitted | A2AFailure


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    task_id: A2ATaskId
    context_id: A2AContextId | None
    state: TaskStateWire
    artifacts: tuple[Artifact, ...]


GetTaskResult = TaskSnapshot | A2AFailure


@dataclass(frozen=True, slots=True, kw_only=True)
class A2AClient:
    endpoint_url: str  # required, no default (D-135's discipline): wherever the peer's AgentCard says JSON-RPC lives
    transport: Transport
    tenant: str | None = None  # A2A's own opaque routing identifier (spec §4.5.2); unset unless the peer requires one

    def send_message(
        self,
        message: MessageWire,
        *,
        push_notification: TaskPushNotificationConfig | None = None,
        history_length: int | None = None,
    ) -> SubmitResult:
        configuration = SendMessageConfiguration(
            task_push_notification_config=push_notification, history_length=history_length, return_immediately=True
        )
        request = SendMessageRequest(tenant=self.tenant, message=message, configuration=configuration)
        result = self._call("SendMessage", request, SendMessageResponse)
        if isinstance(result, A2AFailure):
            return result
        response = result
        if response.task is not None:
            return Submitted(
                task_id=A2ATaskId(response.task.id),
                context_id=A2AContextId(response.task.context_id) if response.task.context_id else None,
                state=response.task.status.state,
                artifacts=response.task.artifacts,
            )
        # A `message`-only response means the peer answered directly with no task created (spec §3.2.1): there is
        # no task id to correlate against, so this is not a shape D-165's non-blocking design has anything to attach
        # to — reported as a malformed response for *this* boundary's purposes, not a transport or protocol fault.
        return A2AFailure(kind=A2AFailureKind.MALFORMED_RESPONSE, message="SendMessage answered with a message, not a task: nothing to correlate")

    def get_task(self, task_id: A2ATaskId, *, history_length: int | None = None) -> GetTaskResult:
        request = GetTaskRequest(id=str(task_id), history_length=history_length, tenant=self.tenant)
        result = self._call("GetTask", request, Task)
        if isinstance(result, A2AFailure):
            return result
        task = result
        return TaskSnapshot(
            task_id=A2ATaskId(task.id),
            context_id=A2AContextId(task.context_id) if task.context_id else None,
            state=task.status.state,
            artifacts=task.artifacts,
        )

    def _call(self, method: str, params: WireModel, response_model: type[WireModel]) -> WireModel | A2AFailure:
        request_id = str(uuid.uuid4())
        envelope = JsonRpcRequest(id=request_id, method=method, params=params.model_dump(mode="json", by_alias=True, exclude_none=True))
        body = envelope.model_dump_json(by_alias=True, exclude_none=True)
        result = self.transport.post_json(self.endpoint_url, body, headers={"Content-Type": "application/json"})
        if isinstance(result, TransportFailure):
            kind = A2AFailureKind.TRANSPORT_TIMEOUT if result.kind is TransportFailureKind.TIMEOUT else A2AFailureKind.NETWORK
            return A2AFailure(kind=kind, message=result.message)
        try:
            parsed = JsonRpcResponse.model_validate_json(result.text)
        except Exception as error:  # noqa: BLE001 — any parse fault is a malformed response, never raised
            return A2AFailure(kind=A2AFailureKind.MALFORMED_RESPONSE, message=f"the response was not a valid JSON-RPC envelope: {error}")
        if parsed.error is not None:
            return A2AFailure(kind=A2AFailureKind.PROTOCOL_ERROR, message=parsed.error.message, code=parsed.error.code)
        try:
            return response_model.model_validate(parsed.result)
        except Exception as error:  # noqa: BLE001
            return A2AFailure(
                kind=A2AFailureKind.MALFORMED_RESPONSE,
                message=f"the result did not match {response_model.__name__}'s shape: {error}",
            )
