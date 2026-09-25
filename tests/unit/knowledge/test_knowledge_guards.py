"""Static guards on ``eidos.knowledge`` (decisions.md D-208 to D-222, invariants 9, 10 and 15, CLAUDE.md section 8; V1.3 Step 2).

The layer is deterministic and pure: no I/O, network, subprocess, clock, randomness, model call or hidden state, and it names no retrieval engine, vector
store or embedding model. It depends only on ``eidos.contracts``; it imports no agent, adapter or backend, and no other package imports it yet. Retrieval ports
will be added under it at a later step (D-222), and this guard is revised deliberately then, not weakened.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "eidos"
KNOWLEDGE = SRC / "knowledge"
MODULES = sorted(KNOWLEDGE.glob("*.py"))

FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "datetime", "http", "importlib", "io", "logging", "multiprocessing", "os", "pathlib", "pickle", "random", "requests",
    "secrets", "shelve", "shutil", "socket", "sqlite3", "ssl", "subprocess", "sys", "tempfile", "threading", "time", "urllib", "uuid", "httpx",
    "aiohttp", "numpy", "scipy", "sklearn", "torch", "transformers", "sentence_transformers", "tokenizers", "huggingface_hub", "safetensors",
    "onnxruntime", "qdrant_client", "faiss", "rank_bm25", "fastembed", "nltk", "spacy", "langgraph", "langchain", "langsmith", "ollama", "openai",
    "anthropic",
}
ALLOWED_ROOTS = {"__future__", "collections", "enum", "hashlib", "json", "re", "types", "typing", "unicodedata", "pydantic", "eidos"}
ALLOWED_EIDOS = {"eidos.contracts", "eidos.knowledge"}
FORBIDDEN_WORDS = {
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere", "ollama", "qdrant", "faiss", "torch", "transformers", "numpy",
    "scipy", "sklearn", "bm25", "onnxruntime", "a2a", "mcp", "rag", "laya", "dspy", "langgraph", "langchain", "langsmith",
}


def imports_of(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    return found


def test_the_package_is_exactly_the_modules_that_implement_the_pure_structures():
    assert [module.name for module in MODULES] == ["__init__.py", "chunking.py", "contracts.py", "identity.py", "independence.py", "snapshot.py"]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_io_network_process_clock_randomness_or_engine_library_is_imported(module):
    roots = {name.split(".")[0] for name in imports_of(module) if not name.startswith(".")}
    assert roots & FORBIDDEN_IMPORTS == set()
    assert roots <= ALLOWED_ROOTS, f"{module.name} imports {sorted(roots - ALLOWED_ROOTS)}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_contracts_and_the_package_itself_are_depended_on(module):
    for name in imports_of(module):
        assert not name.startswith(".."), f"{module.name} reaches out of the package with {name}"
        if name.startswith("eidos"):
            assert ".".join(name.split(".")[:2]) in ALLOWED_EIDOS, f"{module.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_engine_model_vendor_or_transport_name_appears(module):
    words = set(re.findall(r"[a-z0-9]+", module.read_text(encoding="utf-8").lower()))
    assert words & FORBIDDEN_WORDS == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_direct_call_to_io_dynamic_code_or_the_seed_dependent_hash_and_no_clock_or_random_text(module):
    text = module.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "print", "eval", "exec", "compile", "input", "__import__", "hash", "id"}, node.func.id
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            assert "__main__" not in ast.dump(node.test)
    for forbidden in ("datetime.now", "time.monotonic", "time.time", "uuid.uuid4", "random.", "os.environ"):
        assert forbidden not in text, forbidden


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_level_mutable_state(module):
    for node in ast.parse(module.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                continue
            assert not isinstance(node.value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp))


def ascii_only(path: Path) -> bool:
    return all(ord(character) < 128 for character in path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", [*MODULES, *sorted((ROOT / "tests" / "unit" / "knowledge").glob("*.py")), ROOT / "tests" / "support" / "eidos_knowledge_factories.py"],
                         ids=lambda p: p.name)
def test_the_package_and_its_tests_hold_only_ascii_so_no_invisible_or_normalisable_character_can_hide_in_them(path):
    assert ascii_only(path), f"{path.name} contains a non-ASCII character: build it from its code point instead"


def test_the_public_names_are_exactly_what_the_package_imports_from_its_modules():
    tree = ast.parse((KNOWLEDGE / "__init__.py").read_text(encoding="utf-8"))
    imported = {alias.asname or alias.name for node in tree.body if isinstance(node, ast.ImportFrom) for alias in node.names}
    (assign,) = [n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets)]
    exported = {element.value for element in assign.value.elts}
    assert imported == exported


def test_the_ingestion_result_and_the_refusals_are_returned_never_raised():
    tree = ast.parse((KNOWLEDGE / "snapshot.py").read_text(encoding="utf-8"))
    (function,) = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "build_snapshot"]
    assert [n for n in ast.walk(function) if isinstance(n, ast.Raise)] == []


def other_paths():
    for entry in sorted(SRC.iterdir()):
        if entry.name in {"knowledge", "__pycache__"} or entry.name.endswith(".egg-info"):
            continue
        if entry.is_dir():
            yield from sorted(entry.rglob("*.py"))
        elif entry.suffix == ".py":
            yield entry


@pytest.mark.parametrize("path", list(other_paths()), ids=lambda p: str(p.relative_to(SRC)))
def test_no_other_package_imports_the_knowledge_package_yet(path):
    for name in imports_of(path):
        assert not name.startswith("eidos.knowledge"), f"{path.relative_to(SRC)} imports {name}"


def test_importing_the_package_loads_no_other_eidos_layer_and_no_engine_or_model_library():
    code = (
        "import sys; sys.path.insert(0, 'src'); import eidos.knowledge\n"
        "eidos = sorted(m for m in sys.modules if m.startswith('eidos.') and not m.startswith(('eidos.knowledge', 'eidos.contracts')))\n"
        "engines = sorted(m for m in sys.modules if m.split('.')[0] in ('numpy', 'scipy', 'sklearn', 'torch', 'transformers', 'sentence_transformers', "
        "'tokenizers', 'qdrant_client', 'faiss', 'onnxruntime', 'httpx', 'requests', 'langgraph', 'langchain'))\n"
        "print(eidos, engines)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[] []"
