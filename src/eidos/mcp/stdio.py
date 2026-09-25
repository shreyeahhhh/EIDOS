"""A ``ToolPort`` over a locally launched server, spoken to over standard input and output (decisions.md D-203, D-207; V1.2 Step 5).

This is transport, and only transport. **Admission is not here**: by the time a request reaches ``StdioMcpToolPort.call`` the gate has already admitted
it, and this module neither decides whether a call is allowed nor reads a budget, an action, an autonomy level or a read-only declaration. It launches
the server EIDOS is configured to trust, checks that it is the server the allowlist pins, sends the one admitted call, and turns whatever comes back into
EIDOS's own ``ToolResult`` or a typed ``ToolFailure``. Nothing a server says about itself is used as a decision: not its identity, not its instructions and
not its tool annotations (invariant 14; the specification itself says annotations are untrusted).

**Lifecycle.** The server is a child process started on first use, with exactly the environment the launch configuration names (nothing is inherited) and
no shell, its standard input and output as the channel and its standard error discarded. It is kept between calls, because the protocol is stateless and
an open process is not a conversation. If it has exited when a call arrives it is started again; if it dies during a call that call fails, typed, and is
not retried. It is ended by ``close`` (close its input, wait a moment, then kill) and is killed on a timeout, a malformed message or a message over the
size cap, since after any of those the stream cannot be trusted.

**Start of a session.** ``server/discover`` first (the revision is stateless, so there is no handshake): a server that does not answer it as a
``2026-07-28`` server, or does not list that revision, is refused. Then ``tools/list``, paged and bounded: every tool the allowlist pins for this provider
must be offered, and the SHA-256 of the input schema the server declares must equal the pinned digest. A server that fails either check is refused for the
life of this port with a typed ``UNAVAILABLE`` failure and is not launched again.

**Bounds, all deterministic.** The call's timeout covers the whole call, launch and discovery included, and is measured on the monotonic clock; on expiry the
client sends the cancellation notification the specification requires and ends the process. A line longer than ``max_message_bytes`` is refused and the
process ended. A result larger than the allowlist entry's ``max_result_bytes`` is a ``RESULT_TOO_LARGE`` failure, never truncated.

One call is in flight at a time (a lock serialises them): a request is small and the protocol needs no more, and a single in-flight request keeps a
reply unambiguous. Nothing here writes ``MissionState``, records an event or imports the policy layer.
"""

import queue
import subprocess
import threading
import time

from pydantic import Field

from eidos.agents import ToolFailure, ToolFailureKind, ToolOutcome, ToolRequest, ToolResult, bound_result
from eidos.capabilities import ToolRegistry
from eidos.contracts import EidosModel

from . import protocol

_SHUTDOWN_GRACE_SECONDS = 1.0
_MAX_LIST_PAGES = 5  # a bound on paging through tools/list, so a server that never stops offering pages cannot hold the client


class McpServerLaunch(EidosModel):
    """How to start the trusted local server: a program and its arguments (never a shell string), the exact environment it gets, and where it runs."""

    argv: tuple[str, ...] = Field(min_length=1)
    env: tuple[tuple[str, str], ...] = ()
    cwd: str | None = None


class _Stop(Exception):
    """A call or a session start that cannot go on. ``refuse`` says the server itself is unacceptable, not just this call."""

    def __init__(self, kind: ToolFailureKind, message: str, *, refuse: bool = False):
        super().__init__(message)
        self.failure = ToolFailure(kind=kind, message=message)
        self.refuse = refuse


_END_OF_STREAM = object()
_MESSAGE_TOO_LARGE = object()


class _Session:
    """One live server process and the thread that reads its output line by line into a queue."""

    def __init__(self, launch: McpServerLaunch, max_message_bytes: int):
        self.process = subprocess.Popen(  # noqa: S603 — a fixed argv from trusted configuration, never a shell
            list(launch.argv), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=dict(launch.env), cwd=launch.cwd, shell=False,
        )
        self.lines: queue.Queue = queue.Queue()
        self._limit = max_message_bytes + 2  # room for the message, its line ending and one byte more, so an over-long line is recognised
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        stream = self.process.stdout
        try:
            while True:
                line = stream.readline(self._limit)
                if not line:
                    break
                terminated = line.endswith(b"\n")
                body = line[:-1] if terminated else line
                if body.endswith(b"\r"):
                    body = body[:-1]
                if (not terminated and len(line) >= self._limit) or len(body) > self._limit - 2:
                    self.lines.put(_MESSAGE_TOO_LARGE)
                    return
                self.lines.put(body)
        except (OSError, ValueError):
            pass
        self.lines.put(_END_OF_STREAM)

    @property
    def alive(self) -> bool:
        return self.process.poll() is None

    def send(self, data: bytes) -> None:
        self.process.stdin.write(data + b"\n")
        self.process.stdin.flush()

    def close(self) -> None:
        try:
            self.process.stdin.close()
        except OSError:
            pass
        try:
            self.process.wait(timeout=_SHUTDOWN_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        try:
            self.process.stdout.close()
        except OSError:
            pass
        self._reader.join(timeout=_SHUTDOWN_GRACE_SECONDS)


class StdioMcpToolPort:
    """Implements ``eidos.agents.ToolPort`` for the tools one provider's allowlist entries pin. Thread-safe. ``max_message_bytes`` is required: there is no
    default cap on a line."""

    def __init__(self, *, launch: McpServerLaunch, registry: ToolRegistry, provider_id: str, max_message_bytes: int):
        if max_message_bytes < 1:
            raise ValueError("max_message_bytes is a size and is at least one")
        self._launch, self._registry, self._provider_id, self._max_message_bytes = launch, registry, provider_id, max_message_bytes
        self._lock = threading.Lock()
        self._session: _Session | None = None
        self._refusal: str | None = None
        self._next_id = 0
        self.process_starts = 0  # how many times the server has been launched: a fact for tests and audit, never a decision input

    def __enter__(self) -> "StdioMcpToolPort":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            self._end_session()

    @property
    def running(self) -> bool:
        """Whether a server process is currently held."""
        with self._lock:
            return self._session is not None and self._session.alive

    # --- the port --------------------------------------------------------------------------------------------------------------------

    def call(self, request: ToolRequest) -> ToolOutcome:
        with self._lock:
            deadline = time.monotonic() + request.timeout_seconds
            descriptor = self._registry.resolve(request.tool_id)
            if descriptor is None or descriptor.provider_id != self._provider_id:
                return ToolFailure(kind=ToolFailureKind.UNAVAILABLE, message="this provider does not serve that tool")
            if self._refusal is not None:
                return ToolFailure(kind=ToolFailureKind.UNAVAILABLE, message=self._refusal)
            try:
                session = self._live_session(deadline)
                reply = self._exchange(
                    session, "tools/call", {"name": descriptor.tool_name, "arguments": {a.name: a.value for a in request.arguments}}, deadline
                )
            except _Stop as stop:
                if stop.refuse:
                    self._refusal = stop.failure.message
                self._end_session()
                return stop.failure
            if isinstance(reply, protocol.RemoteError):
                return ToolFailure(kind=ToolFailureKind.TOOL_ERROR, message=f"the server answered with error {reply.code}: {reply.message}")
            outcome = protocol.normalise_call_result(reply.result)
            return bound_result(outcome, request.max_result_bytes) if isinstance(outcome, ToolResult) else outcome

    # --- the session ------------------------------------------------------------------------------------------------------------------

    def _live_session(self, deadline: float) -> _Session:
        if self._session is not None and self._session.alive:
            return self._session
        self._end_session()  # one that has exited is cleared away, then started again
        self.process_starts += 1
        try:
            session = _Session(self._launch, self._max_message_bytes)
        except OSError as error:
            raise _Stop(ToolFailureKind.UNAVAILABLE, f"the server could not be launched ({type(error).__name__})") from error
        self._session = session
        self._begin(session, deadline)
        return session

    def _end_session(self) -> None:
        session, self._session = self._session, None
        if session is not None:
            session.close()

    def _begin(self, session: _Session, deadline: float) -> None:
        found = self._exchange(session, "server/discover", None, deadline)
        if isinstance(found, protocol.RemoteError):
            raise _Stop(
                ToolFailureKind.UNAVAILABLE,
                f"the server did not answer server/discover (error {found.code}): it is not a {protocol.PROTOCOL_VERSION} server",
                refuse=True,
            )
        problem = protocol.discovery_problem(found.result)
        if problem is not None:
            raise _Stop(ToolFailureKind.UNAVAILABLE, problem, refuse=True)
        declared = self._list_tools(session, deadline)
        for tool in self._registry.tools:
            if tool.provider_id != self._provider_id:
                continue
            offered = declared.get(tool.tool_name)
            if offered is None:
                raise _Stop(ToolFailureKind.UNAVAILABLE, f"the server does not offer the pinned tool {tool.tool_name!r}", refuse=True)
            if protocol.schema_digest(offered.get("inputSchema")) != tool.input_schema_digest:
                raise _Stop(ToolFailureKind.UNAVAILABLE, f"the schema the server declares for {tool.tool_name!r} is not the pinned schema", refuse=True)

    def _list_tools(self, session: _Session, deadline: float) -> dict[str, dict]:
        declared: dict[str, dict] = {}
        cursor = None
        for _ in range(_MAX_LIST_PAGES):
            page = self._exchange(session, "tools/list", {} if cursor is None else {"cursor": cursor}, deadline)
            if isinstance(page, protocol.RemoteError):
                raise _Stop(ToolFailureKind.UNAVAILABLE, f"the server could not list its tools (error {page.code})", refuse=True)
            problem = protocol.listing_problem(page.result)
            if problem is not None:
                raise _Stop(ToolFailureKind.UNAVAILABLE, problem, refuse=True)
            for tool in page.result["tools"]:
                declared.setdefault(tool["name"], tool)
            cursor = page.result.get("nextCursor")
            if not cursor:
                return declared
        return declared

    # --- one request and its reply -----------------------------------------------------------------------------------------------------

    def _exchange(self, session: _Session, method: str, params, deadline: float):
        """Send one request and wait, until ``deadline``, for its reply: a ``Success`` or a ``RemoteError``. Any other end is a ``_Stop``."""
        self._next_id += 1
        request_id = self._next_id
        try:
            session.send(protocol.request_line(request_id, method, params))
        except OSError as error:
            raise _Stop(ToolFailureKind.UNAVAILABLE, "the server stopped accepting requests") from error
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise self._timed_out(session, request_id)
            try:
                item = session.lines.get(timeout=remaining)
            except queue.Empty:
                raise self._timed_out(session, request_id) from None
            if item is _END_OF_STREAM:
                raise _Stop(ToolFailureKind.UNAVAILABLE, "the server process ended")
            if item is _MESSAGE_TOO_LARGE:
                raise _Stop(ToolFailureKind.RESULT_TOO_LARGE, f"the server sent a message larger than {self._max_message_bytes} bytes")
            reply = protocol.parse_reply(item, request_id)
            if reply is None:
                continue
            if isinstance(reply, protocol.Violation):
                raise _Stop(ToolFailureKind.MALFORMED_RESULT, f"the server broke the protocol: {reply.reason}")
            return reply

    @staticmethod
    def _timed_out(session: _Session, request_id: int) -> _Stop:
        try:
            session.send(protocol.cancellation_line(request_id, "the call exceeded its timeout"))
        except OSError:
            pass
        return _Stop(ToolFailureKind.TIMEOUT, "the call did not finish inside its timeout")
