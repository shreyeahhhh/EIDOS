"""Static guards on ``eidos.expansion`` (decisions.md D-194, D-195; CLAUDE.md §2 invariants 1, 2, 9; V0.9 Step 2).

Mirrors ``tests/unit/planning/test_planning_guards.py``'s own discipline for a sibling core layer: these read the
package source, so they fail the moment someone adds a forbidden dependency, a vendor name, a hidden source of
non-determinism, or a call into the feasibility gate this layer has no business re-running.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
EXPANSION = SRC / "expansion"
MODULES = sorted(EXPANSION.glob("*.py"))

# I/O, network, clock, randomness and process-state modules this deterministic core layer must never depend on
# (mirrors eidos.planning's own list one layer down).
FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "datetime", "http", "importlib", "io", "logging", "multiprocessing",
    "os", "pathlib", "pickle", "random", "requests", "secrets", "shelve", "shutil", "socket",
    "sqlite3", "ssl", "subprocess", "sys", "tempfile", "threading", "time", "urllib", "uuid",
    "httpx", "aiohttp", "numpy", "networkx", "langgraph", "langchain", "langsmith",
}

VENDOR_NAMES = (
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere", "litellm",
    "langgraph", "langchain", "networkx", "qdrant", "a2a", "mcp", "rag", "laya",
)


def imports_of(path: Path) -> list[tuple[str, tuple[str, ...], int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, (), 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", tuple(a.name for a in node.names), node.level))
    return found


def test_the_package_has_the_expected_modules():
    assert [m.name for m in MODULES] == ["__init__.py", "expand.py"]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_imports_io_network_clock_randomness_or_process_state(module):
    top_level = {name.split(".")[0] for name, _, level in imports_of(module) if level == 0}
    assert top_level & FORBIDDEN_IMPORTS == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_expansion_depends_only_on_eidos_contracts_and_planning(module):
    for name, _imported, level in imports_of(module):
        if level:  # relative: inside eidos.expansion
            continue
        if name.split(".")[0] != "eidos":
            continue
        assert name in {"eidos.contracts", "eidos.planning"}, f"{module.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_expansion_never_imports_validation_compiler_runtime_or_any_adapter_package(module):
    forbidden_roots = {
        "validation", "compiler", "runtime", "state", "agents", "providers", "backends", "a2a",
        "recording", "capabilities", "selectors", "baseline",
    }
    for name, _, _ in imports_of(module):
        parts = name.split(".")
        assert not (parts and parts[0] == "eidos" and len(parts) > 1 and parts[1] in forbidden_roots), \
            f"{module.name} imports {name}"


def test_expansion_does_not_call_or_reimplement_feasibility():
    # Mirrors test_planning_guards.py's own test_selection_does_not_rerun_or_reimplement_feasibility exactly:
    # admissibility was already decided before a Strategy was selected (D-180, D-183) — proven by absence.
    text = " ".join(m.read_text(encoding="utf-8") for m in MODULES if m.name == "expand.py")
    for symbol in ("check_feasibility", "FeasibilityReport", "FeasibilityViolation", "FeasibilityCheck"):
        assert symbol not in text, f"expand.py mentions {symbol}"


def test_expansion_does_not_duplicate_any_v02_validation_rule():
    text = " ".join(m.read_text(encoding="utf-8") for m in MODULES)
    for symbol in (
        "validate_plan", "validate_plan_json", "check_capabilities", "check_resources", "check_complexity",
        "check_dependencies", "check_cycles", "check_policy", "ValidationStage", "PlanValidationReport",
    ):
        assert symbol not in text, f"expansion mentions {symbol}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_vendor_or_model_names(module):
    text = module.read_text(encoding="utf-8").lower()
    assert set(re.findall(r"[a-z0-9]+", text)) & set(VENDOR_NAMES) == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_direct_calls_to_io_or_dynamic_code_builtins(module):
    tree = ast.parse(module.read_text(encoding="utf-8"))
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert called & {"open", "print", "input", "exec", "eval", "compile", "__import__", "globals", "hash", "id"} == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_level_mutable_state_beyond_all(module):
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in tree.body:
        value = getattr(node, "value", None)
        if isinstance(value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
            targets = [t.id for t in getattr(node, "targets", []) if isinstance(t, ast.Name)]
            assert targets == ["__all__"], f"{module.name}: mutable module-level state {targets}"


def test_lower_layers_do_not_depend_on_expansion():
    for target in ("contracts", "planning"):
        for path in sorted((SRC / target).glob("*.py")):
            for name, _, _ in imports_of(path):
                assert "expansion" not in name.split("."), f"{path.name} imports {name}"


def test_importing_expansion_loads_no_compiler_runtime_agent_or_protocol_layer():
    # eidos.validation is NOT in the forbidden list below: eidos.planning already, approvedly, imports
    # eidos.validation.limits (D-180), and Python must initialise the eidos.validation *package* (running its
    # __init__.py, which imports .pipeline/.stages too) before any of its submodules — a fact about Python's own
    # import mechanics, not evidence of anything being called, mirroring test_planning_guards.py's own identical
    # exclusion and its own identical reasoning one layer down.
    code = (
        "import sys\n"
        "sys.path.insert(0, 'src')\n"
        "import eidos.expansion\n"
        "loaded = sorted(m for m in sys.modules if m.startswith((\n"
        "    'eidos.compiler', 'eidos.runtime', 'eidos.state', 'eidos.agents',\n"
        "    'eidos.providers', 'eidos.backends', 'eidos.a2a', 'eidos.recording', 'eidos.capabilities',\n"
        "    'eidos.selectors', 'eidos.baseline',\n"
        ")) or m.split('.')[0] in ('langgraph', 'langchain', 'httpx'))\n"
        "print(loaded)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=EXPANSION.parents[2])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
