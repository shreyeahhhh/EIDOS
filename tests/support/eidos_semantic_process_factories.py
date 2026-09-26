"""Helpers for the tests that run the semantic worker as a process: a fake model directory with its identity, and the commands that start the stub and the misbehaving workers (V1.3 Step 5)."""

import hashlib
import sys
from pathlib import Path

from eidos.knowledge import SemanticModelIdentity
from eidos.knowledge.semantic_process import WorkerLimits, semantic_worker_command

ROOT = Path(__file__).resolve().parents[2]
FAKE_WORKER = ROOT / "tests" / "support" / "fake_semantic_worker.py"
MISBEHAVING_WORKER = ROOT / "tests" / "support" / "misbehaving_semantic_worker.py"
FAKE_REVISION = "0123456789abcdef0123456789abcdef01234567"
FAKE_FILES = {"model.safetensors": b"stub weights", "config.json": b"{}", "1_Pooling/config.json": b"pooling", "README.md": b"read me"}
FAST = WorkerLimits(ready_timeout_seconds=60.0, request_timeout_seconds=30.0, idle_timeout_seconds=120.0, lifetime_seconds=300.0)


def make_fake_model(root: Path, files: dict[str, bytes] | None = None, *, revision: str = FAKE_REVISION) -> tuple[Path, SemanticModelIdentity]:
    """A model directory named ``revision`` with ``files``, and the identity a worker reads from it, computed here independently of the worker."""
    files = FAKE_FILES if files is None else files
    directory = root / revision
    for name, content in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    aggregate = hashlib.sha256()
    for name in sorted(files):
        aggregate.update(f"{name}\n{hashlib.sha256(files[name]).hexdigest()}\n".encode("utf-8"))
    identity = SemanticModelIdentity(
        model="test/fake-stub",
        revision=revision,
        weights_sha256=hashlib.sha256(files.get("model.safetensors", b"")).hexdigest(),
        directory_sha256=aggregate.hexdigest(),
        dimension=8,
        max_pieces=16,
    )
    return directory, identity


def fake_command(directory: Path, identity: SemanticModelIdentity, limits: WorkerLimits = FAST, **overrides) -> tuple[str, ...]:
    """The command that starts the stub worker on ``directory``; ``overrides`` replace the worker's own arguments (for example ``lifetime_seconds``), which the limits would not allow."""
    command = list(semantic_worker_command(sys.executable, directory, identity, limits, script=FAKE_WORKER))
    for name, value in overrides.items():
        command[command.index("--" + name.replace("_", "-")) + 1] = str(value)
    return tuple(command)


def misbehaving_command(mode: str, identity: SemanticModelIdentity) -> tuple[str, ...]:
    return (sys.executable, "-I", str(MISBEHAVING_WORKER), mode, identity.model_dump_json())
