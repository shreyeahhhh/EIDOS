"""Static guards on ``eidos.telemetry`` (decisions.md D-159, D-196; CLAUDE.md §2 invariants 1, 2, 9; V0.9 Step 2).

Mirrors ``tests/unit/expansion/test_expansion_guards.py``'s own discipline for a sibling core layer: these read the
package source, so they fail the moment someone adds a forbidden dependency, a vendor name, a hidden source of
non-determinism, a quality/ranking vocabulary, or a filesystem/network access this deterministic projection has no
business performing.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
TELEMETRY = SRC / "telemetry"
MODULES = sorted(TELEMETRY.glob("*.py"))

# I/O, network, clock, randomness and process-state modules this deterministic core layer must never depend on
# (mirrors eidos.expansion's own list one layer down).
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

# Quality/ranking/scoring vocabulary this projection must never introduce (mirrors eidos.planning's own
# test_no_ranking_or_scoring_vocabulary_anywhere_in_planning_results guard, one layer up).
FORBIDDEN_FIELD_NAMES = {"quality", "confidence", "evidence_confidence", "score", "rank", "best", "preferred", "winner"}


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
    assert [m.name for m in MODULES] == ["__init__.py", "project.py"]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_imports_io_network_clock_randomness_or_process_state(module):
    top_level = {name.split(".")[0] for name, _, level in imports_of(module) if level == 0}
    assert top_level & FORBIDDEN_IMPORTS == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_telemetry_depends_only_on_eidos_contracts_runtime_and_state(module):
    for name, _imported, level in imports_of(module):
        if level:  # relative: inside eidos.telemetry
            continue
        if name.split(".")[0] != "eidos":
            continue
        assert name.startswith(("eidos.contracts", "eidos.runtime", "eidos.state")), f"{module.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_telemetry_never_imports_agents_providers_backends_or_any_adapter_package(module):
    forbidden_roots = {
        "agents", "providers", "backends", "a2a", "recording", "capabilities", "selectors",
        "planning", "expansion", "baseline", "compiler", "validation",
    }
    for name, _, _ in imports_of(module):
        parts = name.split(".")
        assert not (parts and parts[0] == "eidos" and len(parts) > 1 and parts[1] in forbidden_roots), \
            f"{module.name} imports {name}"


def test_telemetry_never_imports_the_reducer_so_it_cannot_write_state():
    # Mirrors eidos.recording's own test_the_recorder_never_imports_the_reducer_so_it_cannot_write_state exactly:
    # a projection reads a log; only the reducer writes MissionState (invariants 1, 2).
    for module in MODULES:
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "eidos.state.reducer", f"{module.name} imports the reducer module"
                if node.module in {"eidos.state", "eidos.state.reducer"}:
                    assert all(alias.name not in {"reduce", "reduce_resumed", "ReduceResult"} for alias in node.names), \
                        f"{module.name} imports the reducer"


def test_telemetry_does_not_duplicate_event_folding_logic():
    # Proven by absence, mirroring test_expansion_guards.py's own test_expansion_does_not_call_or_reimplement_feasibility:
    # project() composes execution_record() rather than re-walking payloads to fold counters/status itself.
    text = (TELEMETRY / "project.py").read_text(encoding="utf-8")
    assert "execution_record(" in text  # it must actually call the existing projection, not merely avoid re-deriving it
    for symbol in ("reduce(", "reduce_resumed(", "replay(", "EventLog("):
        assert symbol not in text, f"project.py mentions {symbol}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_vendor_or_model_names(module):
    text = module.read_text(encoding="utf-8").lower()
    assert set(re.findall(r"[a-z0-9]+", text)) & set(VENDOR_NAMES) == set()


def test_telemetry_record_declares_no_quality_ranking_or_scoring_field():
    from eidos.telemetry import TelemetryRecord

    assert FORBIDDEN_FIELD_NAMES & set(TelemetryRecord.model_fields) == set()


def test_telemetry_record_declares_no_strategy_id_or_model_identifier_field():
    # D-196's own deferrals: neither is added yet (Step 1 flagged both as future, separate extension points).
    from eidos.telemetry import TelemetryRecord

    assert {"strategy_id", "model", "model_id"} & set(TelemetryRecord.model_fields) == set()


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


def test_lower_layers_do_not_depend_on_telemetry():
    for target in ("contracts", "runtime", "state"):
        for path in sorted((SRC / target).rglob("*.py")):
            for name, _, _ in imports_of(path):
                assert "telemetry" not in name.split("."), f"{path.relative_to(SRC)} imports {name}"


def test_importing_telemetry_loads_no_agent_provider_backend_or_protocol_layer():
    # eidos.compiler/eidos.validation are deliberately NOT in the forbidden list below: eidos.runtime (an approved
    # dependency, needed here for NodeStatus/RunOutcome) already, legitimately, imports eidos.compiler.CompiledPlan
    # for its own ExecutionContext (pre-existing V0.3 architecture, untouched by V0.9), and eidos.compiler itself
    # already imports eidos.validation.PlanValidationReport. Checked directly (this subprocess reproduced the
    # failure with them included, confirming they load only via eidos.runtime, never via eidos.telemetry's own
    # source, which the static per-module guards above already prove never imports either directly) — the same
    # class of finding V0.8 Step 6 made for eidos.agents transitively loading eidos.compiler/.runtime/.capabilities.
    code = (
        "import sys\n"
        "sys.path.insert(0, 'src')\n"
        "import eidos.telemetry\n"
        "loaded = sorted(m for m in sys.modules if m.startswith((\n"
        "    'eidos.agents', 'eidos.providers', 'eidos.backends', 'eidos.a2a', 'eidos.recording',\n"
        "    'eidos.capabilities', 'eidos.selectors', 'eidos.planning', 'eidos.expansion', 'eidos.baseline',\n"
        ")) or m.split('.')[0] in ('langgraph', 'langchain', 'httpx'))\n"
        "print(loaded)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=TELEMETRY.parents[2])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
