"""Static guards on ``eidos.knowledge`` (decisions.md D-208 to D-226, invariants 9, 10 and 15, CLAUDE.md section 8; V1.3 Steps 2 to 5).

The layer is deterministic and pure: no I/O, network, subprocess, clock, randomness, model call or hidden state, and it names no vector store, reranker or third-party engine. It depends only on
``eidos.contracts``; it imports no agent, policy, transport, workflow library or infrastructure. The dependency direction is one way (D-222 point 4): the only modules elsewhere in the repository
that import it are ``eidos.agents.evidence_ledger`` and the retrieval adapter of ``eidos.recording``, each from the package root. Retrieval vocabulary is confined to three modules: ``retrieval.py``
(the contracts and the port), ``lexical.py`` (the exact in-process lexical retriever, standard library only, which may use decimal arithmetic, D-225 reading 6) and ``semantic.py`` (the pure half of
semantic retrieval: the pinned model identity, the embedder protocol and exact cosine, standard library only, which may use ``math``, D-226 reading 1).

Step 5 (D-226) adds two modules that are not pure and are held to their own, narrower rules: ``semantic_process.py`` is the one adapter in the package that starts a process (it may import ``subprocess``
and its plumbing and nothing of any model library) and ``semantic_worker.py`` is a program for the isolated interpreter, the only file anywhere in ``src`` that names the model library (lazily, inside
a function), and it imports no ``eidos`` and no ``pydantic``. Neither is exported by the package root or imported by anything else in ``src``. These guards are revised deliberately for them, not weakened
for the rest: every other module keeps every rule it had.
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
PROCESS_MODULE, WORKER_MODULE, SEMANTIC_MODULE = "semantic_process.py", "semantic_worker.py", "semantic.py"
MODEL_LIBRARIES = {"numpy", "sentence_transformers", "tokenizers", "torch", "transformers", "safetensors", "huggingface_hub", "scipy", "sklearn", "onnxruntime"}
MODULE_EXTRA_ROOTS = {  # what a module may import beyond ALLOWED_ROOTS, each with the reason it is allowed
    "lexical.py": {"decimal"},  # exact decimal arithmetic, whose logarithm is correctly rounded: the retriever's scores never depend on the platform (D-225 reading 6)
    SEMANTIC_MODULE: {"math"},  # math.fsum and math.sqrt: exact summation for cosine (D-226 reading 4)
    PROCESS_MODULE: {"os", "pathlib", "queue", "subprocess", "sys", "threading"},  # the one adapter that starts the isolated worker (D-226 reading 6): no model library, no socket, no time
}
# The worker is a program, not a module of the layer: it imports the standard library, and the model library lazily, and nothing of EIDOS (D-226 reading 1).
WORKER_ROOTS = {"argparse", "hashlib", "json", "math", "os", "pathlib", "platform", "socket", "sys", "threading", "time"} | {"numpy", "sentence_transformers", "tokenizers", "torch", "transformers"}
MODULE_EXEMPT_WORDS = {  # words a forbidden-name check would refuse, and why each is allowed
    "lexical.py": {"bm25"},  # the scheme names its weighting; a third-party library of that name is still an import, and forbidden
    SEMANTIC_MODULE: {"transformers"},  # only inside the pinned model's name (test_the_model_library_is_named_only_by_the_pinned_model_name_and_the_worker)
    WORKER_MODULE: {"torch", "transformers", "numpy"},  # the one file that loads the library
}
MODULE_EXEMPT_CALLS = {WORKER_MODULE: {"open"}}  # reading the model files to verify their digests, before anything is loaded
MODULE_EXEMPT_TEXT = {WORKER_MODULE: {"time.monotonic", "os.environ"}, PROCESS_MODULE: {"os.environ"}}  # the watchdog's clock; the offline flags and the worker's minimal environment
RETRIEVAL_MODULES = {"retrieval.py", "lexical.py", SEMANTIC_MODULE}
RETRIEVAL_NAME_PARTS = ("retriev", "search", "index", "port", "bm25", "rerank")
SEMANTIC_NAME_PARTS = ("embed", "vector", "cosine", "semantic")  # confined to the three semantic modules
NEVER_NAME_PARTS = ("qdrant", "rerank", "ann_", "faiss", "cross_encoder", "crossencoder")  # defined nowhere in the package
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


def test_the_package_is_exactly_the_modules_of_the_structures_the_evidence_the_retrieval_contracts_the_two_retrievers_and_the_semantic_boundary():
    assert [module.name for module in MODULES] == [
        "__init__.py", "chunking.py", "contracts.py", "evidence.py", "identity.py", "independence.py", "lexical.py", "retrieval.py", "semantic.py", "semantic_process.py", "semantic_worker.py",
        "snapshot.py",
    ]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_io_network_process_clock_randomness_or_engine_library_is_imported(module):
    roots = {name.split(".")[0] for name in imports_of(module) if not name.startswith(".")}
    if module.name == WORKER_MODULE:
        assert roots <= WORKER_ROOTS, f"{module.name} imports {sorted(roots - WORKER_ROOTS)}"
        return
    extra = MODULE_EXTRA_ROOTS.get(module.name, set())
    assert roots & (FORBIDDEN_IMPORTS - extra) == set()
    assert roots <= ALLOWED_ROOTS | extra, f"{module.name} imports {sorted(roots - ALLOWED_ROOTS - extra)}"
    assert not roots & MODEL_LIBRARIES


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
def test_retrieval_vocabulary_is_confined_to_the_three_modules_that_define_retrieval(module):
    """Every other module stays free of retrieval, search, index, port and scoring names: identity, chunking, the snapshot, independence and evidence know nothing of how a chunk is found;
    and neither the process client nor the worker defines a retrieval name: what they do is embed."""
    if module.name in RETRIEVAL_MODULES:
        return
    for name in defined_names(module):
        lowered = name.lower()
        assert not any(part in lowered for part in RETRIEVAL_NAME_PARTS), f"{module.name} defines {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_defines_a_vector_store_reranker_or_approximate_search_name(module):
    for name in defined_names(module):
        lowered = name.lower()
        assert not any(part in lowered for part in NEVER_NAME_PARTS), f"{module.name} defines {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_embedding_vector_cosine_and_semantic_names_are_confined_to_the_three_semantic_modules(module):
    if module.name in {SEMANTIC_MODULE, PROCESS_MODULE, WORKER_MODULE}:
        return
    for name in defined_names(module):
        lowered = name.lower()
        assert not any(part in lowered for part in SEMANTIC_NAME_PARTS), f"{module.name} defines {name}"


def public_classes(path: Path) -> set[str]:
    return {node.name for node in ast.parse(path.read_text(encoding="utf-8")).body if isinstance(node, ast.ClassDef) and not node.name.startswith("_")}


def test_the_port_and_the_contracts_are_defined_in_retrieval_py_and_the_one_retriever_in_lexical_py():
    assert public_classes(KNOWLEDGE / "retrieval.py") == {
        "RetrievalRequest", "RetrievalFailureKind", "RetrievalFailure", "RetrievedChunk", "RetrievalResult", "KnowledgePort",
    }
    assert public_classes(KNOWLEDGE / "lexical.py") == {"LexicalKnowledgePort"}


def test_the_pure_half_of_semantic_retrieval_the_process_client_and_the_worker_define_exactly_their_own_classes():
    assert public_classes(KNOWLEDGE / SEMANTIC_MODULE) == {"SemanticModelIdentity", "EmbeddedText", "EmbedderFailureKind", "EmbedderFailure", "Embedder", "SemanticKnowledgePort"}
    assert public_classes(KNOWLEDGE / PROCESS_MODULE) == {"WorkerLimits", "WorkerEnvironment", "WorkerReady", "IsolatedEmbedder"}
    assert public_classes(KNOWLEDGE / WORKER_MODULE) == {"WorkerRefusal", "SentenceTransformerModel"}


def test_the_semantic_port_answers_by_returning_and_only_its_opening_refuses_a_programming_error():
    tree = ast.parse((KNOWLEDGE / SEMANTIC_MODULE).read_text(encoding="utf-8"))
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert [n for n in ast.walk(functions["retrieve"]) if isinstance(n, ast.Raise)] == []
    assert len([n for n in ast.walk(functions["open"]) if isinstance(n, ast.Raise)]) == 2  # a malformed knowledge base id and a batch of no texts: refused when the port is made
    assert len([n for n in ast.walk(functions["cosine_similarity"]) if isinstance(n, ast.Raise)]) == 2  # a precondition of the pure function; the port never lets it be broken


def test_the_process_client_answers_by_returning_and_raises_nothing_for_an_outcome_of_the_boundary():
    tree = ast.parse((KNOWLEDGE / PROCESS_MODULE).read_text(encoding="utf-8"))
    for function in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        raises = [n for n in ast.walk(function) if isinstance(n, ast.Raise)]
        assert raises == [] or function.name == "_check_the_worker_can_start_before_it_expires", function.name  # a validator refusing an impossible set of limits


def test_the_retriever_answers_by_returning_and_never_raises_for_a_retrieval_outcome():
    tree = ast.parse((KNOWLEDGE / "lexical.py").read_text(encoding="utf-8"))
    for function in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in {"retrieve", "_ranked"}):
        assert [n for n in ast.walk(function) if isinstance(n, ast.Raise)] == [], function.name
    (constructor,) = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "__init__"]
    assert len([n for n in ast.walk(constructor) if isinstance(n, ast.Raise)]) == 1  # a malformed knowledge base id is a programming error, refused when the port is made


def test_only_the_lexical_retriever_uses_decimal_arithmetic():
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
            assert node.func.id not in {"open", "print", "eval", "exec", "compile", "input", "__import__", "hash", "id"} - MODULE_EXEMPT_CALLS.get(module.name, set()), node.func.id
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and module.name != WORKER_MODULE:
            assert "__main__" not in ast.dump(node.test)
    for forbidden in ("datetime.now", "time.monotonic", "time.time", "uuid.uuid4", "random.", "os.environ"):
        if forbidden not in MODULE_EXEMPT_TEXT.get(module.name, set()):
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
        ROOT / "tests" / "protocol" / "test_semantic_worker_protocol.py",
        *sorted((ROOT / "tests" / "integration" / "semantic").glob("*.py")),
        ROOT / "tests" / "support" / "eidos_semantic_process_factories.py",
        ROOT / "tests" / "support" / "fake_semantic_worker.py",
        ROOT / "tests" / "support" / "misbehaving_semantic_worker.py",
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


def test_importing_the_package_loads_no_other_eidos_layer_no_engine_or_model_library_and_no_eidos_process_code():
    code = (
        "import sys; sys.path.insert(0, 'src'); import eidos.knowledge\n"
        "eidos = sorted(m for m in sys.modules if m.startswith('eidos.') and not m.startswith(('eidos.knowledge', 'eidos.contracts')))\n"
        "engines = sorted(m for m in sys.modules if m.split('.')[0] in ('numpy', 'scipy', 'sklearn', 'torch', 'transformers', 'sentence_transformers', "
        "'tokenizers', 'safetensors', 'huggingface_hub', 'qdrant_client', 'faiss', 'onnxruntime', 'httpx', 'requests', 'langgraph', 'langchain'))\n"
        "process = sorted(m for m in sys.modules if m in ('eidos.knowledge.semantic_process', 'eidos.knowledge.semantic_worker'))\n"  # EIDOS's process code; the standard library may load subprocess for its own reasons
        "print(eidos, engines, process)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[] [] []"


def all_source_files():
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" not in path.parts:
            yield path


def test_only_the_semantic_worker_names_the_model_library_anywhere_in_the_source():
    """D-226 ruling 2: the model library never leaks into EIDOS. It is named by one file, a program run by the isolated interpreter, and even there only lazily, inside a function."""
    for path in all_source_files():
        roots = {name.split(".")[0] for name in imports_of(path) if not name.startswith(".")}
        if path == KNOWLEDGE / WORKER_MODULE:
            assert roots & MODEL_LIBRARIES == {"numpy", "sentence_transformers", "tokenizers", "torch", "transformers"}
        else:
            assert roots & MODEL_LIBRARIES == set(), f"{path.relative_to(SRC)} imports {sorted(roots & MODEL_LIBRARIES)}"
    top_level = ast.parse((KNOWLEDGE / WORKER_MODULE).read_text(encoding="utf-8")).body
    top_level_roots = {alias.name.split(".")[0] for node in top_level if isinstance(node, ast.Import) for alias in node.names}
    top_level_roots |= {node.module.split(".")[0] for node in top_level if isinstance(node, ast.ImportFrom) and node.module}
    assert top_level_roots & MODEL_LIBRARIES == set(), "the worker imports the library inside a function, so importing the file loads nothing"


def test_the_model_library_is_named_only_by_the_pinned_model_name_and_the_worker():
    """``semantic.py`` holds the pinned model's name, which contains the word the library is called by; it appears in that one string constant and nowhere else in the module."""
    tree = ast.parse((KNOWLEDGE / SEMANTIC_MODULE).read_text(encoding="utf-8"))
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and "transformers" in n.value.lower()]
    assert strings == ["sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"]
    identifiers = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | defined_names(KNOWLEDGE / SEMANTIC_MODULE)
    assert not [name for name in identifiers if "transformers" in name.lower()]
    docstrings = [ast.get_docstring(n) or "" for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef))]
    assert not [text for text in docstrings if "transformers" in text.lower()]


def test_no_vector_database_or_cross_encoder_is_named_anywhere_in_the_source_or_the_dependencies():
    """D-226 ruling 3: Qdrant stays deferred and there is no cross-encoder. Nothing in the source, and nothing in ``pyproject.toml``, names either."""
    for path in [*all_source_files(), ROOT / "pyproject.toml"]:
        text = path.read_text(encoding="utf-8").lower()
        for name in ("qdrant", "faiss", "cross-encoder", "cross_encoder", "crossencoder", "chromadb", "pinecone", "weaviate", "milvus", "hnsw"):
            assert name not in text, f"{path.name} names {name}"


def test_the_dependencies_name_no_model_library_the_main_environment_needs_none():
    """D-226 ruling 2: no Python 3.13 model dependency is added to the main environment, and ``pyproject.toml`` is not changed to support semantic retrieval."""
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    declared = list(project["dependencies"]) + [dep for group in project.get("optional-dependencies", {}).values() for dep in group]
    names = {re.split(r"[\[<>=!~ ;]", dependency, maxsplit=1)[0].lower().replace("_", "-") for dependency in declared}
    assert names & {"torch", "sentence-transformers", "transformers", "tokenizers", "numpy", "scipy", "scikit-learn", "safetensors", "huggingface-hub", "onnxruntime"} == set()
    assert project["requires-python"] == ">=3.11"


def test_the_package_root_exports_no_process_or_worker_code_and_nothing_else_in_the_source_imports_either():
    root_imports = imports_of(KNOWLEDGE / "__init__.py")
    assert not [name for name in root_imports if "semantic_process" in name or "semantic_worker" in name]
    for path in all_source_files():
        reached = [name for name in imports_of(path) if "semantic_process" in name or "semantic_worker" in name]
        assert reached == [], f"{path.relative_to(SRC)} imports {reached}"


def test_the_process_client_depends_on_the_pure_semantic_module_and_the_worker_on_nothing_of_eidos():
    assert sorted({name for name in imports_of(KNOWLEDGE / PROCESS_MODULE) if name.startswith(".")}) == [".semantic"]
    assert {name for name in imports_of(KNOWLEDGE / PROCESS_MODULE) if name.startswith("eidos")} == {"eidos.contracts"}
    assert sorted({name for name in imports_of(KNOWLEDGE / SEMANTIC_MODULE) if name.startswith(".")}) == [".contracts", ".identity", ".retrieval"]
    assert [name for name in imports_of(KNOWLEDGE / WORKER_MODULE) if name.startswith((".", "eidos", "pydantic"))] == []
    for module in MODULES:
        if module.name not in {"__init__.py", PROCESS_MODULE}:
            assert [name for name in imports_of(module) if name in {".semantic_process", ".semantic_worker"}] == [], module.name
