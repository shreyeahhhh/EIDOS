"""Static guards on ``eidos.state`` (decisions.md D-152, D-153, D-155, D-157; CLAUDE.md §8; invariants 1, 2, 9, 15).

The state package is a core layer: pure, vendor-free, importing only the contract and runtime layers, reading no clock and doing no I/O.
Nothing below it imports it, and it never imports the recording adapters. These are checks on the source, so they hold however the package
is later extended.
"""

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
STATE = SRC / "state"
MODULES = sorted(STATE.glob("*.py"))

# I/O, network, clock, randomness, process state, threads and every workflow or model library: the reducer must be deterministic (D-155).
FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "datetime", "http", "importlib", "io", "logging", "multiprocessing", "os", "pathlib", "pickle", "random",
    "requests", "secrets", "shelve", "shutil", "socket", "sqlite3", "ssl", "subprocess", "sys", "tempfile", "threading", "time", "urllib",
    "uuid", "httpx", "aiohttp", "numpy", "networkx", "langgraph", "langchain", "langsmith", "ollama", "openai", "anthropic",
}
ALLOWED_ROOTS = {"__future__", "collections", "dataclasses", "enum", "types", "typing", "pydantic", "eidos"}
ALLOWED_EIDOS = {"eidos.contracts", "eidos.runtime", "eidos.state"}

VENDOR_NAMES = {
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere", "ollama", "qdrant", "a2a", "mcp",
    "langgraph", "langchain", "langsmith",
}
LOWER_PACKAGES = ("contracts", "validation", "compiler", "runtime", "backends", "agents", "capabilities", "providers")
FORBIDDEN_FOR_LOWER = {"state", "recording"}


def imports_of(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    return found


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_io_network_clock_randomness_threads_or_model_library_is_imported(module):
    roots = {name.split(".")[0] for name in imports_of(module) if not name.startswith(".")}
    assert roots & FORBIDDEN_IMPORTS == set()
    assert roots <= ALLOWED_ROOTS, f"{module.name} imports {sorted(roots - ALLOWED_ROOTS)}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_contract_and_runtime_layers_are_imported_never_an_agent_provider_capability_baseline_or_the_recorders(module):
    for name in imports_of(module):
        if name.startswith("eidos"):
            assert ".".join(name.split(".")[:2]) in ALLOWED_EIDOS, f"{module.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_vendor_or_model_name_appears_in_the_state_package(module):
    words = set(re.findall(r"[a-z0-9]+", module.read_text(encoding="utf-8").lower()))
    assert words & VENDOR_NAMES == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_a_state_module_opens_no_file_prints_nothing_and_executes_no_generated_code(module):
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "print", "eval", "exec", "compile", "input", "__import__"}, f"{module.name}: {node.func.id}()"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_level_mutable_state(module):
    for node in ast.parse(module.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                continue  # the export list is a convention, not state; nothing else is exempt
            assert not isinstance(node.value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)), (
                f"{module.name}: a mutable module-level value"
            )


@pytest.mark.parametrize("package", LOWER_PACKAGES)
def test_no_lower_layer_imports_the_state_or_recording_packages(package):
    for path in sorted((SRC / package).rglob("*.py")):
        for name in imports_of(path):
            parts = name.split(".")
            assert not (parts[0] == "eidos" and len(parts) > 1 and parts[1] in FORBIDDEN_FOR_LOWER), f"{path.relative_to(SRC)} imports {name}"


def test_the_baseline_runner_does_not_import_the_state_or_recording_packages():
    # The runner defines the observer protocol; the recorder imports the runner, never the other way round (D-158, D-160 item 8).
    for name in imports_of(SRC / "baseline.py"):
        parts = name.split(".")
        assert not (parts[0] == "eidos" and len(parts) > 1 and parts[1] in FORBIDDEN_FOR_LOWER), f"baseline.py imports {name}"


def test_importing_the_state_package_loads_no_agent_provider_backend_capability_baseline_or_workflow_library():
    import subprocess
    import sys

    code = (
        "import sys; sys.path.insert(0, 'src'); import eidos.state\n"
        "print(sorted(m for m in sys.modules if m.startswith(('eidos.agents', 'eidos.providers', 'eidos.backends', 'eidos.capabilities', "
        "'eidos.baseline', 'eidos.recording')) or m.split('.')[0] in ('langgraph', 'langchain', 'langsmith', 'requests', 'httpx')))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=SRC.parents[1])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
