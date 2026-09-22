"""eidos.a2a — the one A2A v1.0 boundary V0.6 builds (decisions.md D-165–D-176; V0.6 Step 5).

Speaks the published JSON-RPC 2.0 wire format directly over ``httpx`` (D-171; the optional ``a2a`` extra —
``pip install 'eidos[a2a]'``) — no ``a2a-sdk``. Submission (``A2AClient.send_message``, wrapped by ``A2AWorkAgent``
for the Research Agent, D-175) is the only synchronous call; a task's conclusion arrives later, converted from a raw
push-notification delivery into an ``EventProposal`` by ``webhook.notification_to_proposal`` — a pure function, not
a server — for the caller to carry to the existing ``EventLog.accept`` (D-172's guard, the reducer, all of it,
untouched). ``deadline.check_deadline`` is the third, separate timeout concept (D-173 item 2): EIDOS's own
conclusion that an outstanding task has gone unheard from too long, computed from recorded timestamps, never polled
automatically (D-170: no background driver anywhere in V0.6).

Nothing here is ``eidos.runtime``-visible: the runtime stays protocol-free (item 11's boundary), and this package
depends on ``eidos.contracts``/``eidos.state``/``eidos.runtime``/``eidos.agents``, never the reverse.
"""

from .agent import A2AWorkAgent
from .client import A2AClient, A2AFailure, A2AFailureKind, GetTaskResult, Submitted, SubmitResult, TaskSnapshot
from .convert import ConvertedArtifact, agent_task_status_of, text_artifact_of
from .deadline import check_deadline
from .transport import HttpxTransport, Transport, TransportFailure, TransportFailureKind, TransportResponse, TransportResult
from .webhook import WebhookOutcome, WebhookResult, notification_to_proposal
from .wire import Artifact as WireArtifact
from .wire import (
    AuthenticationInfo,
    GetTaskRequest,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    MessageWire,
    Part,
    RoleWire,
    SendMessageConfiguration,
    SendMessageRequest,
    SendMessageResponse,
    StreamResponse,
    Task,
    TaskArtifactUpdateEvent,
    TaskPushNotificationConfig,
    TaskStateWire,
    TaskStatus,
    TaskStatusUpdateEvent,
)

__all__ = [
    "A2AClient",
    "A2AFailure",
    "A2AFailureKind",
    "A2AWorkAgent",
    "AuthenticationInfo",
    "ConvertedArtifact",
    "GetTaskRequest",
    "GetTaskResult",
    "HttpxTransport",
    "JsonRpcError",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "MessageWire",
    "Part",
    "RoleWire",
    "SendMessageConfiguration",
    "SendMessageRequest",
    "SendMessageResponse",
    "StreamResponse",
    "Submitted",
    "SubmitResult",
    "Task",
    "TaskArtifactUpdateEvent",
    "TaskPushNotificationConfig",
    "TaskSnapshot",
    "TaskStateWire",
    "TaskStatus",
    "TaskStatusUpdateEvent",
    "Transport",
    "TransportFailure",
    "TransportFailureKind",
    "TransportResponse",
    "TransportResult",
    "WebhookOutcome",
    "WebhookResult",
    "WireArtifact",
    "agent_task_status_of",
    "check_deadline",
    "notification_to_proposal",
    "text_artifact_of",
]
