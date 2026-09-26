"""Static guards on ``eidos.recording`` (decisions.md D-152, D-158, D-160, D-172; CLAUDE.md §8; invariants 1, 2 and 9).

The recording package is an adapter: it may read the clock and draw an identifier because both are injected and it is not a deterministic
component. It still holds no ``MissionState``, never imports the reducer, never reaches a provider or backend, and is imported by nothing
below it. These are checks on the source, so they hold however the package is later extended.

V0.6 Step 6 adds one narrow, deliberate exception to "never reaches a provider or backend": ``a2a.py`` alone may
import ``eidos.a2a`` (the recording adapter that bridges a webhook delivery into a caller-owned ``EventLog``) — and
only that one module, never the package's own ``__init__.py``, so importing ``eidos.recording`` itself never pulls
in the optional ``a2a`` extra's ``httpx`` dependency (D-171). ``"a2a"`` is carved out of the vendor-name check below
for the same reason ``eidos.state`` and ``eidos.a2a`` itself already carve it out of theirs: it is the protocol this
one module exists to speak, not a vendor.
"""

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
RECORDING = SRC / "recording"
MODULES = sorted(RECORDING.glob("*.py"))

FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "http", "importlib", "io", "logging", "multiprocessing", "os", "pathlib", "pickle", "random", "requests",
    "secrets", "shelve", "shutil", "socket", "sqlite3", "ssl", "subprocess", "sys", "tempfile", "urllib", "httpx", "aiohttp", "numpy",
    "networkx", "langgraph", "langchain", "langsmith", "ollama", "openai", "anthropic",
}
ALLOWED_ROOTS = {"__future__", "collections", "dataclasses", "datetime", "enum", "threading", "time", "types", "typing", "uuid", "eidos"}
ALLOWED_EIDOS = {
    "eidos.a2a", "eidos.agents", "eidos.baseline", "eidos.capabilities", "eidos.compiler", "eidos.contracts", "eidos.knowledge", "eidos.recording",
    "eidos.runtime", "eidos.state", "eidos.validation",
}
# V1.3 Step 4 (decisions.md D-218, D-225): the one deliberate extension, for the retrieval adapter. One module, a fixed set of names, from the knowledge package root, one way: eidos.knowledge
# never imports this package (its own guard), and eidos.state still imports no knowledge at all. Pinned below so a further layer cannot be added without changing this on purpose.
PRE_RETRIEVAL_ALLOWED_EIDOS = {
    "eidos.a2a", "eidos.agents", "eidos.baseline", "eidos.capabilities", "eidos.compiler", "eidos.contracts", "eidos.recording",
    "eidos.runtime", "eidos.state", "eidos.validation",
}
KNOWLEDGE_BOUNDARY_MODULE = "adapters.py"
APPROVED_KNOWLEDGE_NAMES = {"KnowledgePort", "RetrievalFailure", "RetrievalRequest", "RetrievalResult", "result_problem"}
# Every vendor name this guard forbids, minus "a2a" itself (the protocol a2a.py exists to speak) — mirroring exactly
# how eidos.state and eidos.a2a itself already carve "a2a" out of their own vendor-name sets.
VENDOR_NAMES = {
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere", "ollama", "qdrant", "mcp",
    "langgraph", "langchain", "langsmith",
}


def imports_of(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    return found


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_expected_standard_library_and_no_io_network_or_model_library_is_imported(module):
    roots = {name.split(".")[0] for name in imports_of(module) if not name.startswith(".")}
    assert roots & FORBIDDEN_IMPORTS == set()
    assert roots <= ALLOWED_ROOTS, f"{module.name} imports {sorted(roots - ALLOWED_ROOTS)}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_layers_the_recorder_composes_are_imported_never_a_provider_or_a_backend(module):
    for name in imports_of(module):
        if name.startswith("eidos"):
            assert ".".join(name.split(".")[:2]) in ALLOWED_EIDOS, f"{module.name} imports {name}"
            assert "providers" not in name and "backends" not in name, f"{module.name} imports {name}"


def test_the_only_layer_added_to_what_the_recorder_composes_is_the_knowledge_boundary():
    assert ALLOWED_EIDOS - PRE_RETRIEVAL_ALLOWED_EIDOS == {"eidos.knowledge"}
    assert PRE_RETRIEVAL_ALLOWED_EIDOS <= ALLOWED_EIDOS


def knowledge_imports(module: Path) -> list[ast.AST]:
    return [
        node
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8")))
        if (isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[:2] == ["eidos", "knowledge"])
        or (isinstance(node, ast.Import) and any(alias.name.split(".")[:2] == ["eidos", "knowledge"] for alias in node.names))
        or (isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "eidos" and any(alias.name == "knowledge" for alias in node.names))
    ]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_retrieval_adapter_depends_on_the_knowledge_package(module):
    assert bool(knowledge_imports(module)) == (module.name == KNOWLEDGE_BOUNDARY_MODULE), module.name


def test_the_retrieval_adapter_takes_exactly_the_approved_knowledge_names_from_the_package_root_and_nothing_else():
    (statement,) = knowledge_imports(RECORDING / KNOWLEDGE_BOUNDARY_MODULE)
    assert isinstance(statement, ast.ImportFrom) and statement.module == "eidos.knowledge"
    assert {alias.name for alias in statement.names} == APPROVED_KNOWLEDGE_NAMES
    assert all(alias.asname is None for alias in statement.names)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_the_recorder_never_imports_the_reducer_so_it_cannot_write_state(module):
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "eidos.state.reducer", f"{module.name} imports the reducer module"
            if node.module in {"eidos.state", "eidos.state.reducer"}:
                assert all(alias.name not in {"reduce", "ReduceResult"} for alias in node.names), f"{module.name} imports the reducer"
        if isinstance(node, ast.Import):
            assert all(alias.name != "eidos.state.reducer" for alias in node.names), module.name


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_vendor_or_model_name_appears_in_the_recording_package(module):
    words = set(re.findall(r"[a-z0-9]+", module.read_text(encoding="utf-8").lower()))
    assert words & VENDOR_NAMES == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_a_recording_module_opens_no_file_prints_nothing_and_executes_no_generated_code(module):
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "print", "eval", "exec", "compile", "input", "__import__"}, f"{module.name}: {node.func.id}()"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_level_mutable_state(module):
    for node in ast.parse(module.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                continue
            assert not isinstance(node.value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)), f"{module.name}: a mutable module-level value"


def test_only_a2a_py_imports_eidos_a2a_and_the_package_init_never_does():
    """``eidos.a2a`` needs the optional ``a2a`` extra (``httpx``, D-171); importing ``eidos.recording`` itself must
    stay free of it (see the subprocess check below), so only ``a2a.py`` may reach for it — never ``__init__.py``,
    never any other module, so a plain ``import eidos.recording`` never transitively loads it."""
    for module in MODULES:
        imports_a2a = any(name == "eidos.a2a" or name.startswith("eidos.a2a.") for name in imports_of(module))
        assert imports_a2a == (module.name == "a2a.py"), module.name


def test_the_wall_clock_and_the_random_id_are_read_in_one_place_only_the_ports_module():
    for module in MODULES:
        text = module.read_text(encoding="utf-8")
        uses_clock = "datetime.now" in text or "time.monotonic" in text
        uses_uuid = "uuid.uuid4" in text
        assert (uses_clock or uses_uuid) == (module.name == "ports.py"), module.name


def test_importing_the_recording_package_loads_no_backend_provider_or_workflow_library():
    import subprocess
    import sys

    code = (
        "import sys; sys.path.insert(0, 'src'); import eidos.recording\n"
        "print(sorted(m for m in sys.modules if m.startswith(('eidos.backends', 'eidos.providers')) "
        "or m.split('.')[0] in ('langgraph', 'langchain', 'langsmith', 'requests', 'httpx')))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=SRC.parents[1])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
