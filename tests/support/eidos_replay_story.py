"""What a fresh interpreter can do with a serialized event log when the retrieval stack and every model library cannot be imported (decisions.md D-015, D-218, D-226, D-228).

Replay and the evidence audit read recorded facts and nothing else. This is the proof, shared by the tests that record a retrieving mission: the log is written to a new Python process that blocks the
whole retrieval stack, every agent, provider and backend, and every model library at import, replays it, audits it, and reports the result together with which blocked modules, if any, were nevertheless loaded.
"""

import json
import subprocess
import sys
from pathlib import Path

BLOCKED = (
    "eidos.knowledge", "eidos.agents", "eidos.recording", "eidos.policy", "eidos.mcp", "eidos.baseline", "eidos.providers", "eidos.backends", "eidos.a2a",
    "langgraph", "langchain", "torch", "sentence_transformers", "transformers", "tokenizers", "numpy", "safetensors", "huggingface_hub", "qdrant_client", "faiss", "requests", "httpx",
)

REPLAY_STORY = """
import hashlib, json, sys
sys.path.insert(0, 'src')
BLOCKED = %r

class Blocker:
    def find_spec(self, name, path=None, target=None):
        if name in BLOCKED or any(name.startswith(prefix + '.') for prefix in BLOCKED):
            raise ImportError('blocked: ' + name)
        return None

sys.meta_path.insert(0, Blocker())
from eidos.state import audit_evidence, execution_record, load_jsonl, replay_jsonl

text = sys.stdin.read()
replayed = replay_jsonl(text)
audit = audit_evidence(execution_record(load_jsonl(text).records))
loaded = sorted(m for m in sys.modules if m in BLOCKED or any(m.startswith(prefix + '.') for prefix in BLOCKED))
state_sha256 = hashlib.sha256(replayed.state.model_dump_json().encode('utf-8')).hexdigest()
print(json.dumps({"audit": json.loads(audit.model_dump_json()), "loaded": loaded, "status": str(replayed.state.status), "state_sha256": state_sha256}, sort_keys=True))
""" % (BLOCKED,)


def replay_in_fresh_process(text: str, root: Path) -> dict:
    """The story a new interpreter tells about ``text`` (a serialized log), run from ``root``. It fails, with the interpreter's own error, if the replay could not be done."""
    completed = subprocess.run([sys.executable, "-c", REPLAY_STORY], input=text, capture_output=True, text=True, cwd=root)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])
