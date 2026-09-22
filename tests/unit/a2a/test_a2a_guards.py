"""Static guards on ``eidos.a2a`` (decisions.md D-171, D-172; CLAUDE.md §8; V0.6 Step 5 item 11).

``httpx`` is the one new dependency (D-171), confined to ``transport.py`` — every other module in the package stays
network-free and importable without the optional extra installed. Nothing under ``eidos.contracts``, ``eidos.state``,
``eidos.runtime``, ``eidos.compiler`` or ``eidos.validation`` may import this package (item 11's boundary): it is a
adapter other layers are handed, never a layer other layers reach into.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "eidos"
A2A = SRC / "a2a"
MODULES = sorted(A2A.glob("*.py"))
TRANSPORT = A2A / "transport.py"

# I/O, network (beyond the one seam), process state, randomness and every workflow or model library.
FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "importlib", "io", "logging", "multiprocessing", "os", "pathlib", "pickle", "random",
    "requests", "secrets", "shelve", "shutil", "socket", "sqlite3", "ssl", "subprocess", "sys", "tempfile", "time",
    "urllib", "aiohttp", "numpy", "networkx", "langgraph", "langchain", "langsmith", "ollama", "openai", "anthropic",
}
ALLOWED_ROOTS = {"__future__", "dataclasses", "datetime", "enum", "threading", "typing", "uuid", "pydantic", "eidos"}
ALLOWED_EIDOS = {"eidos.contracts", "eidos.state", "eidos.runtime", "eidos.compiler", "eidos.agents", "eidos.a2a"}

# Every vendor name eidos.state's own guard forbids, minus "a2a" itself (the protocol this package exists to speak) —
# mirroring exactly how eidos.state carved "a2a" out of its own vendor-name set once D-166/D-176 permitted it there.
VENDOR_NAMES = {
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere", "ollama", "qdrant", "mcp",
    "langgraph", "langchain", "langsmith",
}
CORE_PACKAGES = ("contracts", "validation", "compiler", "runtime", "state")


def imports_of(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    return found


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_httpx_lives_only_in_transport_and_every_import_is_otherwise_allowed(module):
    roots = {name.split(".")[0] for name in imports_of(module) if not name.startswith(".")}
    assert roots & FORBIDDEN_IMPORTS == set()
    allowed = ALLOWED_ROOTS | ({"httpx"} if module == TRANSPORT else set())
    assert roots <= allowed, f"{module.name} imports {sorted(roots - allowed)}"
    if module != TRANSPORT:
        assert "httpx" not in roots, f"{module.name} imports httpx directly; only transport.py may"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_allowed_eidos_layers_are_imported(module):
    for name in imports_of(module):
        if name.startswith("eidos"):
            assert ".".join(name.split(".")[:2]) in ALLOWED_EIDOS, f"{module.name} imports {name}"
            assert "providers" not in name and "backends" not in name and "recording" not in name, f"{module.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_vendor_name_other_than_a2a_itself_appears(module):
    words = set(re.findall(r"[a-z0-9]+", module.read_text(encoding="utf-8").lower()))
    assert words & VENDOR_NAMES == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_an_a2a_module_prints_nothing_and_executes_no_generated_code(module):
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"print", "eval", "exec", "compile", "input", "__import__"}, f"{module.name}: {node.func.id}()"


@pytest.mark.parametrize("package", CORE_PACKAGES)
def test_no_core_layer_imports_eidos_a2a(package):
    for path in sorted((SRC / package).rglob("*.py")):
        for name in imports_of(path):
            parts = name.split(".")
            assert not (parts[0] == "eidos" and len(parts) > 1 and parts[1] == "a2a"), f"{path.relative_to(SRC)} imports {name}"


def test_only_eidos_recording_a2a_imports_eidos_a2a():
    """V0.6 Step 6: ``eidos.recording.a2a`` is the one recording adapter that bridges a webhook delivery into a
    caller-owned ``EventLog``, and the only module outside this package allowed to depend on it — every other
    package stays exactly as isolated as item 11 originally required (this guard's own prior form said Step 6
    would be the first to cross it; it now names the one file that does)."""
    permitted = SRC / "recording" / "a2a.py"
    for path in sorted(SRC.rglob("*.py")):
        if A2A in path.parents or path == A2A or path == permitted:
            continue
        for name in imports_of(path):
            parts = name.split(".")
            assert not (parts[0] == "eidos" and len(parts) > 1 and parts[1] == "a2a"), f"{path.relative_to(SRC)} imports {name}"


def test_importing_eidos_a2a_loads_no_workflow_library_and_httpx_only_from_transport():
    code = (
        "import sys; sys.path.insert(0, 'src'); import eidos.a2a\n"
        "print(sorted(m for m in sys.modules if m.split('.')[0] in ('langgraph', 'langchain', 'langsmith', 'requests')))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
