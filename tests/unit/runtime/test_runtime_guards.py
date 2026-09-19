"""Static guards on ``eidos.runtime`` (CLAUDE.md §2 invariants 1, 2, 7, 9, 15; §8; decisions.md D-113, D-115, D-122, D-123).

These read the package source, so they fail the moment someone adds a forbidden
dependency, a LangGraph or backend import, a MissionEvent, a MissionState write, a
clock, an unbounded loop or a hidden source of non-determinism — not merely when
behaviour visibly changes.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

import eidos.compiler

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
RUNTIME = SRC / "runtime"
MODULES = sorted(RUNTIME.glob("*.py"))

# I/O, network, clock, randomness, process state, concurrency — and every graph, workflow
# and LLM library the runtime must never depend on (D-115).
FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "datetime", "http", "importlib", "io", "logging", "multiprocessing",
    "os", "pathlib", "pickle", "random", "requests", "secrets", "shelve", "shutil", "socket",
    "sqlite3", "ssl", "subprocess", "sys", "tempfile", "threading", "time", "urllib", "uuid",
    "httpx", "aiohttp", "numpy", "networkx", "langgraph", "langchain",
}

VENDOR_NAMES = (
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere",
    "langgraph", "langchain", "networkx", "qdrant", "a2a", "mcp",
)

# Contract names the runtime must never import: events, and everything of the authoritative
# state except the one read-only snapshot builder (D-113, D-123).
NEVER_IN_RUNTIME = {"MissionEvent", "MissionEventType", "AgentTask", "ReliabilityContract", "MissionStatus"}


def imports_of(path: Path) -> list[tuple[str, tuple[str, ...], int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, (), 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", tuple(a.name for a in node.names), node.level))
    return found


def tree_of(module: Path) -> ast.AST:
    return ast.parse(module.read_text(encoding="utf-8"))


def test_the_package_has_the_expected_modules():
    assert [m.name for m in MODULES] == [
        "__init__.py", "context.py", "executor.py", "ports.py", "preconditions.py", "results.py",
    ]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_imports_io_network_clock_randomness_or_process_state(module):
    top_level = {name.split(".")[0] for name, _, level in imports_of(module) if level == 0}
    assert top_level & FORBIDDEN_IMPORTS == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_the_runtime_depends_only_on_contracts_the_compilers_public_surface_and_itself(module):
    for name, imported, level in imports_of(module):
        if level or name.split(".")[0] != "eidos":
            continue
        assert name in {"eidos.contracts", "eidos.compiler"}, f"{module.name} imports {name}"
        if name == "eidos.compiler":
            public = set(eidos.compiler.__all__)
            assert set(imported) <= public, f"{module.name} imports non-public {set(imported) - public}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_the_runtime_never_imports_langgraph_or_any_backend(module):
    for name, _, _ in imports_of(module):
        parts = name.split(".")
        assert "backends" not in parts and "langgraph" not in parts and "langchain" not in parts, (
            f"{module.name} imports {name}"
        )


def test_importing_the_runtime_loads_no_langgraph_and_no_backend():
    code = (
        "import sys\n"
        "sys.path.insert(0, 'src')\n"
        "import eidos.runtime\n"
        "loaded = sorted(m for m in sys.modules if m.split('.')[0] in ('langgraph', 'langchain') "
        "or m.startswith('eidos.backends'))\n"
        "print(loaded)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=RUNTIME.parents[2])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_event_or_state_contract_is_imported_beyond_the_one_read_only_snapshot_builder(module):
    imported = {n for _, names, _ in imports_of(module) for n in names}
    assert imported & NEVER_IN_RUNTIME == set()
    if module.name != "context.py":
        assert "MissionState" not in imported, f"{module.name} imports MissionState"


def test_mission_state_is_only_read_never_written_or_copied():
    # context.py takes a MissionState to read narrow fields from. Nothing in the runtime may
    # copy, construct or reassign one.
    for module in MODULES:
        for node in ast.walk(tree_of(module)):
            if isinstance(node, ast.Call):
                func = node.func
                assert not (isinstance(func, ast.Name) and func.id == "MissionState"), module.name
                if isinstance(func, ast.Attribute):
                    assert func.attr not in {"model_copy", "model_construct", "__setattr__"}, (
                        f"{module.name}: {func.attr}"
                    )
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
                pytest.fail(f"{module.name}: attribute assignment .{node.attr}")


def test_lower_layers_do_not_depend_on_the_runtime():
    # Dependency direction: contracts <- validation <- compiler <- runtime.
    for package in ("contracts", "validation", "compiler"):
        for path in (SRC / package).glob("*.py"):
            for name, _, _ in imports_of(path):
                assert "runtime" not in name.split("."), f"{path.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_vendor_or_model_names(module):
    # "CLAUDE.md" is this repository's rules file, cited across the source; it names a
    # document, not a model dependency.
    text = module.read_text(encoding="utf-8").lower().replace("claude.md", "")
    assert set(re.findall(r"[a-z0-9]+", text)) & set(VENDOR_NAMES) == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_level_mutable_state_beyond_constants(module):
    for node in tree_of(module).body:
        value = getattr(node, "value", None)
        if isinstance(value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
            targets = [t.id for t in getattr(node, "targets", []) if isinstance(t, ast.Name)]
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets = [node.target.id]
            assert targets == ["__all__"], f"{module.name}: mutable module state {targets}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_direct_calls_to_io_or_dynamic_code_builtins(module):
    called = {
        n.func.id for n in ast.walk(tree_of(module)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert called & {"open", "print", "input", "exec", "eval", "compile", "__import__", "globals", "hash", "id"} == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_hash_ordered_collection_can_leak_into_output(module):
    # Output order derives from the compiled plan order. Sets are never built; dicts are
    # lookup-only and never walked with .items()/.keys()/.values().
    for node in ast.walk(tree_of(module)):
        assert not isinstance(node, (ast.Set, ast.SetComp)), f"{module.name}: set literal"
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "set":
                pytest.fail(f"{module.name}: set() call")
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"items", "keys", "values"}:
                pytest.fail(f"{module.name}: dict view .{node.func.attr}()")


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_recursion_and_no_unbounded_loop(module):
    # Invariant 7: execution is bounded. There is no `while` anywhere, so no loop can run
    # unbounded, and no function calls itself.
    tree = tree_of(module)
    assert not any(isinstance(node, ast.While) for node in ast.walk(tree)), f"{module.name}: while loop"
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        calls = {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert fn.name not in calls, f"{module.name}: {fn.name} calls itself"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_the_runtime_is_synchronous_and_catches_only_ordinary_exceptions(module):
    # D-122: synchronous ports. And a fault in a port is contained; a KeyboardInterrupt or
    # SystemExit is never swallowed.
    tree = tree_of(module)
    for node in ast.walk(tree):
        assert not isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith)), module.name
        if isinstance(node, ast.ExceptHandler):
            assert node.type is not None, f"{module.name}: bare except"
            assert not (isinstance(node.type, ast.Name) and node.type.id == "BaseException"), module.name


def test_no_default_guard_exists_in_the_runtime():
    # D-122: the AdmissionGuard is explicit and required. No module builds one, and no
    # parameter defaults to one.
    for module in MODULES:
        for node in ast.walk(tree_of(module)):
            if isinstance(node, ast.FunctionDef):
                defaults = node.args.defaults + [d for d in node.args.kw_defaults if d is not None]
                for default in defaults:
                    assert not (isinstance(default, ast.Call) and "Guard" in ast.dump(default.func)), module.name
            if isinstance(node, ast.ClassDef) and node.name.endswith("Guard"):
                assert any(
                    isinstance(base, ast.Name) and base.id == "Protocol" for base in node.bases
                ), f"{module.name}: {node.name} is a concrete guard"


def test_no_runtime_budget_time_or_token_accounting_exists():
    # D-127: runtime accounting is deferred. Nothing in the runtime counts retries, calls,
    # time or tokens against a limit.
    text = " ".join(m.read_text(encoding="utf-8") for m in MODULES if m.name in {"executor.py", "ports.py"})
    for word in ("max_retries", "max_replans", "max_agent_calls", "max_tool_calls", "max_execution_time",
                 "max_tokens", "retries_used", "agent_calls_used", "tokens_used", "SystemLimits"):
        assert word not in text, f"the runtime mentions {word}"


def test_the_executor_does_not_recompute_a_scheduling_model():
    # D-117: levels come from the compiled plan. The runtime imports no graph algorithm and
    # never assigns a level of its own.
    executor = RUNTIME / "executor.py"
    text = executor.read_text(encoding="utf-8")
    for symbol in ("topological", "find_cycles", "longest_chain", "max_antichain"):
        assert symbol not in text, f"executor.py mentions {symbol}"
    for node in ast.walk(tree_of(executor)):  # no assignment to a name called `level`
        targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            assert not any(isinstance(t, ast.Name) and t.id == "level" for t in targets), "assigns a level"
