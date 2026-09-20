"""Static guards on ``eidos.agents`` (decisions.md D-135, D-140; CLAUDE.md §8; invariants 3, 9).

The agents package is vendor-free, does no I/O beyond its ports, never reaches a provider, and no core layer
ever imports it. These are checks on the source, so they hold however the agents are later implemented.
"""

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
AGENTS = SRC / "agents"
MODULES = sorted(AGENTS.glob("*.py"))

# I/O, network, clock, randomness, process state and every workflow or model library: an agent is read-only (D-140).
FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "datetime", "http", "importlib", "io", "logging", "multiprocessing", "os", "pathlib",
    "pickle", "random", "requests", "secrets", "shelve", "shutil", "socket", "sqlite3", "ssl", "subprocess", "sys",
    "tempfile", "time", "urllib", "uuid", "httpx", "aiohttp", "numpy", "networkx", "langgraph", "langchain",
    "langsmith", "ollama", "openai", "anthropic",
}
# The only third-party or standard-library modules the agents package may import.
ALLOWED_ROOTS = {"__future__", "collections", "dataclasses", "enum", "re", "threading", "typing", "pydantic", "eidos"}
ALLOWED_EIDOS = {"eidos.contracts", "eidos.runtime", "eidos.compiler", "eidos.capabilities", "eidos.agents"}

VENDOR_NAMES = {
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere", "ollama", "qdrant", "a2a", "mcp",
    "langgraph", "langchain", "langsmith",
}
CORE_PACKAGES = ("contracts", "validation", "compiler", "runtime", "backends")


def imports_of(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    return found


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_io_network_clock_randomness_or_model_library_is_imported(module):
    roots = {name.split(".")[0] for name in imports_of(module) if not name.startswith(".")}
    assert roots & FORBIDDEN_IMPORTS == set()
    assert roots <= ALLOWED_ROOTS, f"{module.name} imports {sorted(roots - ALLOWED_ROOTS)}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_eidos_layers_an_agent_may_depend_on_are_imported(module):
    for name in imports_of(module):
        if name.startswith("eidos"):
            assert ".".join(name.split(".")[:2]) in ALLOWED_EIDOS, f"{module.name} imports {name}"
            assert "providers" not in name and "backends" not in name, f"{module.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_vendor_or_model_name_appears_in_the_agents_package(module):
    words = set(re.findall(r"[a-z0-9]+", module.read_text(encoding="utf-8").lower()))
    assert words & VENDOR_NAMES == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_an_agent_module_opens_no_file_prints_nothing_and_executes_no_generated_code(module):
    # Invariant 3 and D-140: nothing a model returns is ever executed, and an agent takes no action.
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "print", "eval", "exec", "compile", "input", "__import__"}, (
                f"{module.name}: {node.func.id}()"
            )


@pytest.mark.parametrize("package", CORE_PACKAGES)
def test_no_core_layer_imports_agents_capabilities_or_providers(package):
    for path in sorted((SRC / package).rglob("*.py")):
        for name in imports_of(path):
            parts = name.split(".")
            assert not (parts[0] == "eidos" and len(parts) > 1 and parts[1] in {"agents", "capabilities", "providers"}), (
                f"{path.relative_to(SRC)} imports {name}"
            )


def test_importing_the_agents_package_loads_no_provider_backend_or_workflow_library():
    import subprocess
    import sys

    code = (
        "import sys; sys.path.insert(0, 'src'); import eidos.agents\n"
        "print(sorted(m for m in sys.modules if m.split('.')[0] in ('langgraph', 'langchain', 'langsmith', 'requests', 'httpx') "
        "or m.startswith('eidos.providers') or m.startswith('eidos.backends')))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=SRC.parents[1])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
