"""The semantic process boundary: the client against a running worker, in every way the worker can behave (decisions.md D-214, D-222, D-226; V1.3 Step 5).

The worker that runs is the real ``semantic_worker.py`` with its model replaced by a stub (``fake_semantic_worker.py``), so the protocol loop, the digest verification, the network refusal, the offline
flags and the watchdog are the real ones and no model library is needed; a worker that breaks the protocol in one scripted way (``misbehaving_semantic_worker.py``) covers the rest. What is proven: an
honest worker is served deterministically; a model that is not the pinned one is refused before anything is embedded; a timeout, a crash, an oversize or malformed or out-of-step reply, a worker that
will not serve and a worker that is not there each become a typed failure and stop the worker, and nothing is raised; a stopped embedder never restarts; the worker ends by itself when its lifetime
or idle time is over, when its input closes, and when it is asked to; nothing of the caller's environment reaches it; and it cannot open a network connection.
"""

import math
import socket
import subprocess
import sys
import threading
import time

import pytest

from eidos.knowledge import (
    EmbeddedText,
    EmbedderFailure,
    EmbedderFailureKind,
    RetrievalFailure,
    RetrievalFailureKind,
    RetrievalRequest,
    RetrievalResult,
    SemanticKnowledgePort,
    build_snapshot,
    semantic_scheme_id,
)
from eidos.knowledge.semantic_process import IsolatedEmbedder, WorkerLimits
from eidos_knowledge_factories import SCHEME, doc
from eidos_semantic_process_factories import FAKE_WORKER, FAST, ROOT, fake_command, make_fake_model, misbehaving_command
from fake_semantic_worker import DIMENSION, MAX_PIECES, stub_vector

KINDS = EmbedderFailureKind
SHORT = WorkerLimits(ready_timeout_seconds=10.0, request_timeout_seconds=1.0, idle_timeout_seconds=60.0, lifetime_seconds=120.0)


@pytest.fixture()
def model(tmp_path):
    return make_fake_model(tmp_path)


@pytest.fixture()
def embedder(model):
    directory, identity = model
    started = IsolatedEmbedder.start(fake_command(directory, identity), expected=identity, limits=FAST)
    assert isinstance(started, IsolatedEmbedder), started
    yield started
    started.close()


def start(command, identity, limits=FAST, **kwargs):
    return IsolatedEmbedder.start(command, expected=identity, limits=limits, **kwargs)


def failed(result, kind, *parts):
    assert isinstance(result, EmbedderFailure), result
    assert result.kind is kind, result
    for part in parts:
        assert part in result.message, (part, result.message)


# --- an honest worker ------------------------------------------------------------------------------------------------------------------


def test_a_worker_starts_reports_what_it_measured_and_serves_the_identity_it_was_pinned_to(model, embedder):
    _, identity = model
    assert embedder.identity == identity and embedder.running and embedder.pid > 0
    ready = embedder.ready
    assert ready.identity == identity
    assert ready.environment.implementation == "stub" and ready.environment.threads == 1 and ready.environment.device == "cpu" and ready.environment.dtype == "float32"
    assert ready.environment.python_version == sys.version.split()[0]
    assert ready.environment.evaluation_mode is True
    assert ready.import_seconds == 0.0 and ready.load_seconds == 0.0 and 0.0 <= ready.verify_seconds < 30.0  # a duration, not a reading of the clock


def test_texts_come_back_in_order_with_their_pieces_and_the_stubs_deterministic_vectors(embedder):
    items = embedder.embed(["alpha", "alpha beta gamma", "delta"])
    assert isinstance(items, tuple) and len(items) == 3
    assert [item.pieces for item in items] == [3, 5, 3]
    assert [item.vector for item in items] == [tuple(stub_vector(text)) for text in ("alpha", "alpha beta gamma", "delta")]
    assert all(len(item.vector) == DIMENSION for item in items)


def test_texts_with_accents_other_scripts_and_astral_characters_arrive_intact(embedder):
    texts = ["caf" + chr(0xE9), chr(0x65E5) + chr(0x672C) + chr(0x8A9E), "smile " + chr(0x1F600), "line" + chr(10) + "break", 'quote " and back' + chr(92) + "slash"]
    items = embedder.embed(texts)
    assert [item.vector for item in items] == [tuple(stub_vector(text)) for text in texts]  # the stub's vector is a digest of the exact text it received


def test_a_text_at_the_window_is_embedded_and_a_text_over_it_or_marked_long_is_refused_never_truncated(embedder):
    at_window = " ".join(["w"] * (MAX_PIECES - 2))
    over_window = " ".join(["w"] * (MAX_PIECES - 1))
    items = embedder.embed([at_window, over_window, "!long"])
    assert items[0].pieces == MAX_PIECES and items[0].vector is not None
    assert items[1] == EmbeddedText(pieces=MAX_PIECES + 1, vector=None)
    assert items[2] == EmbeddedText(pieces=10_000, vector=None)
    assert embedder.running  # a refused text is not a failure of the worker


def test_the_same_text_gives_the_same_vector_in_the_same_worker_and_in_another_worker(model, embedder):
    directory, identity = model
    first = embedder.embed(["alpha beta"])
    assert embedder.embed(["alpha beta"]) == first
    other = start(fake_command(directory, identity), identity)
    try:
        assert other.embed(["alpha beta"]) == first
    finally:
        other.close()


def test_requests_and_the_time_the_worker_spent_are_counted(embedder):
    assert embedder.requests == 0 and embedder.worker_seconds == 0.0 and embedder.last_worker_seconds is None
    embedder.embed(["alpha"])
    embedder.embed(["beta", "gamma"])
    assert embedder.requests == 2
    assert embedder.last_worker_seconds is not None and embedder.last_worker_seconds >= 0.0
    assert embedder.worker_seconds >= embedder.last_worker_seconds


def test_several_threads_asking_at_once_each_get_their_own_answer(embedder):
    results, errors = {}, []

    def ask(number):
        try:
            text = f"text number {number}"
            results[number] = (text, embedder.embed([text]))
        except Exception as error:  # pragma: no cover - reported below
            errors.append(error)

    threads = [threading.Thread(target=ask, args=(n,)) for n in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors and len(results) == 12
    for text, items in results.values():
        assert items[0].vector == tuple(stub_vector(text))
    assert embedder.requests == 12


def test_close_ends_the_process_and_is_safe_to_repeat_and_an_embedder_that_was_closed_answers_unavailable(model):
    directory, identity = model
    embedder = start(fake_command(directory, identity), identity)
    assert embedder.running
    embedder.close()
    embedder.close()
    assert not embedder.running
    failed(embedder.embed(["alpha"]), KINDS.UNAVAILABLE, "not running")


def test_a_worker_that_is_asked_to_close_ends_by_itself_with_the_exit_code_of_a_clean_end(model):
    directory, identity = model
    embedder = start(fake_command(directory, identity), identity)
    assert embedder.exit_code is None
    embedder.close()
    assert embedder.exit_code == 0  # it was not killed: a killed worker has another code


def test_a_worker_that_does_not_end_when_asked_to_close_is_killed_after_the_grace_period(model):
    _, identity = model
    embedder = serving("ignore_close", identity)
    started = time.monotonic()
    embedder.close()
    assert not embedder.running and embedder.exit_code not in (None, 0)
    assert 1.5 < time.monotonic() - started < 15  # it was given its two seconds, and no more than that


def test_used_as_a_context_manager_the_worker_is_closed_on_leaving(model):
    directory, identity = model
    with start(fake_command(directory, identity), identity) as embedder:
        assert embedder.embed(["alpha"])
    assert not embedder.running


# --- a request the client will not send, or the worker will not take ---------------------------------------------------------------------


def test_a_request_outside_the_limits_is_refused_by_the_client_and_the_worker_is_not_asked(model):
    directory, identity = model
    limits = WorkerLimits(ready_timeout_seconds=10.0, idle_timeout_seconds=60.0, lifetime_seconds=120.0, max_texts_per_request=2, max_text_characters=5)
    with start(fake_command(directory, identity, limits), identity, limits) as embedder:
        failed(embedder.embed([]), KINDS.REQUEST_REFUSED, "between 1 and 2 texts", "holds 0")
        failed(embedder.embed(["a", "b", "c"]), KINDS.REQUEST_REFUSED, "between 1 and 2 texts", "holds 3")
        failed(embedder.embed(["abcdef"]), KINDS.REQUEST_REFUSED, "between 1 and 5 characters")
        failed(embedder.embed(["ok", ""]), KINDS.REQUEST_REFUSED, "between 1 and 5 characters")
        assert embedder.requests == 0
        assert len(embedder.embed(["a", "abcde"])) == 2  # exactly at the limits
        assert embedder.running


def test_a_request_the_worker_refuses_is_a_refusal_and_the_embedder_stays_usable(model):
    directory, identity = model
    limits = WorkerLimits(ready_timeout_seconds=10.0, idle_timeout_seconds=60.0, lifetime_seconds=120.0, max_texts_per_request=8)
    with start(fake_command(directory, identity, limits, max_texts=2), identity, limits) as embedder:  # the worker takes 2 texts, the client would send 8
        failed(embedder.embed(["a", "b", "c"]), KINDS.REQUEST_REFUSED, "the worker refused the request", "between 1 and 2 texts")
        assert embedder.running and len(embedder.embed(["a", "b"])) == 2


# --- a worker that fails while it serves -----------------------------------------------------------------------------------------------


def test_a_worker_that_crashes_is_a_typed_failure_and_the_embedder_then_answers_unavailable(model):
    directory, identity = model
    embedder = start(fake_command(directory, identity), identity)
    result = embedder.embed(["!crash"])
    failed(result, KINDS.CRASHED)
    assert result.message == "the worker ended without answering (exit code 9)"  # exactly: it said nothing, so there is no last output to add
    assert not embedder.running
    follow_up = embedder.embed(["alpha"])
    failed(follow_up, KINDS.UNAVAILABLE)
    assert follow_up.message == "the worker is not running (exit code 9)"


@pytest.mark.parametrize("text", ["!error", "!nan"])
def test_a_model_that_fails_or_answers_a_vector_that_is_not_finite_is_reported_by_the_worker_which_then_ends(model, text):
    directory, identity = model
    embedder = start(fake_command(directory, identity), identity)
    failed(embedder.embed([text]), KINDS.CRASHED, "reported an error and ended")
    assert not embedder.running
    failed(embedder.embed(["alpha"]), KINDS.UNAVAILABLE)


def test_a_worker_that_does_not_answer_in_time_is_stopped_and_the_call_returns_a_timeout(model):
    directory, identity = model
    embedder = start(fake_command(directory, identity, SHORT), identity, SHORT)
    started = time.monotonic()
    failed(embedder.embed(["!sleep:30"]), KINDS.TIMEOUT, "did not answer within 1.0 seconds", "stopped")
    assert time.monotonic() - started < 10
    assert not embedder.running and embedder.exit_code is not None  # the process was killed and reaped, not left behind
    failed(embedder.embed(["alpha"]), KINDS.UNAVAILABLE)


def test_a_worker_whose_input_is_closed_is_a_crash_and_not_a_wait_for_an_answer_that_will_never_come(model):
    _, identity = model
    embedder = serving("close_input", identity)
    time.sleep(1.0)  # it has closed its input by now
    result = embedder.embed(["a"])
    failed(result, KINDS.CRASHED, "the worker's input is closed")
    assert not embedder.running and embedder.exit_code is not None
    failed(embedder.embed(["a"]), KINDS.UNAVAILABLE, "not running")


def test_a_program_that_never_closes_its_embedder_still_exits_by_itself(model):
    directory, identity = model
    story = """
import sys
sys.path[:0] = ['src', 'tests/support']
from eidos.knowledge import SemanticModelIdentity
from eidos.knowledge.semantic_process import IsolatedEmbedder
from eidos_semantic_process_factories import FAST, fake_command
identity = SemanticModelIdentity.model_validate_json(sys.argv[2])
embedder = IsolatedEmbedder.start(fake_command(sys.argv[1], identity), expected=identity, limits=FAST)
assert isinstance(embedder, IsolatedEmbedder), embedder
print(embedder.embed(['a'])[0].pieces)
"""
    completed = subprocess.run([sys.executable, "-c", story, str(directory), identity.model_dump_json()], cwd=ROOT, capture_output=True, text=True, timeout=45)
    assert completed.returncode == 0 and completed.stdout.strip() == "3", completed.stderr


def test_a_worker_that_ends_by_itself_between_requests_is_noticed_and_never_restarted(model):
    directory, identity = model
    embedder = start(fake_command(directory, identity, idle_seconds=1.2), identity)  # ends after 1.2 s without a request
    assert embedder.embed(["alpha"])
    deadline = time.monotonic() + 10
    while embedder.running and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not embedder.running  # noticed as soon as the process ended, before anything was asked of it
    result = embedder.embed(["alpha"])
    failed(result, KINDS.UNAVAILABLE)
    assert result.message == "the worker is not running (exit code 4)"
    assert not embedder.running
    assert embedder._worker.process.stdin.closed and embedder._worker.process.stdout.closed and embedder._worker.process.stderr.closed  # noticing that it ended also closed its pipes


# --- a worker that will not serve: at the start ----------------------------------------------------------------------------------------


def test_a_model_directory_whose_weights_are_not_the_pinned_ones_is_refused_before_anything_is_embedded(tmp_path):
    directory, identity = make_fake_model(tmp_path)
    other = identity.model_copy(update={"weights_sha256": "0" * 64})
    failed(start(fake_command(directory, other), other), KINDS.IDENTITY_MISMATCH, "identity_mismatch", "weights digest")


def test_a_model_directory_whose_files_are_not_the_pinned_ones_is_refused(tmp_path):
    directory, identity = make_fake_model(tmp_path)
    other = identity.model_copy(update={"directory_sha256": "0" * 64})
    failed(start(fake_command(directory, other), other), KINDS.IDENTITY_MISMATCH, "directory digest")


def test_a_model_directory_that_is_not_the_pinned_revision_is_refused(tmp_path):
    directory, identity = make_fake_model(tmp_path)
    other = identity.model_copy(update={"revision": "f" * 40})
    failed(start(fake_command(directory, other), other), KINDS.IDENTITY_MISMATCH, "revision")


def test_a_worker_whose_model_has_another_dimension_or_window_than_pinned_is_refused_and_stopped(model):
    directory, identity = model
    for change in ({"dimension": identity.dimension + 1}, {"max_pieces": identity.max_pieces + 1}):
        other = identity.model_copy(update=change)
        failed(start(fake_command(directory, other), other), KINDS.IDENTITY_MISMATCH, next(iter(change)))


def test_a_missing_model_directory_and_a_directory_without_weights_are_unavailable(tmp_path):
    directory, identity = make_fake_model(tmp_path)
    missing = tmp_path / identity.revision.replace("0", "1")
    failed(start(fake_command(missing, identity), identity), KINDS.UNAVAILABLE, "model_missing", "does not exist")
    bare, bare_identity = make_fake_model(tmp_path / "bare", {"config.json": b"{}"})
    failed(start(fake_command(bare, bare_identity), bare_identity), KINDS.UNAVAILABLE, "model_missing", "model.safetensors")


def test_a_missing_interpreter_is_unavailable_and_a_missing_script_is_a_crash_with_the_interpreters_message(model):
    directory, identity = model
    failed(start(("no/such/interpreter.exe", "-I", str(FAKE_WORKER)), identity), KINDS.UNAVAILABLE, "cannot be started")
    command = fake_command(directory, identity)
    missing_script = (command[0], "-I", str(FAKE_WORKER) + ".missing") + command[3:]
    failed(start(missing_script, identity), KINDS.CRASHED, "ended without answering (exit code 2)", "last output")


def test_a_worker_that_ends_before_it_is_ready_reports_its_exit_code_and_what_it_said(model):
    _, identity = model
    failed(start(misbehaving_command("exit", identity), identity), KINDS.CRASHED, "(exit code 7)", "scripted early exit")


def test_a_worker_that_is_not_ready_in_time_is_stopped(model):
    _, identity = model
    limits = WorkerLimits(ready_timeout_seconds=1.0, request_timeout_seconds=1.0, idle_timeout_seconds=60.0, lifetime_seconds=120.0)
    started = time.monotonic()
    failed(start(misbehaving_command("hang", identity), identity, limits), KINDS.TIMEOUT, "did not become ready within 1.0 seconds")
    assert time.monotonic() - started < 10


@pytest.mark.parametrize(
    ("mode", "kind", "part"),
    [
        ("garbage", KINDS.MALFORMED_REPLY, "not a message of the protocol"),
        ("bad_protocol", KINDS.MALFORMED_REPLY, "ready message of protocol"),
        ("wrong_type", KINDS.MALFORMED_REPLY, "ready message of protocol"),
        ("extra_field", KINDS.MALFORMED_REPLY, "not a message of the protocol"),
        ("partial_ready", KINDS.CRASHED, "ended without answering"),
        ("failed_identity_mismatch", KINDS.IDENTITY_MISMATCH, "scripted refusal"),
        ("failed_model_missing", KINDS.UNAVAILABLE, "model_missing"),
        ("failed_library_missing", KINDS.UNAVAILABLE, "library_missing"),
        ("failed_load_failed", KINDS.UNAVAILABLE, "load_failed"),
        ("failed_a_reason_nobody_knows", KINDS.MALFORMED_REPLY, "a_reason_nobody_knows"),
        ("identity_revision", KINDS.IDENTITY_MISMATCH, "revision"),
        ("identity_weights_sha256", KINDS.IDENTITY_MISMATCH, "weights_sha256"),
        ("identity_directory_sha256", KINDS.IDENTITY_MISMATCH, "directory_sha256"),
        ("identity_dimension", KINDS.IDENTITY_MISMATCH, "dimension"),
        ("identity_max_pieces", KINDS.IDENTITY_MISMATCH, "max_pieces"),
    ],
)
def test_a_start_that_breaks_the_protocol_or_reports_the_wrong_model_is_a_typed_failure(model, mode, kind, part):
    _, identity = model
    failed(start(misbehaving_command(mode, identity), identity), kind, part)


# --- a worker that breaks the protocol while it serves ---------------------------------------------------------------------------------


def serving(mode, identity, limits=FAST):
    embedder = start(misbehaving_command(mode, identity), identity, limits)
    assert isinstance(embedder, IsolatedEmbedder), embedder
    return embedder


def test_an_honest_scripted_worker_is_served(model):
    _, identity = model
    with serving("ok", identity) as embedder:
        items = embedder.embed(["a", "b"])
        assert [item.vector[0] for item in items] == [1.0, 1.0] and embedder.last_worker_seconds == 0.125


@pytest.mark.parametrize(
    ("mode", "kind", "part"),
    [
        ("wrong_id", KINDS.MALFORMED_REPLY, "one embedded text for each text asked"),
        ("short_items", KINDS.MALFORMED_REPLY, "one embedded text for each text asked"),
        ("too_many_items", KINDS.MALFORMED_REPLY, "one embedded text for each text asked"),
        ("garbage_reply", KINDS.MALFORMED_REPLY, "not a message of the protocol"),
        ("oversize_reply", KINDS.MALFORMED_REPLY, "exceeds 4194304 bytes"),
        ("partial_reply", KINDS.CRASHED, "ended without answering"),
        ("error_reply", KINDS.CRASHED, "scripted internal error"),
        ("eof_reply", KINDS.CRASHED, "ended without answering"),
    ],
)
def test_a_reply_that_breaks_the_protocol_is_a_typed_failure_stops_the_worker_and_the_embedder_never_restarts(model, mode, kind, part):
    _, identity = model
    embedder = serving(mode, identity)
    failed(embedder.embed(["a", "b"]), kind, part)
    assert not embedder.running
    failed(embedder.embed(["a"]), KINDS.UNAVAILABLE, "not running")


def test_requests_are_numbered_from_one_in_order(model):
    _, identity = model
    with serving("echo_id", identity) as embedder:
        assert [embedder.embed(["a"])[0].pieces for _ in range(3)] == [1, 2, 3]


def test_a_worker_that_refuses_a_request_is_a_refusal_and_is_not_stopped(model):
    _, identity = model
    with serving("refused_reply", identity) as embedder:
        failed(embedder.embed(["a"]), KINDS.REQUEST_REFUSED, "scripted refusal")
        assert embedder.running
        failed(embedder.embed(["a"]), KINDS.REQUEST_REFUSED, "scripted refusal")


def test_a_worker_whose_output_ends_but_which_ends_a_moment_later_is_reported_with_its_own_exit_code_and_what_it_said(model):
    _, identity = model
    embedder = serving("slow_exit", identity)
    failed(embedder.embed(["a"]), KINDS.CRASHED, "(exit code 7)", "scripted slow exit")  # it was waited for, not killed for being slow to end


def test_a_worker_that_has_closed_all_its_output_and_ends_a_moment_later_is_still_waited_for_and_reported_with_its_own_exit_code(model):
    _, identity = model
    embedder = serving("quiet_slow_exit", identity)
    result = embedder.embed(["a"])
    failed(result, KINDS.CRASHED, "ended without answering (exit code 7)")
    assert "last output" not in result.message  # it said nothing


@pytest.mark.parametrize(("mode", "accepted"), [("reply_at_bound", True), ("reply_over_bound", False)])
def test_a_reply_of_exactly_the_bound_is_read_and_one_byte_more_is_refused(model, mode, accepted):
    _, identity = model
    limits = WorkerLimits(ready_timeout_seconds=10.0, request_timeout_seconds=5.0, idle_timeout_seconds=60.0, lifetime_seconds=120.0, max_reply_bytes=2048)
    embedder = start(misbehaving_command(mode, identity) + ("2048",), identity, limits)
    try:
        result = embedder.embed(["a"])
        if accepted:
            assert isinstance(result, tuple) and len(result) == 1
        else:
            failed(result, KINDS.MALFORMED_REPLY, "exceeds 2048 bytes")
    finally:
        embedder.close()


def test_a_worker_that_hangs_on_a_request_is_stopped_at_the_request_timeout(model):
    _, identity = model
    embedder = serving("hang_reply", identity, SHORT)
    failed(embedder.embed(["a"]), KINDS.TIMEOUT, "did not answer within 1.0 seconds")
    assert not embedder.running


def test_a_vector_that_is_not_finite_in_a_reply_reaches_the_port_which_refuses_it(model):
    _, identity = model
    snapshot = build_snapshot((doc("s1", "alpha beta"),), SCHEME)
    with serving("nan_reply", identity) as embedder:
        assert math.isnan(embedder.embed(["a"])[0].vector[0])  # it came through the client as a number the port then refuses
        port = SemanticKnowledgePort.open(snapshot, kb_id="kb1", embedder=embedder)
    assert isinstance(port, RetrievalFailure) and port.kind is RetrievalFailureKind.MALFORMED_RESULT and "not a finite number" in port.message


@pytest.mark.parametrize(
    ("mode", "kind"),
    [
        ("wrong_id", RetrievalFailureKind.MALFORMED_RESULT),
        ("garbage_reply", RetrievalFailureKind.MALFORMED_RESULT),
        ("oversize_reply", RetrievalFailureKind.MALFORMED_RESULT),
        ("partial_reply", RetrievalFailureKind.UNAVAILABLE),
        ("error_reply", RetrievalFailureKind.UNAVAILABLE),
        ("refused_reply", RetrievalFailureKind.REQUEST_MISMATCH),
        ("eof_reply", RetrievalFailureKind.UNAVAILABLE),
    ],
)
def test_a_worker_that_breaks_the_protocol_becomes_a_typed_retrieval_failure_and_never_an_exception(model, mode, kind):
    _, identity = model
    snapshot = build_snapshot((doc("s1", "alpha beta"),), SCHEME)
    with serving(mode, identity) as embedder:
        result = SemanticKnowledgePort.open(snapshot, kb_id="kb1", embedder=embedder)
    assert isinstance(result, RetrievalFailure) and result.kind is kind


class RecordingPopen(subprocess.Popen):
    instances: list = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        RecordingPopen.instances.append(self)


def assert_nothing_is_left_behind(processes):
    assert processes, "a worker was started"
    for process in processes:
        assert process.poll() is not None, "the worker process is still running"
        assert process.stdin.closed and process.stdout.closed and process.stderr.closed, "a pipe of the worker was left open"


START_MODES = [
    "garbage", "bad_protocol", "wrong_type", "extra_field", "partial_ready", "failed_identity_mismatch", "failed_model_missing", "failed_a_reason_nobody_knows", "identity_revision",
    "identity_weights_sha256", "identity_directory_sha256", "identity_dimension", "identity_max_pieces", "exit",
]
SERVE_MODES = ["wrong_id", "short_items", "too_many_items", "garbage_reply", "oversize_reply", "partial_reply", "error_reply", "eof_reply"]


@pytest.mark.parametrize("mode", START_MODES)
def test_a_worker_that_fails_at_the_start_is_stopped_reaped_and_its_pipes_closed(model, monkeypatch, mode):
    _, identity = model
    RecordingPopen.instances = []
    monkeypatch.setattr(subprocess, "Popen", RecordingPopen)
    assert isinstance(start(misbehaving_command(mode, identity), identity), EmbedderFailure)
    assert_nothing_is_left_behind(RecordingPopen.instances)


@pytest.mark.parametrize("mode", SERVE_MODES)
def test_a_worker_that_fails_while_it_serves_is_stopped_reaped_and_its_pipes_closed(model, monkeypatch, mode):
    _, identity = model
    RecordingPopen.instances = []
    monkeypatch.setattr(subprocess, "Popen", RecordingPopen)
    embedder = serving(mode, identity)
    assert isinstance(embedder.embed(["a", "b"]), EmbedderFailure)
    assert_nothing_is_left_behind(RecordingPopen.instances)


def test_a_worker_that_never_becomes_ready_and_one_that_never_answers_are_stopped_reaped_and_their_pipes_closed(model, monkeypatch):
    _, identity = model
    RecordingPopen.instances = []
    monkeypatch.setattr(subprocess, "Popen", RecordingPopen)
    quick = WorkerLimits(ready_timeout_seconds=1.0, request_timeout_seconds=1.0, idle_timeout_seconds=60.0, lifetime_seconds=120.0)
    assert isinstance(start(misbehaving_command("hang", identity), identity, quick), EmbedderFailure)
    silent = serving("hang_reply", identity, quick)
    assert isinstance(silent.embed(["a"]), EmbedderFailure)
    assert_nothing_is_left_behind(RecordingPopen.instances)


def test_a_worker_that_is_closed_is_reaped_and_its_pipes_closed(model, monkeypatch):
    directory, identity = model
    RecordingPopen.instances = []
    monkeypatch.setattr(subprocess, "Popen", RecordingPopen)
    with start(fake_command(directory, identity), identity) as embedder:
        assert embedder.embed(["a"])
    assert_nothing_is_left_behind(RecordingPopen.instances)


# --- the lifetime of a worker ----------------------------------------------------------------------------------------------------------


def run_worker(command):
    return subprocess.Popen(list(command), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def wait_for_exit(process, seconds):
    try:
        return process.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        pytest.fail(f"the worker was still running after {seconds} seconds")


def test_a_worker_ends_by_itself_when_its_lifetime_is_over(model):
    directory, identity = model
    process = run_worker(fake_command(directory, identity, lifetime_seconds=1.5))
    try:
        assert process.stdout.readline().startswith(b'{"type":"ready"')
        assert wait_for_exit(process, 15) == 4
    finally:
        process.kill()


def test_a_worker_that_is_asked_nothing_ends_after_its_idle_time_and_one_that_is_kept_busy_does_not(model):
    directory, identity = model
    idle = run_worker(fake_command(directory, identity, idle_seconds=1.5))
    busy = run_worker(fake_command(directory, identity, idle_seconds=1.5))
    try:
        assert idle.stdout.readline() and busy.stdout.readline()
        for number in range(1, 8):  # a request every half second, for more than twice the idle time
            busy.stdin.write((f'{{"type":"embed","id":{number},"texts":["a"]}}' + chr(10)).encode())
            busy.stdin.flush()
            assert busy.stdout.readline().startswith(b'{"type":"embedded"')
            time.sleep(0.5)
        assert wait_for_exit(idle, 15) == 4  # the one nobody asked has ended, with the watchdog's exit code
        assert busy.poll() is None  # and the busy one is still up
    finally:
        idle.kill()
        busy.kill()


def test_a_worker_ends_by_itself_when_its_input_is_closed_and_when_it_is_told_to_close(model):
    directory, identity = model
    closed, told = run_worker(fake_command(directory, identity)), run_worker(fake_command(directory, identity))
    try:
        assert closed.stdout.readline() and told.stdout.readline()
        closed.stdin.close()
        assert wait_for_exit(closed, 15) == 0
        told.stdin.write(b'{"type":"close"}\n')
        told.stdin.flush()
        assert wait_for_exit(told, 15) == 0
    finally:
        closed.kill()
        told.kill()


def test_a_worker_given_arguments_it_does_not_understand_ends_at_once_with_a_usage_error(model):
    directory, identity = model
    process = run_worker(fake_command(directory, identity)[:-2] + ("--max-text-chars", "not-a-number"))
    try:
        assert wait_for_exit(process, 15) == 2 and process.stdout.read() == b""
    finally:
        process.kill()


# --- what reaches the worker, and what it can reach ------------------------------------------------------------------------------------


REQUIRED = ["--model-dir", "--expect-revision", "--expect-weights-sha256", "--expect-directory-sha256", "--lifetime-seconds", "--idle-seconds", "--max-texts", "--max-text-chars"]


@pytest.mark.parametrize("name", REQUIRED)
def test_a_worker_started_without_any_one_of_its_arguments_ends_at_once_with_a_usage_error_and_says_which(model, name):
    directory, identity = model
    command = list(fake_command(directory, identity))
    at = command.index(name)
    del command[at : at + 2]
    process = subprocess.run(command, capture_output=True, timeout=60)
    assert process.returncode == 2 and process.stdout == b""
    assert process.stderr.decode().startswith("usage: semantic_worker [-h]") and name in process.stderr.decode()


def test_a_worker_that_is_ready_gets_the_whole_idle_time_to_be_used_however_long_it_took_to_load(model, monkeypatch):
    """The idle clock is reset when the worker is ready. A load of 3 s and an idle time of 4 s: with no reset the worker would end 4 s after it started, 1 s after it was ready."""
    directory, identity = model
    monkeypatch.setenv("EIDOS_FAKE_LOAD_SECONDS", "3.0")
    process = run_worker(fake_command(directory, identity, idle_seconds=4.0))
    try:
        assert process.stdout.readline().startswith(b'{"type":"ready"')
        time.sleep(2.5)  # 5.5 s after the start, and 1.5 s past the moment an unreset clock would have ended it
        assert process.poll() is None
        process.stdin.write(b'{"type":"embed","id":1,"texts":["a"]}' + chr(10).encode())
        process.stdin.flush()
        assert process.stdout.readline().startswith(b'{"type":"embedded"')
    finally:
        process.kill()


def test_the_callers_environment_does_not_reach_the_worker_but_the_offline_flags_and_what_was_passed_do(model, monkeypatch):
    directory, identity = model
    monkeypatch.setenv("EIDOS_SECRET_MARK", "hunter2")
    monkeypatch.setenv("PYTHONPATH", "/somewhere")
    with start(fake_command(directory, identity), identity, environment={"EIDOS_PASSED_MARK": "1"}) as embedder:
        seen = {name: embedder.embed([f"!env:{name}"])[0].vector[0] for name in ("EIDOS_SECRET_MARK", "PYTHONPATH", "EIDOS_PASSED_MARK", "PATH", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "OMP_NUM_THREADS")}
    assert seen == {"EIDOS_SECRET_MARK": 0.0, "PYTHONPATH": 0.0, "EIDOS_PASSED_MARK": 1.0, "PATH": 1.0, "HF_HUB_OFFLINE": 1.0, "TRANSFORMERS_OFFLINE": 1.0, "OMP_NUM_THREADS": 1.0}


def test_the_worker_sets_the_offline_flags_and_the_one_thread_flags_to_their_values(model):
    directory, identity = model
    expected = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    with start(fake_command(directory, identity), identity) as embedder:
        seen = {name: embedder.embed([f"!envis:{name}={value}"])[0].vector[0] for name, value in expected.items()}
    assert seen == {name: 1.0 for name in expected}


def test_the_worker_cannot_open_a_network_connection_even_to_this_machine(model):
    directory, identity = model
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(0.5)
        port = listener.getsockname()[1]
        with start(fake_command(directory, identity), identity) as embedder:
            vector = embedder.embed([f"!connect:{port}"])[0].vector
            assert vector[:2] == (0.0, 1.0)  # the connection failed
        with pytest.raises(TimeoutError):
            listener.accept()  # and nothing arrived


# --- the whole retriever over the process, the way it will be used ---------------------------------------------------------------------


def test_a_retriever_over_two_separate_workers_gives_the_same_result_and_the_result_is_a_valid_answer(model):
    directory, identity = model
    snapshot = build_snapshot((doc("s1", "alpha beta beta"), doc("s2", "alpha gamma"), doc("s3", "delta delta delta delta")), SCHEME)
    results = []
    for _ in range(2):
        with start(fake_command(directory, identity), identity) as embedder:
            port = SemanticKnowledgePort.open(snapshot, kb_id="kb1", embedder=embedder)
            assert isinstance(port, SemanticKnowledgePort)
            request = RetrievalRequest(kb_id="kb1", snapshot_id=snapshot.snapshot_id, scheme_id=semantic_scheme_id(identity), text="alpha", top_k=3, max_result_bytes=10**6)
            results.append(port.retrieve(request))
    assert isinstance(results[0], RetrievalResult) and results[0] == results[1] and len(results[0].hits) == 3


def test_a_chunk_over_the_window_makes_the_retriever_unavailable_through_the_real_process(model):
    directory, identity = model
    long_text = " ".join(["word"] * (MAX_PIECES - 1))  # one word over the window once the two special pieces are counted
    snapshot = build_snapshot((doc("s1", "alpha"), doc("s2", long_text)), SCHEME.model_copy(update={"max_words": 40}))
    with start(fake_command(directory, identity), identity) as embedder:
        result = SemanticKnowledgePort.open(snapshot, kb_id="kb1", embedder=embedder)
    assert isinstance(result, RetrievalFailure) and result.kind is RetrievalFailureKind.UNAVAILABLE and "never truncated" in result.message
