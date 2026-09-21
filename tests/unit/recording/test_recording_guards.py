"""Static guards on ``eidos.recording`` (decisions.md D-152, D-158, D-160; CLAUDE.md §8; invariants 1, 2 and 9).

The recording package is an adapter: it may read the clock and draw an identifier because both are injected and it is not a deterministic
component. It still holds no ``MissionState``, never imports the reducer, never reaches a provider or backend, and is imported by nothing
below it. These are checks on the source, so they hold however the package is later extended.
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
    "eidos.agents", "eidos.baseline", "eidos.capabilities", "eidos.compiler", "eidos.contracts", "eidos.recording", "eidos.runtime",
    "eidos.state", "eidos.validation",
}
VENDOR_NAMES = {
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere", "ollama", "qdrant", "a2a", "mcp",
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
