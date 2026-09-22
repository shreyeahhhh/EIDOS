"""The A2A v1.0 wire types — verified against the published spec, not assumed (decisions.md D-171, D-172).

Verified 2026-09-22 directly against ``github.com/a2aproject/A2A`` (``specification/a2a.proto``, the single normative
schema) and ``adrs/adr-001-protojson-serialization.md`` (Accepted): the JSON-RPC and HTTP+JSON bindings both serialize
the proto schema via **ProtoJSON** — enum values as their full declared name in ``SCREAMING_SNAKE_CASE`` (never plain
lowercase, never stripped of a prefix), field names as ``lowerCamelCase``. This **resolves** the casing question V0.6
Step 2 (D-166) deliberately left unverified: ``TaskState`` wire values are ``TASK_STATE_SUBMITTED``-style, confirmed
by the spec's own worked example (§6.6), not the pre-unification lowercase form once seen elsewhere.

The JSON-RPC binding (spec §9) wraps these same proto-defined messages in a JSON-RPC 2.0 envelope; method names are
**PascalCase** matching the gRPC method names (``SendMessage``, ``GetTask``) — **not** the ``category/action`` form
(``message/send``) V0.6 Step 1 assumed from an earlier reading. See ``client.py`` and the Step 5 report for this
correction; nothing in ``decisions.md`` D-165–D-176 depended on the literal method-name string, so this is a verified
implementation detail, not a contract change.

These types describe an **external protocol EIDOS does not control** — unlike ``eidos.contracts``, which owns its own
schema and can safely reject an unknown field (D-153's discipline), a wire type here tolerates one: ProtoJSON is
explicitly designed for forward compatibility (unknown fields are dropped, not an error), and a future A2A minor
version must not break EIDOS's parser. ``WireModel`` is deliberately **not** ``EidosModel``: still frozen, still
exactly typed, but ``extra="ignore"`` where ``EidosModel`` forbids it, and not additionally ``strict`` — two
intentional, documented departures (see ``WireModel`` itself).

Only what V0.6's minimal slice needs is modelled: submission (``SendMessage``), an optional reconciliation poll
(``GetTask``), and receiving one push-notification payload (``StreamResponse``, used identically for streaming and for
a webhook body, per spec §4.3.3). No streaming transport, no ``tasks/cancel``, no push-notification-config management
RPCs beyond the inline ``SendMessageConfiguration.task_push_notification_config`` (D-171 item 2's minimal surface).
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class WireModel(BaseModel):
    """Frozen, like ``EidosModel`` — but two deliberate departures, both because this describes an external protocol
    EIDOS does not own, not an EIDOS contract: ``extra="ignore"`` (ProtoJSON is designed for forward compatibility;
    an unknown field must not break parsing a future minor version), and **not** ``strict=True`` (pydantic v2's
    strict mode refuses to build a ``StrEnum`` member from the plain ``str`` every JSON parse produces — a
    well-known limitation, not a relaxation of what values are accepted: every field here is still exactly typed,
    just not additionally forbidden from the ordinary str-to-enum conversion JSON parsing requires). CamelCase-
    aliased, so a Python attribute is written in EIDOS's own snake_case."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True, alias_generator=to_camel)


class TaskStateWire(StrEnum):
    """The real A2A ``TaskState`` wire values (proto enum names, ProtoJSON-serialized). Member *names* match
    ``eidos.contracts.AgentTaskStatus`` exactly (D-166), so converting one to the other is a name lookup, not a
    hand-written table — see ``convert.py``."""

    UNSPECIFIED = "TASK_STATE_UNSPECIFIED"
    SUBMITTED = "TASK_STATE_SUBMITTED"
    WORKING = "TASK_STATE_WORKING"
    COMPLETED = "TASK_STATE_COMPLETED"
    FAILED = "TASK_STATE_FAILED"
    CANCELED = "TASK_STATE_CANCELED"
    INPUT_REQUIRED = "TASK_STATE_INPUT_REQUIRED"
    REJECTED = "TASK_STATE_REJECTED"
    AUTH_REQUIRED = "TASK_STATE_AUTH_REQUIRED"


class RoleWire(StrEnum):
    UNSPECIFIED = "ROLE_UNSPECIFIED"
    USER = "ROLE_USER"
    AGENT = "ROLE_AGENT"


class Part(WireModel):
    """One part of a ``Message`` or ``Artifact`` (a proto ``oneof``): at most one of ``text``/``raw``/``url``/``data``.

    V0.6's minimal slice reads only ``text`` (EIDOS's own artifacts are text/Markdown only, ``SUPPORTED_CONTENT_TYPES``
    in ``eidos.agents.base``); the other three are parsed faithfully but never converted — a part with none of them
    usable is simply not a usable result, handled the same way a `COMPLETED` task with no artifact already is (D-166).
    """

    text: str | None = None
    raw: str | None = None  # base64, per the spec's own JSON note; never decoded here
    url: str | None = None
    data: Any | None = None
    metadata: dict[str, Any] | None = None
    filename: str | None = None
    media_type: str | None = None

    @model_validator(mode="after")
    def _check_at_most_one_content(self) -> "Part":
        present = [v for v in (self.text, self.raw, self.url, self.data) if v is not None]
        if len(present) > 1:
            raise ValueError("a Part carries at most one of text/raw/url/data (a proto oneof)")
        return self


class MessageWire(WireModel):
    message_id: str = Field(min_length=1)
    context_id: str | None = None
    task_id: str | None = None
    role: RoleWire
    parts: tuple[Part, ...] = ()
    metadata: dict[str, Any] | None = None
    extensions: tuple[str, ...] = ()
    reference_task_ids: tuple[str, ...] = ()


class Artifact(WireModel):
    artifact_id: str = Field(min_length=1)
    name: str | None = None
    description: str | None = None
    parts: tuple[Part, ...] = ()
    metadata: dict[str, Any] | None = None
    extensions: tuple[str, ...] = ()


class TaskStatus(WireModel):
    state: TaskStateWire
    message: MessageWire | None = None
    timestamp: str | None = None  # ISO 8601; carried for fidelity, not parsed — nothing here orders on it (D-160 item 7)


class Task(WireModel):
    id: str = Field(min_length=1)
    context_id: str | None = None
    status: TaskStatus
    artifacts: tuple[Artifact, ...] = ()
    history: tuple[MessageWire, ...] = ()
    metadata: dict[str, Any] | None = None


class TaskStatusUpdateEvent(WireModel):
    task_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    status: TaskStatus
    metadata: dict[str, Any] | None = None


class TaskArtifactUpdateEvent(WireModel):
    task_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    artifact: Artifact
    append: bool | None = None
    last_chunk: bool | None = None
    metadata: dict[str, Any] | None = None


class StreamResponse(WireModel):
    """The webhook body (spec §4.3.3) and the streaming payload shape: exactly one of the four fields.

    Unlike ``Part``'s oneof (parsed leniently — a third party's content choice), this one is EIDOS's own webhook
    entry point, so "none set" and "more than one set" are both a typed, reported malformed payload (item 7): the
    boundary between a malformed push and a valid one starts exactly here.
    """

    task: Task | None = None
    message: MessageWire | None = None
    status_update: TaskStatusUpdateEvent | None = None
    artifact_update: TaskArtifactUpdateEvent | None = None

    @model_validator(mode="after")
    def _check_exactly_one_payload(self) -> "StreamResponse":
        present = [v for v in (self.task, self.message, self.status_update, self.artifact_update) if v is not None]
        if len(present) != 1:
            raise ValueError(f"a StreamResponse carries exactly one payload, not {len(present)}")
        return self


class SendMessageResponse(WireModel):
    """The result of ``SendMessage`` (spec §3.2.1): exactly one of ``task``/``message``."""

    task: Task | None = None
    message: MessageWire | None = None

    @model_validator(mode="after")
    def _check_exactly_one_payload(self) -> "SendMessageResponse":
        if (self.task is None) == (self.message is None):
            raise ValueError("a SendMessageResponse carries exactly one of task or message")
        return self


class AuthenticationInfo(WireModel):
    scheme: str = Field(min_length=1)
    credentials: str | None = None


class TaskPushNotificationConfig(WireModel):
    """Registers a webhook (spec §4.3.1). Sent **inline**, inside ``SendMessageConfiguration`` — V0.6 does not call
    the separate ``CreateTaskPushNotificationConfig``/etc. RPCs, which manage configs after the fact (out of scope,
    item 1: only the minimum operations)."""

    tenant: str | None = None
    id: str | None = None
    task_id: str | None = None
    url: str = Field(min_length=1)
    token: str | None = None
    authentication: AuthenticationInfo | None = None


class SendMessageConfiguration(WireModel):
    """No field has a Python-level default: a caller states its choices explicitly, the same discipline
    ``ModelSettings`` already has (D-135) — most importantly ``return_immediately``, which the spec defaults to
    ``false`` server-side (**the server blocks until the task is terminal**) and which EIDOS's non-blocking design
    (D-165 rule 5) requires to be sent as ``true`` on every request; getting this wrong would silently turn every
    submission into a blocking call the moment a real server is speaking, so it is never left to a wire-level default.
    """

    accepted_output_modes: tuple[str, ...] = ()
    task_push_notification_config: TaskPushNotificationConfig | None = None
    history_length: int | None = None
    return_immediately: bool


class SendMessageRequest(WireModel):
    tenant: str | None = None
    message: MessageWire
    configuration: SendMessageConfiguration | None = None
    metadata: dict[str, Any] | None = None


class GetTaskRequest(WireModel):
    tenant: str | None = None
    id: str = Field(min_length=1)
    history_length: int | None = None


# --- the JSON-RPC 2.0 envelope (spec §9.3) -----------------------------------------------------------------------


class JsonRpcRequest(WireModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str = Field(min_length=1)
    method: str = Field(min_length=1)
    params: dict[str, Any] | None = None


class JsonRpcError(WireModel):
    code: int
    message: str
    data: Any | None = None


class JsonRpcResponse(WireModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None  # JSON-RPC 2.0 permits either (the spec's own examples use both); EIDOS's own requests always send a string
    result: Any | None = None
    error: JsonRpcError | None = None

    @model_validator(mode="after")
    def _check_exactly_one_of_result_or_error(self) -> "JsonRpcResponse":
        if (self.result is None) == (self.error is None):
            raise ValueError("a JSON-RPC response carries exactly one of result or error")
        return self
