"""The semantic worker: a program, not a module (decisions.md D-214, D-222, D-226; V1.3 Step 5).

It is run by the isolated Python 3.13 interpreter (``python -I semantic_worker.py --model-dir ...``) and nothing in EIDOS imports it. It is the only file of EIDOS that names the model
library, and it imports no ``eidos`` module and no ``pydantic``: what it shares with the port is a line protocol, not code. It embeds texts and counts their word pieces (only it has the
tokenizer); everything that decides what a retrieval returns (cosine, ordering, ties, ``top_k``, the byte bound, every mismatch) is in ``eidos.knowledge.semantic``, in the main runtime.

Protocol ``eidos-semantic-worker-v1``: one JSON object per line, ASCII, on stdin and stdout (stdout is reserved for the protocol: the library's own output goes to stderr).

    worker -> client, once, first:   {"type":"ready", "protocol":..., "identity":{...}, "environment":{...}, "import_seconds":..., "verify_seconds":..., "load_seconds":...}
                                     or {"type":"failed", "reason":"model_missing|identity_mismatch|library_missing|load_failed", "message":...}, and the worker ends
    client -> worker:                {"type":"embed", "id":N, "texts":[...]}    or   {"type":"close"}
    worker -> client:                {"type":"embedded", "id":N, "seconds":..., "items":[{"pieces":P, "vector":[...] or null}, ...]}
                                     or {"type":"refused", "id":N or null, "message":...} (the request was not an allowed request), or {"type":"error", "id":N, "message":...} and the worker ends

What is pinned, and what is refused. The model directory is verified before the library is imported and before a byte of it is loaded: the SHA-256 of the weights and of the whole directory
(``directory_digests``) must equal what the client expects, and the directory's own name must be the expected revision, or the worker reports ``identity_mismatch`` and ends. The library is
loaded from that directory only (``local_files_only``), the network is refused before the library is imported (the socket layer fails, and the offline flags are set), and a text of more word
pieces than the model's window gets ``"vector": null``: it is refused, never truncated.

A fixed execution configuration (D-226 reading 3): CPU, float32, one thread, each text encoded alone (batch size 1), evaluation mode, no normalisation, no prefix. Bounded: a request has at most
``--max-texts`` texts of at most ``--max-text-chars`` characters; a watchdog ends the process after ``--lifetime-seconds``, or after ``--idle-seconds`` without a request; the worker ends when its
stdin closes. The idle time runs from the start of the process, so it covers the load (the client requires it to exceed the time it gives the worker to start), and is reset when the worker is
ready. It never restarts itself and never writes a file.
"""

import argparse
import hashlib
import json
import math
import os
import platform
import socket
import sys
import threading
import time
from pathlib import Path

PROTOCOL = "eidos-semantic-worker-v1"
WEIGHTS_FILE = "model.safetensors"
JSON_BYTES_PER_CHARACTER = 12  # an ASCII-escaped astral character is a twelve-byte surrogate pair
REQUEST_SLACK_BYTES = 1024
WATCHDOG_POLL_SECONDS = 0.1
EXIT_FAILED = 3
EXIT_ERROR = 5
EXIT_OVERSIZE = 6
EXIT_WATCHDOG = 4


class WorkerRefusal(Exception):
    """A reason the worker cannot serve, with the ``reason`` the client maps to a typed failure."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def sha256_of_file(path: Path) -> str:
    with open(path, "rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def directory_digests(directory: Path) -> tuple[str, str]:
    """(SHA-256 of the weights file, SHA-256 of the whole directory). The directory's digest is that of ``"<path>\\n<file sha256>\\n"`` over every file, paths relative and with ``/``, in sorted string order."""
    relative = sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file())
    aggregate = hashlib.sha256()
    weights = None
    for name in relative:
        digest = sha256_of_file(directory / name)
        if name == WEIGHTS_FILE:
            weights = digest
        aggregate.update(f"{name}\n{digest}\n".encode("utf-8"))
    if weights is None:
        raise WorkerRefusal("model_missing", f"the model directory has no {WEIGHTS_FILE}")
    return weights, aggregate.hexdigest()


def refuse_network() -> None:
    """Make every outgoing connection fail, before the model library is imported, and set the offline flags the library reads."""

    def refuse(*args, **kwargs):
        raise OSError("the semantic worker makes no network connection")

    socket.socket.connect = refuse
    socket.socket.connect_ex = refuse
    socket.getaddrinfo = refuse
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        os.environ[name] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[name] = "1"


class SentenceTransformerModel:
    """The one model the worker loads. What ``serve`` needs of a model is exactly: ``dimension``, ``max_pieces``, ``environment``, ``import_seconds``, ``load_seconds``, ``count_pieces(text)`` and ``encode(text)``; a test's stub has the same."""
    def __init__(self, directory: Path):
        started = time.perf_counter()
        try:
            import numpy
            import sentence_transformers
            import tokenizers
            import torch
            import transformers
        except ImportError as error:
            raise WorkerRefusal("library_missing", f"the model library cannot be imported: {error}") from error
        self.import_seconds = time.perf_counter() - started
        torch.set_num_threads(1)
        started = time.perf_counter()
        try:
            self._model = sentence_transformers.SentenceTransformer(str(directory), device="cpu", trust_remote_code=False, local_files_only=True)
            self._model.eval()
        except (OSError, ValueError, RuntimeError) as error:
            raise WorkerRefusal("load_failed", f"the model cannot be loaded: {error}") from error
        self.load_seconds = time.perf_counter() - started
        self.dimension = int(self._model.get_sentence_embedding_dimension())
        self.max_pieces = int(self._model.max_seq_length)
        self._tokenizer = self._model.tokenizer
        self.environment = {
            "python_version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "libraries": [
                ["torch", torch.__version__],
                ["sentence-transformers", sentence_transformers.__version__],
                ["transformers", transformers.__version__],
                ["tokenizers", tokenizers.__version__],
                ["numpy", numpy.__version__],
            ],
            "threads": int(torch.get_num_threads()),
            "evaluation_mode": not self._model.training,
            "device": "cpu",
            "dtype": str(next(self._model.parameters()).dtype).replace("torch.", ""),
        }

    def count_pieces(self, text: str) -> int:
        return len(self._tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"])

    def encode(self, text: str) -> list[float]:
        return self._model.encode(text, batch_size=1, convert_to_numpy=True, normalize_embeddings=False, show_progress_bar=False).tolist()


def load_model(directory: Path) -> SentenceTransformerModel:
    return SentenceTransformerModel(directory)


def request_byte_limit(max_texts: int, max_text_characters: int) -> int:
    return max_texts * max_text_characters * JSON_BYTES_PER_CHARACTER + REQUEST_SLACK_BYTES


def send(channel, message: dict) -> None:
    channel.write(json.dumps(message, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("ascii") + b"\n")
    channel.flush()


def request_id(request: object) -> int | None:
    """The integer id of a request, or ``None`` if it has none (a boolean is not an id)."""
    identifier = request.get("id") if isinstance(request, dict) else None
    return identifier if isinstance(identifier, int) and not isinstance(identifier, bool) else None


def refusal_of(request: object, max_texts: int, max_text_characters: int) -> str | None:
    """Why ``request`` is not an allowed embed request, or ``None``."""
    if not isinstance(request, dict) or request.get("type") != "embed":
        return "a request is a JSON object of type embed or close"
    if set(request) != {"type", "id", "texts"} or request_id(request) is None:
        return "an embed request has exactly an integer id and a list of texts"
    texts = request["texts"]
    if not isinstance(texts, list) or not 1 <= len(texts) <= max_texts:
        return f"an embed request holds between 1 and {max_texts} texts"
    if not all(isinstance(text, str) and 1 <= len(text) <= max_text_characters for text in texts):
        return f"a text is a string of between 1 and {max_text_characters} characters"
    return None


def embed_items(model, texts: list[str]) -> list[dict]:
    items = []
    for text in texts:
        pieces = model.count_pieces(text)
        if pieces > model.max_pieces:
            items.append({"pieces": pieces, "vector": None})
            continue
        vector = [float(x) for x in model.encode(text)]
        if len(vector) != model.dimension or not all(math.isfinite(x) for x in vector):
            raise ValueError("the model produced a vector that is not of its dimension or not finite")
        items.append({"pieces": pieces, "vector": vector})
    return items


def serve(stdin, stdout, model, *, max_texts: int, max_text_characters: int, touch=lambda: None) -> int:
    """Answer requests until ``close`` or the end of stdin. The exit code: 0 on a clean end."""
    limit = request_byte_limit(max_texts, max_text_characters)
    while True:
        line = stdin.readline(limit + 1)
        touch()
        if not line:
            return 0
        if not line.endswith(b"\n"):
            send(stdout, {"type": "refused", "id": None, "message": f"a request is at most {limit} bytes on one line"})
            return EXIT_OVERSIZE
        try:
            request = json.loads(line.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            send(stdout, {"type": "refused", "id": None, "message": "a request is one line of ASCII JSON"})
            continue
        if isinstance(request, dict) and request == {"type": "close"}:
            return 0
        problem = refusal_of(request, max_texts, max_text_characters)
        if problem is not None:
            send(stdout, {"type": "refused", "id": request_id(request), "message": problem})
            continue
        started = time.perf_counter()
        try:
            items = embed_items(model, request["texts"])
        except Exception as error:  # a failing model call leaves the worker in an unknown state: it reports and ends
            send(stdout, {"type": "error", "id": request["id"], "message": f"{type(error).__name__}: {error}"})
            return EXIT_ERROR
        send(stdout, {"type": "embedded", "id": request["id"], "seconds": time.perf_counter() - started, "items": items})
        touch()


def start_watchdog(lifetime_seconds: float, idle_seconds: float, *, clock=time.monotonic, sleep=time.sleep, terminate=os._exit):
    """End the process after ``lifetime_seconds``, or after ``idle_seconds`` without ``touch()``. Returns ``touch``."""
    started = clock()
    last = [started]

    def touch() -> None:
        last[0] = clock()

    def watch() -> None:
        while True:
            sleep(WATCHDOG_POLL_SECONDS)
            now = clock()
            if now - started >= lifetime_seconds or now - last[0] >= idle_seconds:
                terminate(EXIT_WATCHDOG)
                return  # not reached when ``terminate`` ends the process, as the real one does

    threading.Thread(target=watch, daemon=True).start()
    return touch


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="semantic_worker")
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--expect-revision", required=True)
    parser.add_argument("--expect-weights-sha256", required=True)
    parser.add_argument("--expect-directory-sha256", required=True)
    parser.add_argument("--lifetime-seconds", type=float, required=True)
    parser.add_argument("--idle-seconds", type=float, required=True)
    parser.add_argument("--max-texts", type=int, required=True)
    parser.add_argument("--max-text-chars", type=int, required=True)
    args = parser.parse_args(argv)
    channel = sys.stdout.buffer
    sys.stdout = sys.stderr
    touch = start_watchdog(args.lifetime_seconds, args.idle_seconds)
    refuse_network()
    directory = Path(args.model_dir)
    try:
        if not directory.is_dir():
            raise WorkerRefusal("model_missing", f"the model directory {directory} does not exist")
        started = time.perf_counter()
        weights, aggregate = directory_digests(directory)
        verify_seconds = time.perf_counter() - started
        for name, found, expected in (
            ("revision (the directory's name)", directory.name, args.expect_revision),
            ("weights digest", weights, args.expect_weights_sha256),
            ("directory digest", aggregate, args.expect_directory_sha256),
        ):
            if found != expected:
                raise WorkerRefusal("identity_mismatch", f"the model's {name} is {found}, and {expected} is pinned")
        model = load_model(directory)
    except WorkerRefusal as refusal:
        send(channel, {"type": "failed", "reason": refusal.reason, "message": refusal.message})
        return EXIT_FAILED
    send(
        channel,
        {
            "type": "ready",
            "protocol": PROTOCOL,
            "identity": {"revision": directory.name, "weights_sha256": weights, "directory_sha256": aggregate, "dimension": model.dimension, "max_pieces": model.max_pieces},
            "environment": model.environment,
            "import_seconds": model.import_seconds,
            "verify_seconds": verify_seconds,
            "load_seconds": model.load_seconds,
        },
    )
    touch()
    return serve(sys.stdin.buffer, channel, model, max_texts=args.max_texts, max_text_characters=args.max_text_chars, touch=touch)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
