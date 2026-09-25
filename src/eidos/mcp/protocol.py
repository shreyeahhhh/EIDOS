"""The wire protocol of the one MCP revision EIDOS speaks, as pure functions (decisions.md D-203, D-207; V1.2 Step 5).

**Revision ``2026-07-28``, and only that one.** It was verified against the published specification when this was written: the revision is stateless.
There is no ``initialize`` handshake and no session; every request carries its own ``_meta`` with the protocol version, the client's capabilities and
(by recommendation) its identity, and a server that does not implement the version answers ``UnsupportedProtocolVersionError``. ``server/discover`` is
mandatory for a server and is how a client learns, before it sends anything else, that the server speaks this revision at all. Earlier, handshake-based
revisions (``2025-11-25`` and before) are **not** supported and are not adapted to: a server of another revision is refused with a typed failure
(D-203 ruling 3), never accommodated.

Framing is stdio's: one JSON-RPC message per line, UTF-8, no embedded newline. This module builds and reads those messages and does nothing else: it
opens no process and no stream, reads no clock and holds no state, so every rule in it is testable without a server. What a server *claims* about itself
(``serverInfo``, ``instructions``, tool ``annotations``) is never read, because none of it is a decision input: whether a tool is read-only is EIDOS's own
declaration on its allowlist entry, and text a server returns is data and never an instruction (invariant 3).

The digest of a tool's declared ``inputSchema`` is defined here, because the schema is the MCP side's own artefact: SHA-256 of its canonical JSON (keys
sorted, no whitespace, non-ASCII escaped), in lowercase hex, which is what an allowlist entry's ``input_schema_digest`` pins.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from eidos.agents import ToolDocument, ToolFailure, ToolFailureKind, ToolResult

PROTOCOL_VERSION = "2026-07-28"
CLIENT_INFO = {"name": "eidos-mcp-client", "version": "1"}
_META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
    "io.modelcontextprotocol/clientCapabilities": {},
}
_MESSAGE_TEXT_LIMIT = 200  # how much of a server's own error text is kept in a failure message


def _line(message: Mapping[str, object]) -> bytes:
    return json.dumps(message, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def request_line(request_id: int, method: str, params: Mapping[str, object] | None = None) -> bytes:
    """One request, carrying the per-request ``_meta`` this revision requires on every request. No trailing newline."""
    return _line({"jsonrpc": "2.0", "id": request_id, "method": method, "params": {**(params or {}), "_meta": _META}})


def cancellation_line(request_id: int, reason: str) -> bytes:
    """The notification a stdio client must send to abandon an in-flight request."""
    return _line({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": request_id, "reason": reason}})


def schema_digest(schema: object) -> str:
    """The pin for a declared input schema: SHA-256 (lowercase hex) of its canonical JSON."""
    return hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


# --- reading a reply ------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Success:
    result: dict


@dataclass(frozen=True, slots=True)
class RemoteError:
    code: int
    message: str


@dataclass(frozen=True, slots=True)
class Violation:
    """A message that breaks the protocol: the stream can no longer be trusted, so the caller ends the session."""

    reason: str


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def parse_reply(line: bytes, request_id: int) -> Success | RemoteError | Violation | None:
    """Read one line as the reply to ``request_id``. ``None`` means it is not that reply (a notification, or a reply to another request) and is to be
    skipped; anything that is not valid JSON-RPC is a ``Violation``."""
    try:
        message = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return Violation("a line that is not valid UTF-8 JSON")
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return Violation("a message that is not a JSON-RPC 2.0 object")
    if "method" in message:
        return None  # a notification (or a request, which a server may not send): not the reply
    if "id" not in message:
        return Violation("a response with no id")
    if message["id"] != request_id or not _is_int(message["id"]):
        return None  # a reply to another request: this session sends one at a time, so it can only be stale
    has_result, has_error = "result" in message, "error" in message
    if has_result == has_error:
        return Violation("a response with both or neither of result and error")
    if has_error:
        error = message["error"]
        if not isinstance(error, dict) or not _is_int(error.get("code")) or not isinstance(error.get("message"), str):
            return Violation("an error that is not a code and a message")
        return RemoteError(code=error["code"], message=error["message"][:_MESSAGE_TEXT_LIMIT])
    if not isinstance(message["result"], dict):
        return Violation("a result that is not an object")
    return Success(result=message["result"])


def _result_type_problem(result: Mapping[str, object]) -> str | None:
    result_type = result.get("resultType", "complete")  # an absent resultType is "complete" (the specification says so)
    if result_type != "complete":
        return f"a result of type {str(result_type)[:40]!r}, and only a complete result is supported"
    return None


# --- discovery ------------------------------------------------------------------------------------------------------------------------


def discovery_problem(result: Mapping[str, object]) -> str | None:
    """Why a ``server/discover`` result does not describe a server EIDOS can use, or ``None``. It must complete, list this revision among the versions it
    supports, and declare the tools capability."""
    problem = _result_type_problem(result)
    if problem is not None:
        return problem
    versions = result.get("supportedVersions")
    if not isinstance(versions, list) or PROTOCOL_VERSION not in versions:
        return f"the server does not support protocol revision {PROTOCOL_VERSION}"
    capabilities = result.get("capabilities")
    if not isinstance(capabilities, dict) or "tools" not in capabilities:
        return "the server does not declare the tools capability"
    return None


def listing_problem(result: Mapping[str, object]) -> str | None:
    problem = _result_type_problem(result)
    if problem is not None:
        return problem
    tools = result.get("tools")
    if not isinstance(tools, list) or not all(isinstance(tool, dict) and isinstance(tool.get("name"), str) for tool in tools):
        return "a tool list that is not a list of named tools"
    cursor = result.get("nextCursor")
    if cursor is not None and not isinstance(cursor, str):
        return "a next-page cursor that is not a string"
    return None


# --- a tool call's result, normalised -----------------------------------------------------------------------------------------------


def _first_text(content: object) -> str | None:
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                return block["text"][:_MESSAGE_TEXT_LIMIT]
    return None


def normalise_call_result(result: Mapping[str, object]) -> ToolResult | ToolFailure:
    """A ``tools/call`` result as EIDOS's own ``ToolResult`` or a typed ``ToolFailure``.

    A tool that reports its own error (``isError``) is a ``TOOL_ERROR``. A successful result is read from ``structuredContent``, which must be an object
    with a ``documents`` list of ``{"id", "text"}`` objects with distinct, non-empty string ids; anything else is a ``MALFORMED_RESULT``. Unstructured
    content is never parsed for documents: text a tool returns is data, and this function does not interpret it.
    """
    problem = _result_type_problem(result)
    if problem is not None:
        return ToolFailure(kind=ToolFailureKind.MALFORMED_RESULT, message=problem)
    if result.get("isError") is True:
        return ToolFailure(kind=ToolFailureKind.TOOL_ERROR, message=_first_text(result.get("content")) or "the tool reported an error")
    structured = result.get("structuredContent")
    documents = structured.get("documents") if isinstance(structured, dict) else None
    if not isinstance(documents, list):
        return ToolFailure(kind=ToolFailureKind.MALFORMED_RESULT, message="the result has no structured list of documents")
    found: list[ToolDocument] = []
    seen: set[str] = set()
    for document in documents:
        if not isinstance(document, dict) or not isinstance(document.get("id"), str) or not document["id"] or not isinstance(document.get("text"), str):
            return ToolFailure(kind=ToolFailureKind.MALFORMED_RESULT, message="a document that is not an id and a text")
        if document["id"] in seen:
            return ToolFailure(kind=ToolFailureKind.MALFORMED_RESULT, message="a document id that appears twice")
        seen.add(document["id"])
        found.append(ToolDocument(document_id=document["id"], content=document["text"]))
    return ToolResult(documents=tuple(found))
