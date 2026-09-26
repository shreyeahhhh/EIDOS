"""The process boundary as an isolation guarantee: the main interpreter needs no model library, and the worker checks before it loads (decisions.md D-214, D-222, D-226; V1.3 Step 5).

D-226 ruling 2: the main runtime stays on its own interpreter and imports none of the model library; the library lives behind a process boundary in another interpreter. Every test here starts a fresh
interpreter in which every model library is made unimportable (a meta-path hook that refuses the import), so a passing test proves the code under test never needed one. What is proven: a whole
semantic retrieval, through a real worker process, runs in an interpreter that cannot import the library; every module of EIDOS imports in one; the worker file itself imports in one, because it loads the
library only when it loads a model; and the worker verifies the model directory's digests before it imports the library, and reports a missing library as a typed failure, not a crash.
"""

import json
import subprocess
import sys
from pathlib import Path

from eidos_semantic_process_factories import FAKE_WORKER, FAST, make_fake_model
from eidos.knowledge.semantic_process import WORKER_SCRIPT, semantic_worker_command

ROOT = Path(__file__).resolve().parents[3]
LIBRARIES = ("torch", "sentence_transformers", "transformers", "tokenizers", "numpy", "scipy", "sklearn", "safetensors", "huggingface_hub", "onnxruntime")
OPTIONAL_EXTRAS = ("langgraph", "langchain", "langchain_core", "langsmith", "httpx")  # the extras of pyproject.toml, which the isolated interpreter does not have installed

BLOCKER = """
import sys
BLOCKED = %r

class Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in BLOCKED:
            raise ImportError('blocked: ' + name)
        return None

sys.meta_path.insert(0, Blocker())
""" % (LIBRARIES,)


def run(story: str, *args: str, isolated: bool = False) -> subprocess.CompletedProcess:
    command = [sys.executable, *(["-I"] if isolated else []), "-c", BLOCKER + story, *args]
    return subprocess.run(command, capture_output=True, text=True, cwd=ROOT, timeout=300)


def test_a_whole_semantic_retrieval_runs_in_an_interpreter_that_cannot_import_any_model_library(tmp_path):
    directory, identity = make_fake_model(tmp_path)
    story = """
import json, sys
sys.path[:0] = ['src', 'tests/support']
from eidos.knowledge import RetrievalRequest, SemanticKnowledgePort, build_snapshot, semantic_scheme_id
from eidos.knowledge.semantic_process import IsolatedEmbedder
from eidos_knowledge_factories import SCHEME, doc
from eidos_semantic_process_factories import FAST, fake_command
from eidos.knowledge import SemanticModelIdentity

identity = SemanticModelIdentity.model_validate_json(sys.argv[2])
embedder = IsolatedEmbedder.start(fake_command(sys.argv[1], identity), expected=identity, limits=FAST)
assert isinstance(embedder, IsolatedEmbedder), embedder
with embedder:
    snapshot = build_snapshot((doc('s1', 'alpha beta beta'), doc('s2', 'alpha gamma'), doc('s3', 'delta delta delta delta')), SCHEME)
    port = SemanticKnowledgePort.open(snapshot, kb_id='kb1', embedder=embedder)
    result = port.retrieve(RetrievalRequest(kb_id='kb1', snapshot_id=snapshot.snapshot_id, scheme_id=semantic_scheme_id(identity), text='alpha', top_k=3, max_result_bytes=10**6))
loaded = sorted(m for m in sys.modules if m.split('.')[0] in %r)
print(json.dumps({"hits": len(result.hits), "loaded": loaded}))
""" % (LIBRARIES,)
    completed = run(story, str(directory), identity.model_dump_json())
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == {"hits": 3, "loaded": []}


def test_every_module_of_eidos_imports_in_an_interpreter_that_cannot_import_any_model_library():
    story = """
import importlib, json, pkgutil, sys
sys.path.insert(0, 'src')
import eidos
imported, missing_extras = [], []
for module in pkgutil.walk_packages(eidos.__path__, 'eidos.'):
    try:
        importlib.import_module(module.name)
        imported.append(module.name)
    except ImportError as error:  # an optional extra (the workflow library, the HTTP client) that this interpreter does not have: never a model library
        cause = error.__cause__ or error
        assert (getattr(cause, 'name', None) or '').split('.')[0] in %r, (module.name, repr(error))
        missing_extras.append(module.name)
loaded = sorted(m for m in sys.modules if m.split('.')[0] in %r)
print(json.dumps({"imported": len(imported), "has_process_client": 'eidos.knowledge.semantic_process' in imported, "has_worker": 'eidos.knowledge.semantic_worker' in imported, "loaded": loaded, "missing_extras": missing_extras}))
""" % (OPTIONAL_EXTRAS, LIBRARIES)
    completed = run(story)
    assert completed.returncode == 0, completed.stderr
    story_out = json.loads(completed.stdout.strip().splitlines()[-1])
    assert story_out["loaded"] == [] and story_out["has_process_client"] and story_out["has_worker"] and story_out["imported"] > 50
    assert all(name.startswith(("eidos.backends.langgraph", "eidos.a2a")) for name in story_out["missing_extras"]), story_out["missing_extras"]  # only modules that need an optional extra


def worker_story(command) -> str:
    """Run the real worker program the way its interpreter would (as ``__main__``), with the libraries unimportable."""
    return """
import runpy, sys
sys.argv = %r
runpy.run_path(sys.argv[0], run_name='__main__')
""" % (list(command[2:]),)


def test_the_worker_file_can_be_run_where_the_library_is_missing_and_says_so_as_a_typed_failure_not_a_crash(tmp_path):
    directory, identity = make_fake_model(tmp_path)
    command = semantic_worker_command(sys.executable, directory, identity, FAST)
    completed = run(worker_story(command))
    assert completed.returncode == 3, completed.stderr  # the worker's own exit code for a refusal
    first = json.loads(completed.stdout.splitlines()[0])
    assert first["type"] == "failed" and first["reason"] == "library_missing" and "blocked" in first["message"]
    assert len(completed.stdout.splitlines()) == 1


def test_the_worker_verifies_the_model_directory_before_it_imports_the_library(tmp_path):
    directory, identity = make_fake_model(tmp_path)
    wrong = identity.model_copy(update={"weights_sha256": "0" * 64})
    completed = run(worker_story(semantic_worker_command(sys.executable, directory, wrong, FAST)))
    assert completed.returncode == 3, completed.stderr
    first = json.loads(completed.stdout.splitlines()[0])
    assert first["reason"] == "identity_mismatch"  # not library_missing: the digests were checked first, and the library was never asked for


def test_the_worker_file_imports_where_the_library_is_missing_because_it_loads_the_library_only_when_it_loads_a_model():
    story = """
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('semantic_worker_file', sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
try:
    module.load_model(Path('nowhere'))
    outcome = 'loaded'
except module.WorkerRefusal as refusal:
    outcome = refusal.reason
print(json.dumps({"outcome": outcome, "loaded": sorted(m for m in sys.modules if m.split('.')[0] in %r)}))
""" % (LIBRARIES,)
    completed = run(story, str(WORKER_SCRIPT), isolated=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == {"outcome": "library_missing", "loaded": []}


def test_the_stub_worker_used_by_the_protocol_tests_is_the_real_worker_with_only_the_model_replaced():
    """The fake worker loads the real file and replaces ``load_model`` alone, so every protocol test exercises the real loop; it must not grow a protocol of its own."""
    text = FAKE_WORKER.read_text(encoding="utf-8")
    assert "worker.load_model = " in text and "worker.main(sys.argv[1:])" in text
    for name in ("serve", "send", "refuse_network", "start_watchdog", "directory_digests", "refusal_of", "embed_items"):
        assert f"worker.{name} = " not in text, f"the fake worker must not replace {name}"
