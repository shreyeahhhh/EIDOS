"""Static guards on ``eidos.backends`` (CLAUDE.md §2 invariants 1, 2, 7, 9, 15; §8; decisions.md D-113, D-115, D-116, D-122, D-123, D-127).

These read source and run subprocesses; they never import LangGraph themselves, so they run — and must pass —
in an environment where LangGraph is not installed. That is what "core installation and core tests remain
usable without importing LangGraph" (D-116) means, and the last tests here prove it directly.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

import eidos.compiler
import eidos.contracts
import eidos.runtime

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
BACKENDS = SRC / "backends"
ADAPTER = BACKENDS / "langgraph"
MODULES = sorted(BACKENDS.rglob("*.py"))
ADAPTER_MODULES = sorted(ADAPTER.glob("*.py"))
ROOT = SRC.parents[1]

# I/O, network, clock, randomness, process state and concurrency the adapter must never use itself. LangGraph
# owns its threads; the adapter starts none.
FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "datetime", "http", "importlib", "io", "logging", "multiprocessing",
    "os", "pathlib", "pickle", "random", "requests", "secrets", "shelve", "shutil", "socket",
    "sqlite3", "ssl", "subprocess", "sys", "tempfile", "threading", "time", "urllib", "uuid",
    "httpx", "aiohttp", "numpy", "networkx", "langchain",
}
ALLOWED_TOP_LEVEL = {"dataclasses", "typing", "langgraph", "langsmith", "pydantic", "eidos"}
ALLOWED_LANGGRAPH_MODULES = {"langgraph.graph", "langgraph.errors"}
# LangSmith (a dependency of LangGraph) may be imported for one purpose only: to switch tracing off.
ALLOWED_LANGSMITH_IMPORTS = {("langsmith", ("tracing_context",))}

# The adapter never touches state, events or anything that is not an execution concern (D-113, D-123).
NEVER_IN_ADAPTER = {
    "MissionState", "MissionEvent", "MissionEventType", "MissionStatus", "AgentTask", "ReliabilityContract",
    "TaskGenome",
}

# LangGraph features the design rules out: persistence, resumption, retry, routing, streaming (D-127).
FORBIDDEN_KEYWORDS = {
    "checkpointer", "retry_policy", "interrupt_before", "interrupt_after", "thread_id", "store", "cache_policy",
    "defer", "stream_mode", "callbacks", "durability",
}
FORBIDDEN_NAMES = {
    "Command", "Send", "interrupt", "MemorySaver", "InMemorySaver", "RetryPolicy", "add_conditional_edges",
    "add_sequence", "set_entry_point", "set_finish_point", "END", "astream", "stream", "ainvoke", "batch",
    "get_state", "update_state",
}

VENDOR_NAMES = (
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere", "networkx", "qdrant", "a2a", "mcp",
)


def imports_of(path: Path) -> list[tuple[str, tuple[str, ...], int]]:
    found = []
    for node in ast.walk(tree_of(path)):
        if isinstance(node, ast.Import):
            found.extend((alias.name, (), 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", tuple(a.name for a in node.names), node.level))
    return found


def tree_of(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def run_python(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)


BLOCK_LANGGRAPH = (
    "import sys\n"
    "sys.path.insert(0, 'src')\n"
    "from importlib.abc import MetaPathFinder\n"
    "class Block(MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name.split('.')[0] in ('langgraph', 'langchain', 'langchain_core', 'langsmith'):\n"
    "            raise ImportError('blocked for this test: ' + name)\n"
    "sys.meta_path.insert(0, Block())\n"
)


# --- the package and its one exclusive right -----------------------------------------------------------------------


def test_the_package_has_the_expected_modules():
    assert [m.relative_to(BACKENDS).as_posix() for m in MODULES] == [
        "__init__.py", "langgraph/__init__.py", "langgraph/errors.py", "langgraph/executor.py",
    ]


def test_only_the_langgraph_adapter_package_imports_langgraph_anywhere_in_eidos():
    # D-115: the compiler, the runtime and every other core layer must not import LangGraph.
    for path in sorted(SRC.rglob("*.py")):
        if ADAPTER in path.parents:
            continue
        for name, _, level in imports_of(path):
            top = name.split(".")[0]
            assert level or top not in {"langgraph", "langchain", "langchain_core", "langsmith"}, (
                f"{path.relative_to(SRC)} imports {name}"
            )


def test_the_backends_package_itself_imports_nothing_that_would_load_langgraph():
    assert not any(name.split(".")[0] in {"langgraph", "langchain"} for name, _, _ in imports_of(BACKENDS / "__init__.py"))


def test_no_core_layer_imports_the_backends_package():
    for package in ("contracts", "validation", "compiler", "runtime"):
        for path in (SRC / package).glob("*.py"):
            for name, _, _ in imports_of(path):
                assert "backends" not in name.split("."), f"{path.name} imports {name}"


# --- what the adapter may import ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("module", ADAPTER_MODULES, ids=lambda m: m.name)
def test_the_adapter_imports_only_the_standard_names_pydantic_langgraph_and_eidos(module):
    top_level = {name.split(".")[0] for name, _, level in imports_of(module) if level == 0}
    assert top_level <= ALLOWED_TOP_LEVEL, top_level - ALLOWED_TOP_LEVEL
    assert top_level & FORBIDDEN_IMPORTS == set()


@pytest.mark.parametrize("module", ADAPTER_MODULES, ids=lambda m: m.name)
def test_the_adapter_touches_only_the_public_surfaces_of_contracts_compiler_and_runtime(module):
    public = {
        "eidos.contracts": set(eidos.contracts.__all__),
        "eidos.compiler": set(eidos.compiler.__all__),
        "eidos.runtime": set(eidos.runtime.__all__),
    }
    for name, imported, level in imports_of(module):
        if level or name.split(".")[0] != "eidos":
            continue
        assert name in public, f"{module.name} imports {name}"
        assert set(imported) <= public[name], f"{module.name} imports non-public {set(imported) - public[name]}"


@pytest.mark.parametrize("module", ADAPTER_MODULES, ids=lambda m: m.name)
def test_the_adapter_uses_only_the_langgraph_modules_it_needs(module):
    for name, _, level in imports_of(module):
        if not level and name.split(".")[0] == "langgraph":
            assert name in ALLOWED_LANGGRAPH_MODULES, f"{module.name} imports {name}"


@pytest.mark.parametrize("module", ADAPTER_MODULES, ids=lambda m: m.name)
def test_langsmith_is_imported_only_to_switch_tracing_off(module):
    for name, imported, level in imports_of(module):
        if not level and name.split(".")[0] == "langsmith":
            assert (name, imported) in ALLOWED_LANGSMITH_IMPORTS, f"{module.name}: from {name} import {imported}"


@pytest.mark.parametrize("module", ADAPTER_MODULES, ids=lambda m: m.name)
def test_the_adapter_never_imports_state_event_or_genome_contracts(module):
    imported = {n for _, names, _ in imports_of(module) for n in names}
    assert imported & NEVER_IN_ADAPTER == set()


# --- the LangGraph features the design rules out (D-113, D-127) --------------------------------------------------------


@pytest.mark.parametrize("module", ADAPTER_MODULES, ids=lambda m: m.name)
def test_no_checkpointer_thread_id_interrupt_retry_routing_or_streaming_is_used(module):
    for node in ast.walk(tree_of(module)):
        if isinstance(node, ast.keyword):
            assert node.arg not in FORBIDDEN_KEYWORDS, f"{module.name}: keyword {node.arg}"
        if isinstance(node, ast.Name):
            assert node.id not in FORBIDDEN_NAMES, f"{module.name}: name {node.id}"
        if isinstance(node, ast.Attribute):
            assert node.attr not in FORBIDDEN_NAMES, f"{module.name}: attribute {node.attr}"
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith(("langgraph.checkpoint", "langgraph.types", "langgraph.prebuilt")), node.module


def test_the_graph_state_class_declares_outcomes_and_nothing_else():
    tree = tree_of(ADAPTER / "executor.py")
    (state,) = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "_RunState"]
    annotated = [n.target.id for n in state.body if isinstance(n, ast.AnnAssign)]
    assert annotated == ["outcomes"]
    assert len(state.body) == 1  # no other attribute, method or default


def test_compile_is_called_once_and_never_with_arguments():
    # `compile()` with no arguments cannot attach a checkpointer, a store, a cache or an interrupt.
    calls = [
        n for n in ast.walk(tree_of(ADAPTER / "executor.py"))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "compile"
    ]
    assert len(calls) == 1 and calls[0].args == [] and calls[0].keywords == []


def test_invoke_is_called_once_with_only_a_recursion_limit_in_its_config():
    calls = [
        n for n in ast.walk(tree_of(ADAPTER / "executor.py"))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "invoke"
    ]
    assert len(calls) == 1 and len(calls[0].args) == 2 and calls[0].keywords == []
    config = calls[0].args[1]
    assert isinstance(config, ast.Dict) and [k.value for k in config.keys] == ["recursion_limit"]


def test_the_one_invoke_runs_inside_tracing_context_enabled_false():
    # An ambient LANGSMITH_TRACING would otherwise export every node's inputs and outputs to a third party.
    tree = tree_of(ADAPTER / "executor.py")
    guarded = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "tracing_context"
                    and [(k.arg, getattr(k.value, "value", "?")) for k in call.keywords] == [("enabled", False)]
                ):
                    guarded.extend(
                        n for n in ast.walk(node)
                        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "invoke"
                    )
    assert len(guarded) == 1


# --- determinism and boundedness, as for every other core layer ----------------------------------------------------------


@pytest.mark.parametrize("module", ADAPTER_MODULES, ids=lambda m: m.name)
def test_no_module_level_mutable_state_beyond_constants(module):
    for node in tree_of(module).body:
        value = getattr(node, "value", None)
        if isinstance(value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
            targets = [t.id for t in getattr(node, "targets", []) if isinstance(t, ast.Name)]
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets = [node.target.id]
            assert targets == ["__all__"], f"{module.name}: mutable module state {targets}"


@pytest.mark.parametrize("module", ADAPTER_MODULES, ids=lambda m: m.name)
def test_no_io_dynamic_code_recursion_unbounded_loop_or_async(module):
    tree = tree_of(module)
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert called & {"open", "print", "input", "exec", "eval", "compile", "__import__", "globals", "hash", "id"} == set()
    assert not any(isinstance(n, ast.While) for n in ast.walk(tree)), f"{module.name}: while loop"
    assert not any(isinstance(n, (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith)) for n in ast.walk(tree))
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        calls = {n.func.id for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert fn.name not in calls, f"{module.name}: {fn.name} calls itself"


@pytest.mark.parametrize("module", ADAPTER_MODULES, ids=lambda m: m.name)
def test_no_set_is_built_and_no_bare_or_base_exception_is_caught(module):
    for node in ast.walk(tree_of(module)):
        assert not isinstance(node, (ast.Set, ast.SetComp)), f"{module.name}: set literal"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "set", f"{module.name}: set() call"
        if isinstance(node, ast.ExceptHandler):
            assert node.type is not None, f"{module.name}: bare except"
            assert not (isinstance(node.type, ast.Name) and node.type.id == "BaseException")


@pytest.mark.parametrize("module", ADAPTER_MODULES, ids=lambda m: m.name)
def test_no_mutation_of_shared_objects(module):
    for node in ast.walk(tree_of(module)):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
            pytest.fail(f"{module.name}: attribute assignment .{node.attr}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"model_copy", "model_construct", "__setattr__"}, module.name


def test_no_default_guard_exists_in_the_adapter():
    for node in ast.walk(tree_of(ADAPTER / "executor.py")):
        if isinstance(node, ast.FunctionDef):
            for default in node.args.defaults + [d for d in node.args.kw_defaults if d is not None]:
                assert not (isinstance(default, ast.Call) and "Guard" in ast.dump(default.func))


@pytest.mark.parametrize("module", ADAPTER_MODULES, ids=lambda m: m.name)
def test_no_vendor_or_model_names_beyond_langgraph_itself(module):
    # "CLAUDE.md" is this repository's rules file; it names a document, not a model dependency.
    text = module.read_text(encoding="utf-8").lower().replace("claude.md", "")
    assert set(re.findall(r"[a-z0-9]+", text)) & set(VENDOR_NAMES) == set()


def test_the_adapter_does_no_runtime_accounting_and_no_scheduling_of_its_own():
    text = (ADAPTER / "executor.py").read_text(encoding="utf-8")
    for word in ("max_retries", "max_replans", "max_agent_calls", "max_tool_calls", "max_execution_time",
                 "max_tokens", "retries_used", "agent_calls_used", "tokens_used", "SystemLimits"):
        assert word not in text, f"the adapter mentions {word}"
    for symbol in ("topological", "find_cycles", "longest_chain", "max_antichain"):
        assert symbol not in text


# --- LangGraph is an optional extra: core works without it (D-116) -----------------------------------------------------------


def test_the_core_imports_and_runs_with_langgraph_blocked():
    code = BLOCK_LANGGRAPH + (
        "import eidos.contracts, eidos.validation, eidos.compiler, eidos.runtime, eidos.backends\n"
        "loaded = sorted(m for m in sys.modules if m.split('.')[0] in ('langgraph', 'langchain', 'langchain_core'))\n"
        "print(loaded)\n"
    )
    result = run_python(code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"  # not even the backends package loads LangGraph


def test_importing_the_adapter_without_langgraph_says_how_to_install_it():
    result = run_python(BLOCK_LANGGRAPH + "import eidos.backends.langgraph\n")
    assert result.returncode != 0
    assert "ImportError" in result.stderr
    assert "pip install 'eidos[langgraph]'" in result.stderr


def test_the_reference_executor_runs_a_plan_with_langgraph_blocked():
    code = BLOCK_LANGGRAPH + (
        "sys.path.insert(0, 'tests/support')\n"
        "from eidos.runtime import SequentialExecutor\n"
        "from eidos_runtime_factories import *\n"
        "compiled = compiled_of({'a': '', 'b': 'a'})\n"
        "result = SequentialExecutor(work_executor=ScriptedWork(), verifier=ScriptedVerifier(), "
        "admission_guard=admit_all()).run(compiled, context_for(compiled))\n"
        "print(result.outcome.value)\n"
    )
    result = run_python(code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "finished"


def test_a_unit_test_session_loads_neither_langgraph_nor_langsmith():
    # LangGraph's dependency langsmith registers a pytest plugin. pyproject disables it, so a session that
    # only runs core tests loads no part of the LangGraph family, even where the extra is installed.
    code = (
        "import sys, pytest\n"
        "code = pytest.main(['-q', '-p', 'no:cacheprovider', 'tests/unit/contracts/test_enums.py'])\n"
        "family = ('langgraph', 'langchain', 'langchain_core', 'langsmith')\n"
        "print(int(code), sorted({m.split('.')[0] for m in sys.modules if m.split('.')[0] in family}))\n"
    )
    result = run_python(code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "0 []"


def test_pyproject_disables_the_langsmith_pytest_plugin():
    import tomllib

    options = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
    assert "-p no:langsmith_plugin" in options["addopts"]
