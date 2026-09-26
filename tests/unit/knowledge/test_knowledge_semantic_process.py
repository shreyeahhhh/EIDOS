"""The isolated embedder's pure parts: the limits, the command that starts a worker, the worker's environment, and the messages of the protocol (decisions.md D-214, D-222, D-226; V1.3 Step 5).

No process is started here. The behaviour of the client against a running worker (start, embed, every failure, close, the lifetime) is in ``tests/protocol/test_semantic_worker_protocol.py``.
"""

import inspect
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from pydantic import ValidationError

from eidos.knowledge import PINNED_MODEL
from eidos.knowledge import semantic_process as process
from eidos.knowledge.semantic_process import (
    INHERITED_ENVIRONMENT,
    WORKER_SCRIPT,
    WorkerEnvironment,
    WorkerLimits,
    child_environment,
    hub_model_directory,
    semantic_worker_command,
)

READY = {
    "type": "ready",
    "protocol": "eidos-semantic-worker-v1",
    "identity": {"revision": "a" * 40, "weights_sha256": "b" * 64, "directory_sha256": "c" * 64, "dimension": 3, "max_pieces": 10},
    "environment": {"python_version": "3.13.1", "implementation": "CPython", "platform": "p", "libraries": [["lib", "1.0"]], "threads": 1, "evaluation_mode": True, "device": "cpu", "dtype": "float32"},
    "import_seconds": 1.5,
    "verify_seconds": 0.5,
    "load_seconds": 0.25,
}


def parse(message):
    import json

    return process._LINE.validate_json(json.dumps(message))


# --- the limits ------------------------------------------------------------------------------------------------------------------------


def test_the_default_limits_are_the_recorded_ones():
    limits = WorkerLimits()
    assert (limits.ready_timeout_seconds, limits.request_timeout_seconds, limits.idle_timeout_seconds, limits.lifetime_seconds) == (300.0, 120.0, 600.0, 3600.0)
    assert (limits.max_texts_per_request, limits.max_text_characters, limits.max_reply_bytes) == (64, 20000, 4 * 1024 * 1024)


@pytest.mark.parametrize(
    "change",
    [
        {"ready_timeout_seconds": 0.0},
        {"request_timeout_seconds": 0.0},
        {"idle_timeout_seconds": 0.0},
        {"lifetime_seconds": -1.0},
        {"lifetime_seconds": float("inf")},  # a lifetime that never ends is not a bound
        {"idle_timeout_seconds": float("inf")},
        {"ready_timeout_seconds": float("inf")},
        {"request_timeout_seconds": float("inf")},
        {"request_timeout_seconds": float("nan")},
        {"max_texts_per_request": 0},
        {"max_text_characters": 0},
        {"max_reply_bytes": 1023},
        {"idle_timeout_seconds": 300.0},  # not more than the time to start
        {"lifetime_seconds": 300.0},
        {"idle_timeout_seconds": 10.0, "ready_timeout_seconds": 20.0},
    ],
)
def test_a_limit_must_be_positive_and_a_worker_must_be_able_to_start_before_it_expires(change):
    with pytest.raises(ValidationError):
        WorkerLimits(**change)


def test_the_smallest_allowed_limits_are_allowed():
    limits = WorkerLimits(
        ready_timeout_seconds=0.1, request_timeout_seconds=0.1, idle_timeout_seconds=0.3, lifetime_seconds=0.5, max_texts_per_request=1, max_text_characters=1, max_reply_bytes=1024
    )
    assert (limits.ready_timeout_seconds, limits.request_timeout_seconds, limits.idle_timeout_seconds, limits.lifetime_seconds) == (0.1, 0.1, 0.3, 0.5)
    assert (limits.max_texts_per_request, limits.max_text_characters, limits.max_reply_bytes) == (1, 1, 1024)


def test_the_smallest_reply_bound_and_a_lifetime_just_over_the_start_time_are_allowed():
    assert WorkerLimits(max_reply_bytes=1024, idle_timeout_seconds=300.001, lifetime_seconds=300.001).max_reply_bytes == 1024


# --- the command -----------------------------------------------------------------------------------------------------------------------


def test_the_command_is_the_isolated_interpreter_the_script_the_directory_what_it_must_verify_and_every_bound():
    limits = WorkerLimits(ready_timeout_seconds=10.0, idle_timeout_seconds=20.0, lifetime_seconds=30.5, max_texts_per_request=7, max_text_characters=99)
    command = semantic_worker_command("C:/py/python.exe", Path("models/rev"), PINNED_MODEL, limits)
    assert command == (
        "C:/py/python.exe",
        "-I",
        str(WORKER_SCRIPT),
        "--model-dir",
        str(Path("models/rev")),
        "--expect-revision",
        PINNED_MODEL.revision,
        "--expect-weights-sha256",
        PINNED_MODEL.weights_sha256,
        "--expect-directory-sha256",
        PINNED_MODEL.directory_sha256,
        "--lifetime-seconds",
        "30.5",
        "--idle-seconds",
        "20.0",
        "--max-texts",
        "7",
        "--max-text-chars",
        "99",
    )


def test_a_worker_gets_a_console_window_of_its_own_nowhere_and_is_not_given_one_on_windows():
    assert process.creation_flags("linux") == 0 and process.creation_flags("darwin") == 0
    assert process.creation_flags("win32") == getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if sys.platform == "win32":
        assert process.creation_flags("win32") == 0x08000000


def test_a_process_is_stopped_at_once_unless_it_is_given_time_to_end():
    assert inspect.signature(process._Worker.stop).parameters["grace"].default == 0.0


def test_what_a_worker_says_on_stderr_is_kept_only_to_the_last_two_thousand_bytes():
    child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stderr.write('a' * 5000 + 'b' * 10); sys.stderr.flush()"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    worker = process._Worker(child, WorkerLimits())
    assert worker.lines.get(timeout=30) is process._END
    worker._stderr_pump.join(timeout=30)
    assert len(worker.stderr) == process.STDERR_TAIL_BYTES == 2000 and bytes(worker.stderr).endswith(b"a" * 1990 + b"b" * 10)
    worker.stop()


def test_the_reader_threads_are_daemons_so_a_program_that_never_closes_its_embedder_can_still_exit():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    before = set(threading.enumerate())
    worker = process._Worker(child, WorkerLimits())
    started = [thread for thread in threading.enumerate() if thread not in before]
    try:
        assert len(started) == 2 and all(thread.daemon for thread in started)
    finally:
        worker.stop()


def test_the_fixed_constants_of_the_boundary():
    """Fixed a priori and recorded (D-226): how long a worker is given to end after it is asked to close, how much of its last words are kept, the protocol and the names of the environment it is given."""
    assert (process.STOP_GRACE_SECONDS, process.STDERR_TAIL_BYTES, process.PROTOCOL) == (2.0, 2000, "eidos-semantic-worker-v1")
    assert INHERITED_ENVIRONMENT == (
        "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "TEMP", "TMP", "USERPROFILE", "HOME", "LOCALAPPDATA", "APPDATA", "LANG", "LC_ALL",
    )


def test_the_worker_script_is_the_file_beside_the_module_and_the_script_can_be_replaced():
    assert WORKER_SCRIPT == Path(process.__file__).with_name("semantic_worker.py") and WORKER_SCRIPT.is_file()
    assert semantic_worker_command(sys.executable, Path("m"), PINNED_MODEL, WorkerLimits(), script=Path("other.py"))[2] == "other.py"
    assert semantic_worker_command(Path("py"), Path("m"), PINNED_MODEL, WorkerLimits())[0] == "py"


def test_the_command_is_deterministic():
    args = (sys.executable, Path("m"), PINNED_MODEL, WorkerLimits())
    assert semantic_worker_command(*args) == semantic_worker_command(*args)


def test_the_cache_directory_of_a_model_revision():
    assert hub_model_directory(Path("hub"), "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "abc") == (
        Path("hub") / "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2" / "snapshots" / "abc"
    )
    assert hub_model_directory(Path("hub"), "plain-name", "r") == Path("hub") / "models--plain-name" / "snapshots" / "r"


# --- the worker's environment ----------------------------------------------------------------------------------------------------------


def test_only_the_named_variables_the_caller_has_reach_the_worker_and_nothing_else(monkeypatch):
    for name in INHERITED_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PATH", "/bin")
    monkeypatch.setenv("TEMP", "/tmp")
    monkeypatch.setenv("SECRET_TOKEN", "hunter2")
    monkeypatch.setenv("PYTHONPATH", "/somewhere")
    monkeypatch.setenv("HF_TOKEN", "hf_secret")
    assert child_environment() == {"PATH": "/bin", "TEMP": "/tmp"}


def test_extra_variables_are_added_and_win_over_inherited_ones(monkeypatch):
    monkeypatch.setenv("TEMP", "/tmp")
    assert child_environment({"TEMP": "/other", "MARK": "1"})["TEMP"] == "/other"
    assert child_environment({"MARK": "1"})["MARK"] == "1"


def test_the_inherited_names_are_what_an_interpreter_needs_and_no_credentials():
    assert "SYSTEMROOT" in INHERITED_ENVIRONMENT and "PATH" in INHERITED_ENVIRONMENT
    assert not [name for name in INHERITED_ENVIRONMENT if any(part in name for part in ("TOKEN", "KEY", "SECRET", "PASSWORD", "PYTHON", "HF_"))]


# --- the messages of the protocol ------------------------------------------------------------------------------------------------------


def test_a_ready_message_is_parsed_with_its_identity_environment_and_times():
    message = parse(READY)
    assert message.identity.dimension == 3 and message.identity.max_pieces == 10
    assert message.environment == WorkerEnvironment(
        python_version="3.13.1", implementation="CPython", platform="p", libraries=(("lib", "1.0"),), threads=1, evaluation_mode=True, device="cpu", dtype="float32"
    )
    assert (message.import_seconds, message.verify_seconds, message.load_seconds) == (1.5, 0.5, 0.25)


def test_an_embedded_message_carries_integer_or_float_components_and_a_null_vector_for_a_refused_text():
    message = parse({"type": "embedded", "id": 3, "seconds": 0.5, "items": [{"pieces": 4, "vector": [1, 2.5, -3]}, {"pieces": 200, "vector": None}]})
    assert message.id == 3 and message.items[0].vector == (1.0, 2.5, -3.0) and message.items[1].vector is None and message.items[1].pieces == 200


@pytest.mark.parametrize(
    "message",
    [
        {"type": "unknown"},
        {},
        READY | {"surprise": 1},
        READY | {"import_seconds": -1.0},
        READY | {"identity": READY["identity"] | {"dimension": "3"}},
        {k: v for k, v in READY.items() if k != "environment"},
        READY | {"environment": READY["environment"] | {"threads": 0}},
        READY | {"environment": {k: v for k, v in READY["environment"].items() if k != "evaluation_mode"}},
        {"type": "failed", "reason": "x"},
        {"type": "embedded", "id": "3", "seconds": 0.0, "items": []},
        {"type": "embedded", "id": 3, "seconds": -0.5, "items": []},
        {"type": "embedded", "id": 3, "seconds": 0.0, "items": [{"pieces": 0, "vector": None}]},
        {"type": "embedded", "id": 3, "seconds": 0.0, "items": [{"pieces": 3, "vector": ["a"]}]},
        {"type": "embedded", "id": 3, "seconds": 0.0, "items": [{"pieces": 3, "vector": [True]}]},
        {"type": "embedded", "id": 3, "seconds": 0.0, "items": [{"pieces": 3}], "extra": 1},
        {"type": "refused", "message": "no id key"},
        {"type": "error", "id": None, "message": "an error has an id"},
    ],
)
def test_a_message_that_is_not_one_of_the_protocol_is_rejected(message):
    with pytest.raises(ValidationError):
        parse(message)


def test_a_refused_message_may_have_a_null_id_and_an_error_message_has_an_integer_id():
    assert parse({"type": "refused", "id": None, "message": "m"}).id is None
    assert parse({"type": "refused", "id": 4, "message": "m"}).id == 4
    assert parse({"type": "error", "id": 4, "message": "m"}).id == 4
    assert parse({"type": "failed", "reason": "model_missing", "message": "m"}).reason == "model_missing"


def test_a_line_that_is_not_json_is_rejected():
    for payload in (b"", b"not json", b"[1,2", b'{"type":"ready"'):
        with pytest.raises(ValidationError):
            process._LINE.validate_json(payload)


def test_every_reason_the_worker_can_fail_with_has_a_typed_failure():
    reasons = {"identity_mismatch", "model_missing", "library_missing", "load_failed"}
    assert set(process._FAILURE_OF_REASON) == reasons


def test_the_tail_of_a_workers_output_is_bounded_and_readable():
    assert process._tail(b"") == "" and process._tail(b"   \n") == ""
    assert process._tail(b"boom\n") == "; its last output: boom"
    assert process._tail(b"x" * 5000).endswith("x" * 2000) and len(process._tail(b"x" * 5000)) == len("; its last output: ") + 2000
    assert process._tail(bytes([0xFF, 0x62])).endswith("b")  # bytes that are not UTF-8 do not break it
