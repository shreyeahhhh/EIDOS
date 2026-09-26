"""A semantic worker with a stub model, for the tests of the process boundary (V1.3 Step 5).

Run as ``python -I fake_semantic_worker.py <the arguments of semantic_worker>``. It loads the REAL ``semantic_worker.py`` by its path (so under any interpreter, with no ``eidos`` on the path) and only
replaces its ``load_model``: the protocol loop, the digest verification, the network refusal, the offline flags and the watchdog that run are the real ones; only the model is a stub, so no
model library is needed. The stub is deterministic: a text's vector is made of the bytes of its SHA-256, and its pieces are its words plus two.

A few texts, marked with ``!``, make the stub misbehave in a scripted way, so the client's handling of a failing worker can be tested through the real loop:
``!sleep:S`` sleeps S seconds and then answers; ``!crash`` ends the process; ``!error`` raises; ``!nan`` returns a vector that is not finite; ``!long`` is over the window;
``!connect:PORT`` tries to connect to that local port and answers a vector whose first component says whether it could; ``!env:NAME`` answers a vector whose first component says whether that
environment variable is set, and ``!envis:NAME=VALUE`` whether it is set to that value; ``EIDOS_FAKE_LOAD_SECONDS`` makes the "model load" take that long.
"""

import hashlib
import importlib.util
import os
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "src" / "eidos" / "knowledge" / "semantic_worker.py"
DIMENSION = 8
MAX_PIECES = 16


def load_worker_module():
    spec = importlib.util.spec_from_file_location("semantic_worker_under_test", WORKER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def stub_vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [(byte - 127.5) / 127.5 for byte in digest[:DIMENSION]]


class StubModel:
    dimension = DIMENSION
    max_pieces = MAX_PIECES
    import_seconds = 0.0
    load_seconds = 0.0
    environment = {
        "python_version": sys.version.split()[0],
        "implementation": "stub",
        "platform": "stub",
        "libraries": [["stub", "0"]],
        "threads": 1,
        "evaluation_mode": True,
        "device": "cpu",
        "dtype": "float32",
    }

    def count_pieces(self, text: str) -> int:
        return 10_000 if text == "!long" else len(text.split()) + 2

    def encode(self, text: str) -> list[float]:
        if text.startswith("!sleep:"):
            time.sleep(float(text.split(":", 1)[1]))
        elif text == "!crash":
            os._exit(9)
        elif text == "!error":
            raise RuntimeError("scripted failure")
        elif text == "!nan":
            return [float("nan")] * DIMENSION
        elif text.startswith("!connect:"):
            try:
                socket.create_connection(("127.0.0.1", int(text.split(":", 1)[1])), timeout=2).close()
                return [1.0] + [0.0] * (DIMENSION - 1)
            except OSError:
                return [0.0, 1.0] + [0.0] * (DIMENSION - 2)
        elif text.startswith("!env:"):
            return [1.0 if text.split(":", 1)[1] in os.environ else 0.0] + [0.0] * (DIMENSION - 1)
        elif text.startswith("!envis:"):
            name, value = text.split(":", 1)[1].split("=", 1)
            return [1.0 if os.environ.get(name) == value else 0.0] + [0.0] * (DIMENSION - 1)
        return stub_vector(text)


if __name__ == "__main__":
    worker = load_worker_module()
    def load_model(directory):
        time.sleep(float(os.environ.get("EIDOS_FAKE_LOAD_SECONDS", "0")))  # a slow load, to show the idle time counts from the moment the worker is ready
        return StubModel()

    worker.load_model = load_model
    sys.exit(worker.main(sys.argv[1:]))
