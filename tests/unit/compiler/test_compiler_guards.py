"""Static guards on ``eidos.compiler`` (CLAUDE.md §2 invariants 1, 2, 9; §8; decisions.md D-113, D-114, D-115, D-123).

These read the package source, so they fail the moment someone adds a forbidden
dependency, a LangGraph or runtime import, a vendor name, a MissionState
reference, or a hidden source of non-determinism — not merely when behaviour
visibly changes.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

import eidos.validation

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
COMPILER = SRC / "compiler"
MODULES = sorted(COMPILER.glob("*.py"))

# Anything that does I/O, talks to the network, reads a clock, draws randomness,
# spawns work, or carries hidden process state — plus graph and LLM libraries the
# compiler must never depend on (D-115).
FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "datetime", "http", "importlib", "io", "logging", "multiprocessing",
    "os", "pathlib", "pickle", "random", "requests", "secrets", "shelve", "shutil", "socket",
    "sqlite3", "ssl", "subprocess", "sys", "tempfile", "threading", "time", "urllib", "uuid",
    "httpx", "aiohttp", "numpy", "networkx", "langgraph", "langchain",
}

# Model, vendor and SDK names never appear in the compiler (invariant 9). The
# compiler is also not the place to mention the backend that will execute it.
VENDOR_NAMES = (
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere",
    "langgraph", "langchain", "networkx", "qdrant", "a2a", "mcp",
)

# Contract names that would mean the compiler touches mission state or events (D-113, D-123).
STATE_AND_EVENT_NAMES = {
    "MissionState", "MissionEvent", "MissionEventType", "MissionStatus", "AgentTask",
    "TaskGenome", "ReliabilityContract",
}


def imports_of(path: Path) -> list[tuple[str, tuple[str, ...], int]]:
    """(module, imported names, relative level) for every import statement."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, (), 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", tuple(a.name for a in node.names), node.level))
    return found


def test_the_package_has_the_expected_modules():
    assert [m.name for m in MODULES] == ["__init__.py", "compile.py", "ir.py", "results.py"]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_imports_io_network_clock_randomness_or_process_state(module):
    top_level = {
        name.split(".")[0] for name, _, level in imports_of(module) if level == 0
    }
    assert top_level & FORBIDDEN_IMPORTS == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_the_compiler_depends_only_on_contracts_and_the_public_validation_surface(module):
    for name, imported, level in imports_of(module):
        if level:  # relative: inside eidos.compiler
            continue
        if name.split(".")[0] != "eidos":
            continue
        assert name in {"eidos.contracts", "eidos.validation"}, f"{module.name} imports {name}"
        if name == "eidos.validation":
            public = set(eidos.validation.__all__)
            assert set(imported) <= public, f"{module.name} imports non-public {set(imported) - public}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_the_compiler_never_imports_the_runtime_or_a_backend(module):
    for name, _, level in imports_of(module):
        assert not name.startswith(("eidos.runtime", "eidos.backends")), f"{module.name} imports {name}"
        assert "runtime" not in name.split(".") and "backends" not in name.split(".")


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_the_compiler_touches_no_mission_state_event_or_genome_contract(module):
    imported_names = {n for _, names, _ in imports_of(module) for n in names}
    assert imported_names & STATE_AND_EVENT_NAMES == set()


def test_importing_the_compiler_loads_no_langgraph_and_no_runtime():
    code = (
        "import sys\n"
        "sys.path.insert(0, 'src')\n"
        "import eidos.compiler\n"
        "loaded = sorted(m for m in sys.modules if m.split('.')[0] in ('langgraph', 'langchain') "
        "or m.startswith(('eidos.runtime', 'eidos.backends')))\n"
        "print(loaded)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=COMPILER.parents[2]
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_lower_layers_do_not_depend_on_the_compiler():
    # Dependency direction: contracts <- validation <- compiler.
    for package in ("contracts", "validation"):
        for path in (SRC / package).glob("*.py"):
            for name, _, _ in imports_of(path):
                assert "compiler" not in name.split("."), f"{path.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_vendor_or_model_names(module):
    # "CLAUDE.md" is this repository's rules file, cited across the source; it names a
    # document, not a model dependency.
    text = module.read_text(encoding="utf-8").lower().replace("claude.md", "")
    assert set(re.findall(r"[a-z0-9]+", text)) & set(VENDOR_NAMES) == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_level_mutable_state_beyond_constants(module):
    # Module-level literals must not be lists, dicts or sets that code could mutate as
    # hidden state. Tuples, frozenset(...) calls, enums and ``__all__`` are constants.
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in tree.body:
        value = getattr(node, "value", None)
        if isinstance(value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
            targets = [t.id for t in getattr(node, "targets", []) if isinstance(t, ast.Name)]
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets = [node.target.id]
            assert targets == ["__all__"], f"{module.name}: mutable module state {targets}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_direct_calls_to_io_or_dynamic_code_builtins(module):
    tree = ast.parse(module.read_text(encoding="utf-8"))
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert called & {"open", "print", "input", "exec", "eval", "compile", "__import__", "globals", "hash", "id"} == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_hash_ordered_collections_can_leak_into_output(module):
    # Output order derives from Plan.steps order. Sets are never built, and dicts are used
    # for lookup and membership only — never walked with .items()/.keys()/.values().
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        assert not isinstance(node, (ast.Set, ast.SetComp)), f"{module.name}: set literal"
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "set":
                pytest.fail(f"{module.name}: set() call")
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"items", "keys", "values"}:
                pytest.fail(f"{module.name}: dict view .{node.func.attr}()")


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_recursion(module):
    # A function that calls itself by name is recursive; the compiler must be iterative so
    # a very long chain cannot raise RecursionError.
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        calls = {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert fn.name not in calls, f"{module.name}: {fn.name} calls itself"


def test_the_compiler_does_not_reimplement_the_v02_stages():
    # Capabilities, resource ceilings, complexity limits and policy stay V0.2's job (D-114).
    text = " ".join(m.read_text(encoding="utf-8") for m in MODULES if m.name == "compile.py")
    for symbol in ("SystemLimits", "required_capabilities", "max_nodes", "max_depth", "max_parallel_branches",
                   "max_agent_calls", "check_capabilities", "check_resources", "check_complexity", "check_policy"):
        assert symbol not in text, f"compile.py mentions {symbol}"
