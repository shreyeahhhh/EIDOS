"""Static guards on ``eidos.knowledge`` (decisions.md D-208 to D-225, invariants 9, 10 and 15, CLAUDE.md section 8; V1.3 Steps 2 to 4).

The layer is deterministic and pure: no I/O, network, subprocess, clock, randomness, model call or hidden state, and it names no retrieval engine, vector
store or embedding model. It depends only on ``eidos.contracts``; it imports no agent, policy, transport, workflow library or infrastructure. The dependency
direction is one way (D-222 point 4): the only modules elsewhere in the repository that import it are ``eidos.agents.evidence_ledger`` and the retrieval adapter of
``eidos.recording``, each from the package root. Retrieval vocabulary is confined to two modules: ``retrieval.py`` (the contracts and the port) and ``lexical.py`` (the one retriever, exact,
in process and standard library only, D-225 reading 6, which may name its scheme and use decimal arithmetic); every other module stays free of it, and no module names an embedding, a vector
store, a reranker or a third-party engine. Other retrievers arrive at a later step (D-222), and these guards are revised deliberately then, not weakened.
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
MODULE_EXTRA_ROOTS = {"lexical.py": {"decimal"}}  # exact decimal arithmetic, whose logarithm is correctly rounded: the retriever's scores never depend on the platform (D-225 reading 6)
MODULE_EXEMPT_WORDS = {"lexical.py": {"bm25"}}  # the scheme names its weighting; a third-party library of that name is still an import, and forbidden
RETRIEVAL_MODULES = {"retrieval.py", "lexical.py"}
RETRIEVAL_NAME_PARTS = ("retriev", "search", "index", "port", "bm25", "rerank")
NEVER_NAME_PARTS = ("embed", "vector", "qdrant", "cosine", "semantic", "rerank", "ann_", "faiss")
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


def test_the_package_is_exactly_the_modules_of_the_structures_the_evidence_the_retrieval_contracts_and_the_one_retriever():
    assert [module.name for module in MODULES] == [
        "__init__.py", "chunking.py", "contracts.py", "evidence.py", "identity.py", "independence.py", "lexical.py", "retrieval.py", "snapshot.py",
    ]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_io_network_process_clock_randomness_or_engine_library_is_imported(module):
    roots = {name.split(".")[0] for name in imports_of(module) if not name.startswith(".")}
    assert roots & FORBIDDEN_IMPORTS == set()
    allowed = ALLOWED_ROOTS | MODULE_EXTRA_ROOTS.get(module.name, set())
    assert roots <= allowed, f"{module.name} imports {sorted(roots - allowed)}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_contracts_and_the_package_itself_are_depended_on(module):
    for name in imports_of(module):
        assert not name.startswith(".."), f"{module.name} reaches out of the package with {name}"
        if name.startswith("eidos"):
            assert ".".join(name.split(".")[:2]) in ALLOWED_EIDOS, f"{module.name} imports {name}"


FORBIDDEN_LAYERS = {
    "agents", "policy", "mcp", "a2a", "providers", "backends", "recording", "state", "runtime", "compiler", "capabilities", "validation", "planning",
    "selectors", "replanning", "expansion", "memory", "baseline", "telemetry",
}


def eidos_names_imported(path: Path) -> set[str]:
    """Every dotted ``eidos`` name a module imports, including a name taken with ``from eidos import x``."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if alias.name.split(".")[0] == "eidos")
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.split(".")[0] == "eidos":
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_the_knowledge_package_never_imports_an_agent_the_policy_layer_a_transport_a_workflow_library_or_infrastructure(module):
    """D-222 point 4: the direction is one way. Agents may depend on this package; this package never depends on them (nor on the layers around them)."""
    names = eidos_names_imported(module)
    reached = {name for name in names if len(name.split(".")) > 1 and name.split(".")[1] in FORBIDDEN_LAYERS}
    assert reached == set(), f"{module.name} imports {sorted(reached)}"
    assert {name for name in names if name.startswith("eidos.") and name.split(".")[1] not in {"contracts", "knowledge"}} == set()


def defined_names(path: Path) -> set[str]:
    return {node.name for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))}


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_retrieval_vocabulary_is_confined_to_the_two_modules_that_define_retrieval(module):
    """Every other module stays free of retrieval, search, index, port and scoring names: identity, chunking, the snapshot, independence and evidence know nothing of how a chunk is found."""
    if module.name in RETRIEVAL_MODULES:
        return
    for name in defined_names(module):
        lowered = name.lower()
        assert not any(part in lowered for part in RETRIEVAL_NAME_PARTS), f"{module.name} defines {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_defines_an_embedding_vector_semantic_or_reranking_name(module):
    for name in defined_names(module):
        lowered = name.lower()
        assert not any(part in lowered for part in NEVER_NAME_PARTS), f"{module.name} defines {name}"


def public_classes(path: Path) -> set[str]:
    return {node.name for node in ast.parse(path.read_text(encoding="utf-8")).body if isinstance(node, ast.ClassDef) and not node.name.startswith("_")}


def test_the_port_and_the_contracts_are_defined_in_retrieval_py_and_the_one_retriever_in_lexical_py():
    assert public_classes(KNOWLEDGE / "retrieval.py") == {
        "RetrievalRequest", "RetrievalFailureKind", "RetrievalFailure", "RetrievedChunk", "RetrievalResult", "KnowledgePort",
    }
    assert public_classes(KNOWLEDGE / "lexical.py") == {"LexicalKnowledgePort"}


def test_the_retriever_answers_by_returning_and_never_raises_for_a_retrieval_outcome():
    tree = ast.parse((KNOWLEDGE / "lexical.py").read_text(encoding="utf-8"))
    for function in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in {"retrieve", "_ranked"}):
        assert [n for n in ast.walk(function) if isinstance(n, ast.Raise)] == [], function.name
    (constructor,) = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "__init__"]
    assert len([n for n in ast.walk(constructor) if isinstance(n, ast.Raise)]) == 1  # a malformed knowledge base id is a programming error, refused when the port is made


def test_only_the_retriever_uses_decimal_arithmetic():
    for module in MODULES:
        roots = {name.split(".")[0] for name in imports_of(module) if not name.startswith(".")}
        assert ("decimal" in roots) == (module.name == "lexical.py"), module.name


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_engine_model_vendor_or_transport_name_appears(module):
    words = set(re.findall(r"[a-z0-9]+", module.read_text(encoding="utf-8").lower()))
    assert words & (FORBIDDEN_WORDS - MODULE_EXEMPT_WORDS.get(module.name, set())) == set()


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


@pytest.mark.parametrize(
    "path",
    [
        *MODULES,
        *sorted((ROOT / "tests" / "unit" / "knowledge").glob("*.py")),
        ROOT / "src" / "eidos" / "agents" / "evidence_ledger.py",
        ROOT / "src" / "eidos" / "state" / "evidence_audit.py",
        ROOT / "tests" / "unit" / "agents" / "test_agents_evidence_ledger.py",
        ROOT / "tests" / "unit" / "state" / "test_state_retrieval_facts.py",
        ROOT / "tests" / "unit" / "state" / "test_state_evidence_audit.py",
        ROOT / "tests" / "unit" / "recording" / "test_recording_retrieval.py",
        *sorted((ROOT / "tests" / "integration" / "retrieval").glob("*.py")),
        ROOT / "tests" / "support" / "eidos_knowledge_factories.py",
        ROOT / "tests" / "support" / "eidos_retrieval_fact_factories.py",
        ROOT / "tests" / "support" / "eidos_retrieval_fixture.py",
        ROOT / "tests" / "support" / "eidos_retrieval_benchmark.py",
        ROOT / "tests" / "scenarios" / "test_retrieval_benchmark_lexical.py",
    ],
    ids=lambda p: p.name,
)
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


@pytest.mark.parametrize("name", ["evidence_from_snapshot", "legacy_supplied_record", "legacy_tool_record"])
def test_an_evidence_that_cannot_be_made_is_a_returned_refusal_never_a_raise(name):
    tree = ast.parse((KNOWLEDGE / "evidence.py").read_text(encoding="utf-8"))
    (function,) = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    assert [n for n in ast.walk(function) if isinstance(n, ast.Raise)] == []


def other_paths():
    for entry in sorted(SRC.iterdir()):
        if entry.name in {"knowledge", "__pycache__"} or entry.name.endswith(".egg-info"):
            continue
        if entry.is_dir():
            yield from sorted(entry.rglob("*.py"))
        elif entry.suffix == ".py":
            yield entry


BOUNDARIES = {SRC / "agents" / "evidence_ledger.py", SRC / "recording" / "adapters.py"}


@pytest.mark.parametrize("path", list(other_paths()), ids=lambda p: str(p.relative_to(SRC)))
def test_only_the_evidence_ledger_and_the_retrieval_adapter_import_the_knowledge_package_and_only_from_its_root(path):
    reached = sorted(name for name in eidos_names_imported(path) if name == "eidos.knowledge" or name.startswith("eidos.knowledge."))
    if path in BOUNDARIES:
        assert [name for name in imports_of(path) if name.startswith("eidos.knowledge")] == ["eidos.knowledge"], "a boundary module imports from the package root, once"
    else:
        assert reached == [], f"{path.relative_to(SRC)} imports {reached}"


def test_the_state_package_imports_no_knowledge_at_all_its_facts_mirror_the_identifiers():
    for path in sorted((SRC / "state").glob("*.py")):
        assert not [n for n in eidos_names_imported(path) if n.split(".")[:2] == ["eidos", "knowledge"]], path.name


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
