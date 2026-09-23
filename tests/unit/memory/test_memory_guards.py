"""Static guards on ``eidos.memory`` (decisions.md D-198; CLAUDE.md §2 invariants 1, 2, 9, 11; V1.0 Step 1).

Mirrors ``tests/unit/planning/test_planning_guards.py``'s own discipline for a sibling core layer: these read the
package source, so they fail the moment someone adds a forbidden dependency, a vendor name, a hidden source of
non-determinism, or one of the concepts the V1.0 decision revision explicitly excluded (a quality/confidence
score, a strategy signature/genome encoding, embeddings) — not merely when behaviour visibly changes.

Scoped to what V1.0 Step 1 actually built (``__init__.py``, ``experience.py``). ``relevance.py`` (Step 2) and
``store.py`` (Step 3, the one file in this package ever permitted file I/O) will extend
``test_the_package_has_the_expected_modules`` and the forbidden-imports check when they land — not weakened
early, extended on schedule, exactly like ``eidos.planning``'s own guards grew across V0.7 Steps 2 to 5.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
MEMORY = SRC / "memory"
MODULES = sorted(MEMORY.glob("*.py"))

# I/O, network, clock, randomness, process state, and graph/model libraries this core layer must never depend on
# (mirrors eidos.planning's own list, D-198's own "pure logic free of I/O, clock, randomness, network").
FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "datetime", "http", "importlib", "io", "logging", "multiprocessing",
    "os", "pathlib", "pickle", "random", "requests", "secrets", "shelve", "shutil", "socket",
    "sqlite3", "ssl", "subprocess", "sys", "tempfile", "threading", "time", "urllib", "uuid",
    "httpx", "aiohttp", "numpy", "networkx", "langgraph", "langchain",
}

VENDOR_NAMES = (
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere", "litellm",
    "langgraph", "langchain", "networkx", "qdrant", "a2a", "mcp", "rag", "laya", "dspy",
)

# The V1.0 decision revision's own explicit exclusions (item 7: "keep ExecutionExperience immutable and
# factual... do not add quality score, confidence score, strategy signature, embeddings, artifact text,
# subjective judgments"). Checked as literal text, mirroring test_selectors_guards's own
# test_no_forbidden_concept_is_mentioned discipline.
FORBIDDEN_CONCEPT_WORDS = ("quality_score", "confidence_score", "strategy_signature", "embedding", "trust_score")
FORBIDDEN_FIELD_NAMES = {"quality", "confidence", "score", "rank", "trust"}


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
    # Extended at Step 2 (relevance.py) and Step 3 (store.py) — not built yet, per D-198's own step order.
    assert [m.name for m in MODULES] == ["__init__.py", "experience.py"]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_imports_io_network_clock_randomness_or_process_state(module):
    top_level = {name.split(".")[0] for name, _, level in imports_of(module) if level == 0}
    assert top_level & FORBIDDEN_IMPORTS == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_memory_depends_only_on_the_approved_layers(module):
    # D-198: eidos.contracts, eidos.planning, eidos.runtime, eidos.state, eidos.telemetry — the same shape
    # eidos.telemetry itself already depends on, one layer further (its own __init__.py: "joining eidos.contracts,
    # eidos.runtime and eidos.state"), plus eidos.planning for Strategy/StrategyStage/VerificationPosture.
    allowed = {"eidos.contracts", "eidos.planning", "eidos.runtime", "eidos.state", "eidos.telemetry"}
    for name, _imported, level in imports_of(module):
        if level:  # relative: inside eidos.memory
            continue
        if name.split(".")[0] != "eidos":
            continue
        assert any(name == root or name.startswith(root + ".") for root in allowed), f"{module.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_memory_never_imports_agents_providers_backends_a2a_recording_selectors_or_capabilities(module):
    forbidden_roots = {"agents", "providers", "backends", "a2a", "recording", "selectors", "capabilities"}
    for name, _, _ in imports_of(module):
        parts = name.split(".")
        assert not (parts and parts[0] == "eidos" and len(parts) > 1 and parts[1] in forbidden_roots), \
            f"{module.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_vendor_or_model_names(module):
    text = module.read_text(encoding="utf-8").lower().replace("claude.md", "")
    assert set(re.findall(r"[a-z0-9]+", text)) & set(VENDOR_NAMES) == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_forbidden_v1_concept_word_appears(module):
    text = module.read_text(encoding="utf-8").lower()
    for word in FORBIDDEN_CONCEPT_WORDS:
        assert word not in text, f"{module.name} mentions {word!r}"


def test_execution_experience_declares_none_of_the_forbidden_field_names():
    from eidos.memory import ExecutionExperience

    assert FORBIDDEN_FIELD_NAMES & set(ExecutionExperience.model_fields) == set()


def test_no_ranking_or_scoring_vocabulary_in_execution_experience():
    from eidos.memory import ExecutionExperience

    forbidden = {"best", "preferred", "winner", "rank", "score", "weight", "weighted"}
    assert forbidden & set(ExecutionExperience.model_fields) == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_direct_calls_to_io_or_dynamic_code_builtins(module):
    tree = ast.parse(module.read_text(encoding="utf-8"))
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert called & {"open", "print", "input", "exec", "eval", "compile", "__import__", "globals", "hash", "id"} == set()


def test_lower_layers_do_not_depend_on_memory():
    # Dependency direction: contracts/runtime/state/telemetry/planning <- memory, never the reverse.
    for layer in ("contracts", "runtime", "state", "telemetry", "planning"):
        for path in (SRC / layer).glob("*.py"):
            for name, _, _ in imports_of(path):
                assert "memory" not in name.split("."), f"{path.name} imports {name}"


def test_importing_the_memory_package_loads_no_agent_backend_or_protocol_layer():
    # eidos.compiler and eidos.validation are expected, approved transitive loads (eidos.runtime -> eidos.compiler,
    # V0.3; eidos.planning -> eidos.validation.limits, D-180) — confirmed by direct inspection before writing this
    # guard, not assumed. What must still never load: every layer this package has no reason to touch.
    code = (
        "import sys\n"
        "sys.path.insert(0, 'src')\n"
        "import eidos.memory\n"
        "loaded = sorted(m for m in sys.modules if m.startswith((\n"
        "    'eidos.agents', 'eidos.providers', 'eidos.backends', 'eidos.a2a', 'eidos.recording', 'eidos.selectors',\n"
        "    'eidos.capabilities',\n"
        ")) or m.split('.')[0] in ('langgraph', 'langchain', 'httpx'))\n"
        "print(loaded)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=MEMORY.parents[2])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_level_mutable_state_beyond_constants(module):
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in tree.body:
        value = getattr(node, "value", None)
        if isinstance(value, (ast.List, ast.Set, ast.ListComp, ast.SetComp)):
            targets = [t.id for t in getattr(node, "targets", []) if isinstance(t, ast.Name)]
            assert targets == ["__all__"], f"{module.name}: mutable list/set module state {targets}"
