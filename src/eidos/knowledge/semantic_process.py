"""The isolated embedder: the one adapter of EIDOS that starts a process (decisions.md D-214, D-222, D-226; V1.3 Step 5).

``IsolatedEmbedder`` is an ``Embedder`` whose model runs in another interpreter, the isolated Python 3.13 environment that holds the model library, so the main runtime imports none of that
library. It starts ``semantic_worker.py`` (``semantic_worker_command``), speaks the worker's line protocol over its stdin and stdout, and turns every way that can go wrong into a typed
``EmbedderFailure``: nothing is raised for an outcome of the boundary.

Bounded and deterministic at the boundary. Every wait has a deadline (``WorkerLimits``): the worker's start (its model load), each request, its idle time and its total lifetime, which the worker
enforces on itself too, so an orphaned worker ends; a request is at most so many texts of so many characters, and a reply at most so many bytes, read with a limit, never whole. A timeout, a
crash, an oversize or malformed reply, a reply to another request, an identity that is not the pinned one and a worker that will not serve each stop the worker, and an embedder that has failed
does not restart: it answers ``unavailable`` from then on, and the caller makes a new one. The child gets an interpreter in isolated mode (``-I``) and a minimal explicit environment, never the caller's.

This module reads no model file and imports no model library; it is not imported by replay, by the state reducer or by anything but the code that assembles a semantic retriever.
"""

import json
import os
import queue
import subprocess
import sys
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Literal, Union

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from eidos.contracts import EidosModel

from .semantic import EmbeddedText, EmbedderFailure, EmbedderFailureKind, SemanticModelIdentity

PROTOCOL = "eidos-semantic-worker-v1"
WORKER_SCRIPT = Path(__file__).with_name("semantic_worker.py")
STDERR_TAIL_BYTES = 2000
STOP_GRACE_SECONDS = 2.0

# The only names the worker's environment is made of: what an interpreter needs to start and to find its libraries on this platform. Nothing else of the caller's environment reaches it.
INHERITED_ENVIRONMENT = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "TEMP", "TMP", "USERPROFILE", "HOME", "LOCALAPPDATA", "APPDATA", "LANG", "LC_ALL")

_FAILURE_OF_REASON = MappingProxyType(
    {
        "identity_mismatch": EmbedderFailureKind.IDENTITY_MISMATCH,
        "model_missing": EmbedderFailureKind.UNAVAILABLE,
        "library_missing": EmbedderFailureKind.UNAVAILABLE,
        "load_failed": EmbedderFailureKind.UNAVAILABLE,
    }
)


class WorkerLimits(EidosModel):
    """Every bound of the process boundary, in seconds, texts, characters and bytes. The defaults are fixed a priori and recorded in D-226; none is tuned."""

    ready_timeout_seconds: float = Field(default=300.0, gt=0, allow_inf_nan=False)  # the worker's start: interpreter, the digests of the model files, the library import and the model load
    request_timeout_seconds: float = Field(default=120.0, gt=0, allow_inf_nan=False)
    idle_timeout_seconds: float = Field(default=600.0, gt=0, allow_inf_nan=False)
    lifetime_seconds: float = Field(default=3600.0, gt=0, allow_inf_nan=False)
    max_texts_per_request: int = Field(default=64, ge=1)
    max_text_characters: int = Field(default=20000, ge=1)
    max_reply_bytes: int = Field(default=4 * 1024 * 1024, ge=1024)

    @model_validator(mode="after")
    def _check_the_worker_can_start_before_it_expires(self) -> "WorkerLimits":
        if self.idle_timeout_seconds <= self.ready_timeout_seconds or self.lifetime_seconds <= self.ready_timeout_seconds:
            raise ValueError("the idle time and the lifetime of a worker exceed the time it is given to start")
        return self


class WorkerEnvironment(EidosModel):
    """Where the model ran: the interpreter, the platform, the library versions, the thread count, whether the model was in evaluation mode, the device and the precision, as the worker measured them."""

    python_version: str
    implementation: str
    platform: str
    libraries: tuple[tuple[str, str], ...]
    threads: int = Field(ge=1)
    evaluation_mode: bool
    device: str
    dtype: str


class WorkerReady(EidosModel):
    """What the worker reported when it started: the identity it measured, the environment and how long each part of starting took."""

    identity: SemanticModelIdentity
    environment: WorkerEnvironment
    import_seconds: float = Field(ge=0)
    verify_seconds: float = Field(ge=0)
    load_seconds: float = Field(ge=0)


class _MeasuredIdentity(EidosModel):
    revision: str
    weights_sha256: str
    directory_sha256: str
    dimension: int
    max_pieces: int


class _ReadyLine(EidosModel):
    type: Literal["ready"]
    protocol: str
    identity: _MeasuredIdentity
    environment: WorkerEnvironment
    import_seconds: float = Field(ge=0)
    verify_seconds: float = Field(ge=0)
    load_seconds: float = Field(ge=0)


class _FailedLine(EidosModel):
    type: Literal["failed"]
    reason: str
    message: str


class _EmbeddedLine(EidosModel):
    type: Literal["embedded"]
    id: int
    seconds: float = Field(ge=0)
    items: tuple[EmbeddedText, ...]


class _RefusedLine(EidosModel):
    type: Literal["refused"]
    id: int | None
    message: str


class _ErrorLine(EidosModel):
    type: Literal["error"]
    id: int
    message: str


_END = object()  # the worker's output ended (in the middle of a line, or cleanly)
_TOO_LONG = object()  # a line too long to be read whole
_LINE = TypeAdapter(Annotated[Union[_ReadyLine, _FailedLine, _EmbeddedLine, _RefusedLine, _ErrorLine], Field(discriminator="type")])


def hub_model_directory(hub_root: Path, model: str, revision: str) -> Path:
    """Where a model library's local cache keeps one revision of a model: ``<hub_root>/models--<org>--<name>/snapshots/<revision>``."""
    return hub_root / f"models--{model.replace('/', '--')}" / "snapshots" / revision


def semantic_worker_command(
    python: str | Path, model_directory: Path, expected: SemanticModelIdentity, limits: WorkerLimits, *, script: Path = WORKER_SCRIPT
) -> tuple[str, ...]:
    """The command that starts a worker: the interpreter in isolated mode, the worker's script, the model directory and what it must verify, and every bound it enforces on itself."""
    return (
        str(python),
        "-I",
        str(script),
        "--model-dir",
        str(model_directory),
        "--expect-revision",
        expected.revision,
        "--expect-weights-sha256",
        expected.weights_sha256,
        "--expect-directory-sha256",
        expected.directory_sha256,
        "--lifetime-seconds",
        repr(limits.lifetime_seconds),
        "--idle-seconds",
        repr(limits.idle_timeout_seconds),
        "--max-texts",
        str(limits.max_texts_per_request),
        "--max-text-chars",
        str(limits.max_text_characters),
    )


def child_environment(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment of a worker: the names of ``INHERITED_ENVIRONMENT`` that this process has, and ``extra``."""
    environment = {name: os.environ[name] for name in INHERITED_ENVIRONMENT if name in os.environ}
    environment.update(extra or {})
    return environment


def creation_flags(platform: str) -> int:
    """The process creation flags of a worker: on Windows, no console window of its own; nowhere else, none."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if platform == "win32" else 0


def _tail(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace").strip()
    return f"; its last output: {text[-STDERR_TAIL_BYTES:]}" if text else ""


class _Worker:
    """A started process, the two threads that read its output, and the queue of what it said. Any failure to read a message stops the process."""

    def __init__(self, process: subprocess.Popen, limits: WorkerLimits):
        self.process = process
        self.limits = limits
        self.lines: queue.Queue = queue.Queue()
        self.stderr = bytearray()
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        self._stderr_pump = threading.Thread(target=self._pump_stderr, daemon=True)
        self._stderr_pump.start()

    def _pump_stdout(self) -> None:
        limit = self.limits.max_reply_bytes + 1
        try:
            while True:
                line = self.process.stdout.readline(limit)
                if line.endswith(b"\n"):
                    self.lines.put(line)
                    continue
                self.lines.put(_TOO_LONG if len(line) >= limit else _END)  # no newline: a line too long to read whole, or the stream ended (in the middle of a line, or cleanly)
                return
        except (OSError, ValueError):
            self.lines.put(_END)

    def _pump_stderr(self) -> None:
        try:
            for chunk in iter(lambda: self.process.stderr.read1(4096), b""):
                self.stderr.extend(chunk)
                del self.stderr[:-STDERR_TAIL_BYTES]
        except (OSError, ValueError):
            return

    @property
    def tail(self) -> str:
        return _tail(bytes(self.stderr))

    def running(self) -> bool:
        return self.process.poll() is None

    def write(self, data: bytes) -> bool:
        try:
            self.process.stdin.write(data)
            self.process.stdin.flush()
        except (OSError, ValueError):
            return False
        return True

    def message(self, timeout: float, *, what: str):
        """The worker's next message, parsed, or the typed failure that has stopped it: a timeout, a crash, an oversize line, or a line that is not a message of the protocol."""
        try:
            item = self.lines.get(timeout=timeout)
        except queue.Empty:
            self.stop()
            return EmbedderFailure(kind=EmbedderFailureKind.TIMEOUT, message=f"the worker did not {what} within {timeout} seconds, and was stopped")
        if item is _END:
            self._await_the_end()
            self.stop()
            return EmbedderFailure(kind=EmbedderFailureKind.CRASHED, message=f"the worker ended without answering (exit code {self.process.returncode}){self.tail}")
        if item is _TOO_LONG:
            self.stop()
            return EmbedderFailure(kind=EmbedderFailureKind.MALFORMED_REPLY, message=f"a reply of the worker exceeds {self.limits.max_reply_bytes} bytes, and the worker was stopped")
        try:
            return _LINE.validate_json(item)
        except ValidationError as error:
            self.stop()
            return EmbedderFailure(kind=EmbedderFailureKind.MALFORMED_REPLY, message=f"a reply of the worker is not a message of the protocol ({error.error_count()} errors)")

    def _await_the_end(self) -> None:
        """The worker's output has ended: give the process a moment to end and its last words a moment to be read, so a crash is reported with its exit code and what it said."""
        try:
            self.process.wait(timeout=STOP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        self._stderr_pump.join(timeout=STOP_GRACE_SECONDS)

    def stop(self, *, grace: float = 0.0) -> None:
        """End the process: wait ``grace`` seconds for it to end by itself, then kill it, and close the pipes."""
        if grace:
            try:
                self.process.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                pass
        if self.running():
            self.process.kill()
        self.process.wait()
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            try:
                pipe.close()
            except OSError:
                pass


class IsolatedEmbedder:
    """An ``Embedder`` over a running worker. Made only by ``start``; safe to share (one request at a time); ``close`` it, or use it as a context manager."""

    def __init__(self, worker: _Worker, *, expected: SemanticModelIdentity, limits: WorkerLimits, ready: WorkerReady):
        self._worker = worker
        self._expected = expected
        self._limits = limits
        self._ready = ready
        self._lock = threading.Lock()
        self._next_id = 1
        self._requests = 0
        self._worker_seconds = 0.0
        self._last_worker_seconds: float | None = None

    @classmethod
    def start(
        cls, command: Sequence[str], *, expected: SemanticModelIdentity, limits: WorkerLimits | None = None, environment: Mapping[str, str] | None = None
    ) -> "IsolatedEmbedder | EmbedderFailure":
        """Start a worker and wait for it to be ready, at most ``limits.ready_timeout_seconds``. The embedder, or the typed reason there is none. What the worker measured of the model must equal ``expected``."""
        limits = limits or WorkerLimits()
        try:
            process = subprocess.Popen(
                list(command), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=child_environment(environment), creationflags=creation_flags(sys.platform)
            )
        except (OSError, ValueError) as error:
            return EmbedderFailure(kind=EmbedderFailureKind.UNAVAILABLE, message=f"the worker cannot be started: {error}")
        worker = _Worker(process, limits)
        answer = worker.message(limits.ready_timeout_seconds, what="become ready")
        if isinstance(answer, EmbedderFailure):
            return answer
        if isinstance(answer, _FailedLine):
            worker.stop()
            return EmbedderFailure(
                kind=_FAILURE_OF_REASON.get(answer.reason, EmbedderFailureKind.MALFORMED_REPLY), message=f"the worker could not serve ({answer.reason}): {answer.message}"
            )
        if not isinstance(answer, _ReadyLine) or answer.protocol != PROTOCOL:
            worker.stop()
            return EmbedderFailure(kind=EmbedderFailureKind.MALFORMED_REPLY, message=f"the worker's first message is not a ready message of protocol {PROTOCOL}")
        for name in ("revision", "weights_sha256", "directory_sha256", "dimension", "max_pieces"):
            if getattr(answer.identity, name) != getattr(expected, name):
                worker.stop()
                return EmbedderFailure(
                    kind=EmbedderFailureKind.IDENTITY_MISMATCH,
                    message=f"the worker's model has {name} {getattr(answer.identity, name)!r}, and {getattr(expected, name)!r} is pinned",
                )
        ready = WorkerReady(
            identity=expected, environment=answer.environment, import_seconds=answer.import_seconds, verify_seconds=answer.verify_seconds, load_seconds=answer.load_seconds
        )
        return cls(worker, expected=expected, limits=limits, ready=ready)

    @property
    def identity(self) -> SemanticModelIdentity:
        return self._expected

    @property
    def ready(self) -> WorkerReady:
        return self._ready

    @property
    def pid(self) -> int:
        return self._worker.process.pid

    @property
    def running(self) -> bool:
        """Whether the worker is up. Every way of stopping it (a failure, a close) ends its process, so this is whether the process is running."""
        return self._worker.running()

    @property
    def exit_code(self) -> int | None:
        """The worker process's exit code, or ``None`` while it runs."""
        return self._worker.process.poll()

    @property
    def requests(self) -> int:
        return self._requests

    @property
    def worker_seconds(self) -> float:
        """The time the worker itself spent embedding, summed over every request it answered."""
        return self._worker_seconds

    @property
    def last_worker_seconds(self) -> float | None:
        return self._last_worker_seconds

    def embed(self, texts: Sequence[str]) -> tuple[EmbeddedText, ...] | EmbedderFailure:
        limits = self._limits
        if not 1 <= len(texts) <= limits.max_texts_per_request:
            return EmbedderFailure(kind=EmbedderFailureKind.REQUEST_REFUSED, message=f"a request holds between 1 and {limits.max_texts_per_request} texts, and this one holds {len(texts)}")
        if not all(1 <= len(text) <= limits.max_text_characters for text in texts):
            return EmbedderFailure(kind=EmbedderFailureKind.REQUEST_REFUSED, message=f"a text is between 1 and {limits.max_text_characters} characters")
        with self._lock:
            if not self._worker.running():
                self._worker.stop()
                return EmbedderFailure(kind=EmbedderFailureKind.UNAVAILABLE, message=f"the worker is not running (exit code {self._worker.process.returncode}){self._worker.tail}")
            request_id, self._next_id = self._next_id, self._next_id + 1
            request = {"type": "embed", "id": request_id, "texts": list(texts)}
            if not self._worker.write(json.dumps(request, ensure_ascii=True, separators=(",", ":")).encode("ascii") + b"\n"):
                self._worker.stop()
                return EmbedderFailure(kind=EmbedderFailureKind.CRASHED, message=f"the worker's input is closed{self._worker.tail}")
            answer = self._worker.message(limits.request_timeout_seconds, what="answer")
            if isinstance(answer, EmbedderFailure):
                return answer
            if isinstance(answer, _RefusedLine):
                return EmbedderFailure(kind=EmbedderFailureKind.REQUEST_REFUSED, message=f"the worker refused the request: {answer.message}")
            if isinstance(answer, _ErrorLine):
                self._worker.stop()
                return EmbedderFailure(kind=EmbedderFailureKind.CRASHED, message=f"the worker reported an error and ended: {answer.message}")
            if not isinstance(answer, _EmbeddedLine) or answer.id != request_id or len(answer.items) != len(texts):
                self._worker.stop()
                return EmbedderFailure(kind=EmbedderFailureKind.MALFORMED_REPLY, message="the worker did not answer this request with one embedded text for each text asked")
            self._requests += 1
            self._last_worker_seconds = answer.seconds
            self._worker_seconds += answer.seconds
            return answer.items

    def close(self) -> None:
        """End the worker: ask it to close, give it a moment, and kill it if it has not ended. Safe to call again."""
        with self._lock:
            self._worker.write(b'{"type":"close"}\n')
            self._worker.stop(grace=STOP_GRACE_SECONDS)

    def __enter__(self) -> "IsolatedEmbedder":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
