"""The semantic worker's own logic, run in process with a stub model (decisions.md D-214, D-222, D-226; V1.3 Step 5).

``semantic_worker.py`` is a program for the isolated interpreter, but everything it decides except loading the model library is plain Python: the directory digests that pin the model, what a request
may be, how a text becomes an item (refused over the window, never truncated), the request loop and its byte bound, and the watchdog. Those are proven here in the main interpreter with a stub
model; the loading of the real library, and the whole thing as a process, are proven elsewhere (the protocol tests and the ``real_model`` tests).
"""

import hashlib
import io
import json
import platform
import sys
import threading
import time
import types
from pathlib import Path

import pytest

from eidos.knowledge import semantic_worker as worker
from eidos.knowledge import semantic_process

WINDOW = 6


class StubModel:
    dimension = 3
    max_pieces = WINDOW
    environment = {}
    import_seconds = 0.0
    load_seconds = 0.0

    def __init__(self, *, vector=None, boom=None):
        self.vector = [0.5, -1.0, 2.0] if vector is None else vector
        self.boom = boom
        self.encoded: list[str] = []

    def count_pieces(self, text):
        return len(text.split()) + 2

    def encode(self, text):
        self.encoded.append(text)
        if self.boom:
            raise self.boom
        return list(self.vector)


def line(message) -> bytes:
    return json.dumps(message).encode("ascii") + b"\n"


def run_serve(requests: bytes, model=None, *, max_texts=4, max_chars=50, touch=lambda: None):
    stdin, stdout = io.BytesIO(requests), io.BytesIO()
    code = worker.serve(stdin, stdout, model or StubModel(), max_texts=max_texts, max_text_characters=max_chars, touch=touch)
    return code, [json.loads(part) for part in stdout.getvalue().splitlines()], stdout.getvalue()


def test_a_refusal_carries_its_reason_and_its_message_as_the_exception_text():
    refusal = worker.WorkerRefusal("model_missing", "no such directory")
    assert (refusal.reason, refusal.message, str(refusal)) == ("model_missing", "no such directory", "no such directory")


def test_the_worker_ends_with_these_exit_codes_and_its_watchdog_looks_this_often():
    """The exit codes are part of the boundary (the client reads them in a crash message and the tests read them from the process), and the poll interval is how far past a deadline the watchdog can let a worker live."""
    assert (worker.EXIT_FAILED, worker.EXIT_WATCHDOG, worker.EXIT_ERROR, worker.EXIT_OVERSIZE) == (3, 4, 5, 6)
    assert worker.WATCHDOG_POLL_SECONDS == 0.1
    assert worker.WEIGHTS_FILE == "model.safetensors" and worker.JSON_BYTES_PER_CHARACTER == 12 and worker.REQUEST_SLACK_BYTES == 1024


# --- the digests that pin a model directory --------------------------------------------------------------------------------------------


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_directory(root: Path, files: dict[str, bytes]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return root


def expected_digests(files: dict[str, bytes]) -> tuple[str, str]:
    aggregate = hashlib.sha256()
    for name in sorted(files):  # sorted as strings: capitals before lower case, whatever the platform's file system does
        aggregate.update(f"{name}\n{sha(files[name])}\n".encode("utf-8"))
    return sha(files["model.safetensors"]), aggregate.hexdigest()


FILES = {"model.safetensors": b"weights", "config.json": b"{}", "README.md": b"read me", "1_Pooling/config.json": b"pool", "a/b/deep.txt": b"deep"}


def test_the_digests_are_the_weights_and_the_sorted_path_and_content_aggregate(tmp_path):
    directory = make_directory(tmp_path / "model", FILES)
    assert worker.directory_digests(directory) == expected_digests(FILES)


def test_paths_are_sorted_as_strings_so_a_capital_sorts_before_a_lower_case_name(tmp_path):
    files = {"model.safetensors": b"w", "Zeta.txt": b"z", "alpha.txt": b"a"}
    assert sorted(files) == ["Zeta.txt", "alpha.txt", "model.safetensors"]
    assert worker.directory_digests(make_directory(tmp_path / "m", files)) == expected_digests(files)


def test_a_changed_file_a_renamed_file_or_an_added_file_changes_the_directory_digest_and_only_a_changed_weights_file_changes_the_weights_digest(tmp_path):
    base_weights, base_directory = worker.directory_digests(make_directory(tmp_path / "base", FILES))
    changed = worker.directory_digests(make_directory(tmp_path / "changed", FILES | {"config.json": b"{ }"}))
    renamed = worker.directory_digests(make_directory(tmp_path / "renamed", {("config2.json" if name == "config.json" else name): value for name, value in FILES.items()}))
    added = worker.directory_digests(make_directory(tmp_path / "added", FILES | {"extra.txt": b"x"}))
    assert changed == (base_weights, changed[1]) and changed[1] != base_directory
    assert renamed[0] == base_weights and renamed[1] != base_directory
    assert added[0] == base_weights and added[1] != base_directory
    assert worker.directory_digests(make_directory(tmp_path / "w", FILES | {"model.safetensors": b"other"}))[0] != base_weights


def test_empty_directories_do_not_count_and_a_directory_without_weights_is_refused(tmp_path):
    directory = make_directory(tmp_path / "m", FILES)
    (directory / "empty").mkdir()
    assert worker.directory_digests(directory) == expected_digests(FILES)
    with pytest.raises(worker.WorkerRefusal) as refusal:
        worker.directory_digests(make_directory(tmp_path / "none", {"config.json": b"{}"}))
    assert refusal.value.reason == "model_missing"


def test_a_file_bigger_than_one_read_block_is_hashed_whole(tmp_path):
    data = bytes(range(256)) * 9000  # 2.3 million bytes: more than two read blocks
    path = tmp_path / "big.bin"
    path.write_bytes(data)
    assert worker.sha256_of_file(path) == sha(data)


# --- what a request may be -------------------------------------------------------------------------------------------------------------


def request_of(**changes):
    return {"type": "embed", "id": 1, "texts": ["alpha"]} | changes


@pytest.mark.parametrize(
    "request_",
    [
        request_of(),
        request_of(texts=["a"] * 4),
        request_of(texts=["x" * 50]),
        request_of(id=0),
        request_of(id=-3),
    ],
)
def test_an_embed_request_with_an_integer_id_and_one_to_max_texts_of_one_to_max_characters_is_allowed(request_):
    assert worker.refusal_of(request_, 4, 50) is None


@pytest.mark.parametrize(
    "request_",
    [
        None,
        [],
        "embed",
        7,
        {},
        {"type": "close"},
        {"type": "stats", "id": 1, "texts": ["a"]},
        request_of(type="embedx"),
        {"type": "embed", "texts": ["a"]},
        {"type": "embed", "id": 1},
        request_of(surprise=1),
        request_of(id="1"),
        request_of(id=True),
        request_of(id=1.0),
        request_of(id=None),
        request_of(texts=[]),
        request_of(texts=["a"] * 5),
        request_of(texts="alpha"),
        request_of(texts=("alpha",)),
        request_of(texts=[""]),
        request_of(texts=["x" * 51]),
        request_of(texts=["ok", 3]),
        request_of(texts=["ok", None]),
        request_of(texts=[["ok"]]),
    ],
)
def test_anything_else_is_refused_with_a_reason(request_):
    assert isinstance(worker.refusal_of(request_, 4, 50), str)


def test_the_request_line_bound_holds_the_worst_request_the_client_may_send_and_no_more_than_a_little_over():
    max_texts, max_chars = 64, 20000
    astral = chr(0x1F600) * max_chars  # ASCII-escaped, one character is a twelve-byte surrogate pair
    encoded = json.dumps({"type": "embed", "id": 10**9, "texts": [astral] * max_texts}, ensure_ascii=True, separators=(",", ":")).encode("ascii") + b"\n"
    limit = worker.request_byte_limit(max_texts, max_chars)
    assert len(encoded) - 1 <= limit
    assert limit - len(encoded) < 1100
    assert worker.request_byte_limit(1, 1) == 12 + 1024


def test_the_clients_encoding_of_the_worst_request_fits_the_workers_bound_for_every_default_limit():
    limits = semantic_process.WorkerLimits()
    astral = chr(0x1F600) * limits.max_text_characters
    encoded = json.dumps({"type": "embed", "id": 2**31, "texts": [astral] * limits.max_texts_per_request}, ensure_ascii=True, separators=(",", ":")).encode("ascii") + b"\n"
    assert len(encoded) <= worker.request_byte_limit(limits.max_texts_per_request, limits.max_text_characters) + 1


def test_the_worker_and_the_client_speak_the_same_protocol():
    assert worker.PROTOCOL == semantic_process.PROTOCOL == "eidos-semantic-worker-v1"


# --- a text becomes an item ------------------------------------------------------------------------------------------------------------


def test_a_text_within_the_window_gets_its_pieces_and_its_vector():
    model = StubModel()
    assert worker.embed_items(model, ["alpha beta"]) == [{"pieces": 4, "vector": [0.5, -1.0, 2.0]}]
    assert model.encoded == ["alpha beta"]


def test_a_text_exactly_at_the_window_is_embedded_and_one_piece_more_is_refused_and_never_encoded():
    model = StubModel()
    at_window, over = "a b c d", "a b c d e"  # 4 + 2 = 6 pieces, and 5 + 2 = 7
    items = worker.embed_items(model, [at_window, over])
    assert items == [{"pieces": 6, "vector": [0.5, -1.0, 2.0]}, {"pieces": 7, "vector": None}]
    assert model.encoded == [at_window]


def test_items_come_back_in_the_order_of_the_texts():
    items = worker.embed_items(StubModel(), ["a b c d e", "a", "a b"])
    assert [item["pieces"] for item in items] == [7, 3, 4]


@pytest.mark.parametrize("vector", [[1.0, 2.0], [1.0, 2.0, 3.0, 4.0], [1.0, float("nan"), 0.0], [float("inf"), 0.0, 0.0], []])
def test_a_vector_of_the_wrong_length_or_not_finite_is_an_error_not_an_item(vector):
    with pytest.raises(ValueError):
        worker.embed_items(StubModel(vector=vector), ["alpha"])


def test_integers_from_the_model_become_floats():
    items = worker.embed_items(StubModel(vector=[1, 2, 3]), ["alpha"])
    assert items[0]["vector"] == [1.0, 2.0, 3.0] and all(type(x) is float for x in items[0]["vector"])


# --- the request loop ------------------------------------------------------------------------------------------------------------------


def test_an_embed_request_gets_one_ascii_line_with_its_id_its_time_and_its_items():
    code, replies, raw = run_serve(line(request_of(id=7, texts=["alpha", "a b c d e"])))
    assert code == 0
    assert len(replies) == 1 and raw.endswith(b"\n") and raw.count(b"\n") == 1 and all(b < 128 for b in raw)
    reply = replies[0]
    assert set(reply) == {"type", "id", "seconds", "items"} and reply["type"] == "embedded" and reply["id"] == 7
    assert 0 <= reply["seconds"] < 30 and reply["items"] == [{"pieces": 3, "vector": [0.5, -1.0, 2.0]}, {"pieces": 7, "vector": None}]  # a duration, not a reading of the clock


def test_requests_are_answered_in_order_and_close_ends_the_loop_without_a_reply():
    code, replies, _ = run_serve(line(request_of(id=1)) + line(request_of(id=2)) + line({"type": "close"}) + line(request_of(id=3)))
    assert code == 0 and [reply["id"] for reply in replies] == [1, 2]


def test_the_end_of_stdin_ends_the_loop_cleanly():
    assert run_serve(b"")[0] == 0
    assert run_serve(line(request_of()))[0] == 0


def test_a_refused_request_is_answered_with_its_id_and_the_loop_goes_on():
    code, replies, _ = run_serve(line(request_of(id=5, texts=[])) + line(request_of(id=6)))
    assert code == 0
    assert replies[0]["type"] == "refused" and replies[0]["id"] == 5 and "between 1 and 4 texts" in replies[0]["message"]
    assert replies[1]["type"] == "embedded" and replies[1]["id"] == 6


@pytest.mark.parametrize("bad_id", ["1", True, None, 1.5])
def test_a_refused_request_whose_id_is_not_an_integer_is_answered_with_a_null_id(bad_id):
    _, replies, _ = run_serve(line(request_of(id=bad_id, texts=[])))
    assert replies[0]["type"] == "refused" and replies[0]["id"] is None


def test_a_line_that_is_not_json_or_not_ascii_is_refused_and_the_loop_goes_on():
    code, replies, _ = run_serve(b"this is not json\n" + "caf\xe9\n".encode("latin-1") + b"[1, 2\n" + line(request_of(id=9)))
    assert code == 0
    assert [reply["type"] for reply in replies] == ["refused", "refused", "refused", "embedded"]
    assert all(reply["id"] is None for reply in replies[:3]) and replies[3]["id"] == 9
    assert all(reply["message"] == "a request is one line of ASCII JSON" for reply in replies[:3])


def test_a_request_line_over_the_bound_is_refused_and_ends_the_worker_because_the_stream_is_out_of_step():
    limit = worker.request_byte_limit(4, 50)
    code, replies, _ = run_serve(b"x" * (limit + 1) + b"\n" + line(request_of(id=1)))
    assert code == worker.EXIT_OVERSIZE and len(replies) == 1 and replies[0]["type"] == "refused" and str(limit) in replies[0]["message"]
    assert replies[0] == {"type": "refused", "id": None, "message": f"a request is at most {limit} bytes on one line"}


def test_a_request_line_of_exactly_the_bound_is_read_whole():
    limit = worker.request_byte_limit(4, 50)
    padded = json.dumps(request_of(id=1)).encode("ascii")
    line_at_the_bound = padded + b" " * (limit - len(padded)) + b"\n"
    assert len(line_at_the_bound) == limit + 1
    code, replies, _ = run_serve(line_at_the_bound)
    assert code == 0 and replies[0]["type"] == "embedded"


def test_a_failing_model_call_is_reported_and_ends_the_worker():
    code, replies, _ = run_serve(line(request_of(id=4)) + line(request_of(id=5)), StubModel(boom=RuntimeError("scripted")))
    assert code == worker.EXIT_ERROR and len(replies) == 1
    assert replies[0] == {"type": "error", "id": 4, "message": "RuntimeError: scripted"}


def test_a_vector_that_is_not_finite_is_reported_as_an_error_and_ends_the_worker():
    code, replies, _ = run_serve(line(request_of(id=4)), StubModel(vector=[float("nan"), 0.0, 0.0]))
    assert code == worker.EXIT_ERROR and replies[0]["type"] == "error" and replies[0]["id"] == 4


def test_the_activity_clock_is_touched_when_a_line_is_read_and_when_a_reply_is_sent():
    touched = []
    run_serve(line(request_of(id=1)), touch=lambda: touched.append(1))
    assert len(touched) == 3  # the request, the end of stdin, and the reply


def test_the_worker_never_sends_a_non_finite_number():
    with pytest.raises(ValueError):
        worker.send(io.BytesIO(), {"vector": [float("nan")]})


def test_a_message_is_one_ascii_json_line():
    out = io.BytesIO()
    worker.send(out, {"type": "x", "text": chr(0xE9) + chr(0x1F600)})
    raw = out.getvalue()
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1 and all(b < 128 for b in raw)
    assert json.loads(raw) == {"type": "x", "text": chr(0xE9) + chr(0x1F600)}


# --- the one model the worker loads, against a recording stand-in for the model library ---------------------------------------------------------------------


class Recorder:
    """Stands in for the model library in ``sys.modules``: it records every call the worker makes on it, so the fixed execution configuration is read off the calls."""

    def __init__(self, *, fail_with=None):
        self.calls: list[tuple] = []
        self.fail_with = fail_with
        recorder = self

        class Dtype:
            def __str__(self):
                return "torch.float32"

        class Parameter:
            dtype = Dtype()

        class Vector:
            def __init__(self, values):
                self.values = values

            def tolist(self):
                return list(self.values)

        class Model:
            max_seq_length = 128

            def __init__(self, *args, **kwargs):
                recorder.calls.append(("SentenceTransformer", args, kwargs))
                if recorder.fail_with is not None:
                    raise recorder.fail_with
                self.training = True  # a model is built in training mode until it is told otherwise

            def eval(self):
                recorder.calls.append(("eval",))
                self.training = False

            def get_sentence_embedding_dimension(self):
                return 3  # the stand-in's vectors are three numbers long

            def tokenizer(self, text, **kwargs):
                recorder.calls.append(("tokenizer", text, kwargs))
                return {"input_ids": list(range(len(text.split()) + 2))}

            def parameters(self):
                return iter([Parameter()])

            def encode(self, text, **kwargs):
                recorder.calls.append(("encode", text, kwargs))
                return Vector([0.25, -0.5, 1.0])

        self.torch = types.ModuleType("torch")
        self.torch.__version__ = "1.2.3+cpu"
        self.torch.set_num_threads = lambda n: (recorder.calls.append(("set_num_threads", n)), setattr(recorder, "threads", n))[0]
        self.torch.get_num_threads = lambda: getattr(recorder, "threads", 12)
        self.sentence_transformers = types.ModuleType("sentence_transformers")
        self.sentence_transformers.__version__ = "5.6.7"
        self.sentence_transformers.SentenceTransformer = Model
        self.transformers, self.tokenizers, self.numpy = types.ModuleType("transformers"), types.ModuleType("tokenizers"), types.ModuleType("numpy")
        self.transformers.__version__, self.tokenizers.__version__, self.numpy.__version__ = "4.5.6", "0.9.9", "2.3.4"

    def install(self, monkeypatch):
        for name in ("torch", "sentence_transformers", "transformers", "tokenizers", "numpy"):
            monkeypatch.setitem(sys.modules, name, getattr(self, name))
        return self


def loaded_model(monkeypatch, tmp_path, **kwargs):
    recorder = Recorder(**kwargs).install(monkeypatch)
    return recorder, worker.SentenceTransformerModel(tmp_path)


def test_the_model_is_loaded_from_its_local_directory_on_the_cpu_offline_without_remote_code_and_put_in_evaluation_mode(monkeypatch, tmp_path):
    recorder, model = loaded_model(monkeypatch, tmp_path)
    assert recorder.calls[:3] == [
        ("set_num_threads", 1),
        ("SentenceTransformer", (str(tmp_path),), {"device": "cpu", "trust_remote_code": False, "local_files_only": True}),
        ("eval",),
    ]
    assert model.environment["evaluation_mode"] is True and model.environment["threads"] == 1


def test_what_the_worker_reports_of_the_model_is_measured_from_it(monkeypatch, tmp_path):
    _, model = loaded_model(monkeypatch, tmp_path)
    assert (model.dimension, model.max_pieces) == (3, 128) and type(model.dimension) is int and type(model.max_pieces) is int
    environment = model.environment
    assert environment == {
        "python_version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "libraries": [["torch", "1.2.3+cpu"], ["sentence-transformers", "5.6.7"], ["transformers", "4.5.6"], ["tokenizers", "0.9.9"], ["numpy", "2.3.4"]],
        "threads": 1,
        "evaluation_mode": True,
        "device": "cpu",
        "dtype": "float32",
    }
    assert 0.0 <= model.import_seconds < 30.0 and 0.0 <= model.load_seconds < 30.0  # durations, not readings of the clock


def test_a_text_is_counted_by_the_tokenizer_with_the_special_pieces_and_no_truncation_and_encoded_alone_with_no_normalisation(monkeypatch, tmp_path):
    recorder, model = loaded_model(monkeypatch, tmp_path)
    recorder.calls.clear()
    assert model.count_pieces("three little words") == 5
    assert recorder.calls == [("tokenizer", "three little words", {"add_special_tokens": True, "truncation": False})]
    recorder.calls.clear()
    assert model.encode("a text") == [0.25, -0.5, 1.0]
    assert recorder.calls == [
        ("encode", "a text", {"batch_size": 1, "convert_to_numpy": True, "normalize_embeddings": False, "show_progress_bar": False})
    ]


@pytest.mark.parametrize("error", [OSError("no such file"), ValueError("bad config"), RuntimeError("bad weights")])
def test_a_model_that_cannot_be_loaded_is_a_typed_refusal_with_the_reason(monkeypatch, tmp_path, error):
    recorder = Recorder(fail_with=error).install(monkeypatch)
    with pytest.raises(worker.WorkerRefusal) as refusal:
        worker.SentenceTransformerModel(tmp_path)
    assert refusal.value.reason == "load_failed" and str(error) in refusal.value.message and "cannot be loaded" in refusal.value.message
    assert ("eval",) not in recorder.calls


def test_a_missing_library_is_a_typed_refusal_naming_the_import(monkeypatch, tmp_path):
    Recorder().install(monkeypatch)
    monkeypatch.setitem(sys.modules, "tokenizers", None)  # an import of it now fails
    with pytest.raises(worker.WorkerRefusal) as refusal:
        worker.SentenceTransformerModel(tmp_path)
    assert refusal.value.reason == "library_missing" and "tokenizers" in refusal.value.message


def test_the_loaded_model_is_what_load_model_returns_and_serves_the_request_loop(monkeypatch, tmp_path):
    Recorder().install(monkeypatch)
    model = worker.load_model(tmp_path)
    assert isinstance(model, worker.SentenceTransformerModel)
    code, replies, _ = run_serve(line(request_of(id=1, texts=["one two three"])), model)
    assert code == 0 and replies[0]["type"] == "embedded" and replies[0]["items"] == [{"pieces": 5, "vector": [0.25, -0.5, 1.0]}]


# --- the watchdog ----------------------------------------------------------------------------------------------------------------------


def watch(lifetime, idle):
    now = [0.0]
    ended = []

    def terminate(code):
        ended.append(code)

    touch = worker.start_watchdog(lifetime, idle, clock=lambda: now[0], terminate=terminate)
    return now, ended, touch


def wait_for(condition, seconds=3.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_the_watchdog_ends_the_process_when_the_lifetime_is_over():
    now, ended, touch = watch(lifetime=100.0, idle=1000.0)
    time.sleep(0.3)
    assert ended == []
    now[0] = 100.0
    assert wait_for(lambda: ended)
    time.sleep(0.4)
    assert ended == [worker.EXIT_WATCHDOG]  # once: the watchdog does not go on after it has ended the process


def test_the_watchdog_ends_the_process_after_the_idle_time_without_activity_and_a_touch_resets_it():
    now, ended, touch = watch(lifetime=10_000.0, idle=10.0)
    now[0] = 9.0
    touch()
    now[0] = 18.0  # nine seconds since the touch: not idle yet
    time.sleep(0.4)
    assert ended == []
    now[0] = 19.0  # ten seconds since the touch
    assert wait_for(lambda: ended) and ended == [worker.EXIT_WATCHDOG]


def test_the_watchdog_lets_a_busy_worker_live_until_its_lifetime_is_over():
    now, ended, touch = watch(lifetime=50.0, idle=10.0)
    for second in range(1, 49, 5):
        now[0] = float(second)
        touch()
        time.sleep(0.15)
    assert ended == []
    now[0] = 50.0
    assert wait_for(lambda: ended)


def test_the_watchdog_sleeps_between_looks_and_does_not_spin():
    naps, ended = [], []
    gate = threading.Event()

    def sleep(seconds):
        naps.append(seconds)
        gate.wait(0.02)

    worker.start_watchdog(100.0, 1000.0, clock=lambda: 0.0, sleep=sleep, terminate=ended.append)
    assert wait_for(lambda: len(naps) >= 3)
    assert set(naps) == {worker.WATCHDOG_POLL_SECONDS} and ended == []


def test_the_watchdog_thread_does_not_keep_the_process_alive():
    before = {thread for thread in threading.enumerate()}
    now, ended, touch = watch(lifetime=100.0, idle=1000.0)
    started = [thread for thread in threading.enumerate() if thread not in before]
    assert len(started) == 1 and started[0].daemon
    now[0] = 1000.0
    assert wait_for(lambda: ended)
