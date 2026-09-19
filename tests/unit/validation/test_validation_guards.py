"""Static guards on ``eidos.validation`` (CLAUDE.md §2 invariants 5, 9, 14; §8; decisions.md D-103).

These read the package's source, so they fail the moment someone adds a
forbidden dependency, a vendor name, a shipped numeric default, or a hidden
source of non-determinism — not merely when behaviour visibly changes.
"""

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
VALIDATION = SRC / "validation"
CONTRACTS = SRC / "contracts"
MODULES = sorted(VALIDATION.glob("*.py"))

# Anything that does I/O, talks to the network, reads a clock, draws randomness,
# spawns work, or carries hidden process state. Deterministic components stay
# free of all of these (CLAUDE.md §8).
FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "datetime", "http", "importlib", "io", "logging", "multiprocessing",
    "os", "pathlib", "pickle", "random", "requests", "secrets", "shelve", "shutil", "socket",
    "sqlite3", "ssl", "subprocess", "sys", "tempfile", "threading", "time", "urllib", "uuid",
    "httpx", "aiohttp", "numpy", "networkx", "langgraph", "langchain",
}

# Model, vendor and SDK names never appear in contracts, planning, validation,
# compiler, runtime or state (invariant 9).
VENDOR_NAMES = (
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere",
    "langgraph", "langchain", "networkx", "qdrant", "a2a", "mcp",
)


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add(("." * node.level) + (node.module or ""))
    return found


def test_the_package_has_the_expected_modules():
    assert [m.name for m in MODULES] == [
        "__init__.py", "graph.py", "limits.py", "pipeline.py", "results.py", "stages.py",
    ]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_imports_io_network_clock_randomness_or_process_state(module):
    top_level = {name.lstrip(".").split(".")[0] for name in imported_modules(module) if not name.startswith(".")}
    assert top_level & FORBIDDEN_IMPORTS == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_validation_depends_only_on_contracts_and_itself_within_eidos(module):
    for name in imported_modules(module):
        if name.startswith("."):
            continue  # relative: inside eidos.validation
        if name.split(".")[0] == "eidos":
            assert name == "eidos.contracts", f"{module.name} imports {name}"


def test_contracts_do_not_depend_on_validation():
    # Dependency direction: validation -> contracts, never the reverse.
    for path in CONTRACTS.glob("*.py"):
        for name in imported_modules(path):
            assert "validation" not in name, f"{path.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_vendor_or_model_names(module):
    # "CLAUDE.md" is this repository's rules file, cited across the source
    # (CLAUDE.md §8 ...); it names a document, not a model dependency.
    text = module.read_text(encoding="utf-8").lower().replace("claude.md", "")
    words = set(re.findall(r"[a-z0-9]+", text))
    assert words & set(VENDOR_NAMES) == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_the_handoffs_illustrative_limits_are_not_shipped(module):
    # D-103 point 5: 600000 (latency_budget_ms) and 10,000 (tokens) are examples,
    # never defaults.
    source = module.read_text(encoding="utf-8")
    assert not re.search(r"\b(600_?000|10_?000)\b", source)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_numeric_limit_literal_is_assigned_anywhere_in_source(module):
    # D-103: SystemLimits has no built-in values. Any keyword or annotated default
    # named like a limit and given an int literal would be one.
    tree = ast.parse(module.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg and node.arg.startswith("max_"):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
                offenders.append(node.arg)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id.startswith("max_") and isinstance(node.value, ast.Constant):
                offenders.append(node.target.id)
    assert offenders == []


def test_no_module_level_system_limits_instance_exists_in_source():
    for module in MODULES:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                calls = [n for n in ast.walk(node.value) if isinstance(n, ast.Call)]
                assert not any(
                    isinstance(c.func, ast.Name) and c.func.id == "SystemLimits" for c in calls
                ), f"{module.name} builds a module-level SystemLimits"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_level_mutable_state_beyond_constants(module):
    # Module-level names must be constants, functions, classes or type aliases —
    # no list/dict/set literals that code could mutate as hidden state, except
    # ``__all__`` and the two fixed lookup tables that are never written to.
    allowed = {"__all__", "CODE_STAGE", "_FIXED_LIMIT"}
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
        if isinstance(getattr(node, "value", None), (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
            assert set(targets) <= allowed, f"{module.name}: mutable module state {targets}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_direct_calls_to_clock_randomness_or_io_builtins(module):
    tree = ast.parse(module.read_text(encoding="utf-8"))
    called = {
        n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert called & {"open", "print", "input", "exec", "eval", "compile", "__import__", "globals", "hash"} == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_recursion_in_graph_algorithms(module):
    # A function that calls itself by name is recursive; the graph algorithms must
    # be iterative so a long chain cannot raise RecursionError.
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        calls = {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert fn.name not in calls, f"{module.name}: {fn.name} calls itself"
