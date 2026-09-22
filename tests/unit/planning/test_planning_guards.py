"""Static guards on ``eidos.planning`` (decisions.md D-178 to D-182; CLAUDE.md §2 invariants 1, 2, 9, 11; V0.7 Steps 2 to 4).

Mirrors ``tests/unit/compiler/test_compiler_guards.py``'s own discipline for a sibling core layer: these read the
package source, so they fail the moment someone adds a forbidden dependency, a vendor name, a hidden source of
non-determinism, or one of the concepts D-179 explicitly excluded from ``Strategy`` — not merely when behaviour
visibly changes. ``uuid``/``random``/``time``/``datetime`` are forbidden **everywhere** in this package, stronger
than ``eidos.compiler``'s own "confined to one file" carve-out for a clock/id port: no real, randomness-drawing
``StrategyIdSource`` implementation lives here at all (``pipeline.py``'s own docstring) — a caller supplies one,
exactly as a caller supplies a real ``IdSource`` to ``eidos.recording`` today.

**Step 4 adds one, narrow, approved dependency** (D-180): ``eidos.validation.limits`` — plain ceiling numbers
(``SystemLimits``, ``LimitName``), never ``eidos.validation.stages``/``.pipeline``/``.results`` (the actual Plan
validator). Importing ``eidos.validation.limits`` unavoidably initialises the ``eidos.validation`` *package*,
which itself imports ``.pipeline`` (Python must run a parent package's ``__init__.py`` before any submodule) — so
those modules legitimately appear in ``sys.modules`` after `import eidos.planning`; that is a fact about Python's
own import mechanics, not evidence of anything being *called*. The precise, correct guard is therefore static
(source text and imports), not a ``sys.modules`` presence check — mirroring
``test_compiler_guards.py::test_the_compiler_does_not_reimplement_the_v02_stages`` exactly.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
PLANNING = SRC / "planning"
MODULES = sorted(PLANNING.glob("*.py"))

# I/O, network, clock, randomness, process state, and graph/model libraries this core layer must never depend on
# (mirrors eidos.compiler's own list; Strategy carries no timestamp or id-drawing behaviour of its own, D-158's
# "identity is injected, not drawn inside a deterministic core" discipline applied here too).
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

# D-179's explicit exclusions: a Strategy names capabilities only, never any of these. Checked both as an
# imported symbol and (below, separately) as a literal Strategy/StrategyStage field name.
FORBIDDEN_CONCEPT_IMPORTS = {"AgentId", "StepId", "ArtifactRef", "A2ATaskId", "A2AContextId"}
FORBIDDEN_FIELD_NAMES = {
    "step_id", "depends_on", "agent_id", "model", "vendor", "tool", "tools",
    "max_retries", "max_replans", "retry_policy", "replan_policy",
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
    assert [m.name for m in MODULES] == [
        "__init__.py", "feasibility.py", "generator.py", "pipeline.py", "results.py", "strategy.py",
    ]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_imports_io_network_clock_randomness_or_process_state(module):
    top_level = {name.split(".")[0] for name, _, level in imports_of(module) if level == 0}
    assert top_level & FORBIDDEN_IMPORTS == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_planning_depends_only_on_eidos_contracts_and_validation_limits(module):
    # D-180: eidos.validation.limits (plain ceiling numbers) is the one approved addition — never bare
    # eidos.validation, never .stages/.pipeline/.results (the actual Plan validator; see below).
    for name, _imported, level in imports_of(module):
        if level:  # relative: inside eidos.planning
            continue
        if name.split(".")[0] != "eidos":
            continue
        assert name in {"eidos.contracts", "eidos.validation.limits"}, f"{module.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_planning_never_imports_the_plan_validator_compiler_or_other_higher_layers(module):
    forbidden_roots = {"agents", "providers", "backends", "a2a", "recording", "capabilities", "runtime", "compiler"}
    for name, _, _ in imports_of(module):
        parts = name.split(".")
        assert not (parts and parts[0] == "eidos" and len(parts) > 1 and parts[1] in forbidden_roots), \
            f"{module.name} imports {name}"
        # The Plan validator's own stage/pipeline/report modules specifically — D-180 permits only .limits.
        assert not name.startswith(("eidos.validation.stages", "eidos.validation.pipeline", "eidos.validation.results")), \
            f"{module.name} imports {name}"


def test_feasibility_does_not_reimplement_or_call_the_plan_validator():
    # Mirrors test_compiler_guards.py::test_the_compiler_does_not_reimplement_the_v02_stages exactly: strategy
    # feasibility is not Plan validation (module docstring), proven by absence, not merely by non-import.
    text = " ".join(m.read_text(encoding="utf-8") for m in MODULES if m.name in {"feasibility.py", "pipeline.py"})
    for symbol in (
        "validate_plan", "validate_plan_json", "check_capabilities", "check_resources", "check_complexity",
        "check_dependencies", "check_cycles", "check_policy", "ValidationStage", "PlanValidationReport",
        "StageResult", "StageStatus",
    ):
        assert symbol not in text, f"feasibility.py/pipeline.py mentions {symbol}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_forbidden_strategy_concept_is_imported(module):
    imported_names = {n for _, names, _ in imports_of(module) for n in names}
    assert imported_names & FORBIDDEN_CONCEPT_IMPORTS == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_vendor_or_model_names(module):
    text = module.read_text(encoding="utf-8").lower().replace("claude.md", "")
    assert set(re.findall(r"[a-z0-9]+", text)) & set(VENDOR_NAMES) == set()


def test_strategy_and_stage_declare_none_of_the_forbidden_field_names():
    from eidos.planning import (
        CandidateGenerationResult,
        FeasibilityReport,
        FeasibilityViolation,
        RejectedCandidate,
        Strategy,
        StrategyShape,
        StrategyStage,
    )

    for model in (
        Strategy, StrategyShape, StrategyStage, CandidateGenerationResult, RejectedCandidate,
        FeasibilityReport, FeasibilityViolation,
    ):
        assert FORBIDDEN_FIELD_NAMES & set(model.model_fields) == set(), model.__name__


def test_candidate_generation_result_never_names_a_winner_or_a_score():
    # Candidate generation is not strategy selection (V0.8, not built): no ranking vocabulary anywhere.
    from eidos.planning import CandidateGenerationResult

    forbidden = {"best", "preferred", "winner", "rank", "score", "selected"}
    assert forbidden & set(CandidateGenerationResult.model_fields) == set()


# Frozen-in-practice module-level lookup tables (dict literals, never mutated after definition), matching the
# exact precedent eidos.validation.results sets for a sibling core layer (its own CODE_STAGE/_FIXED_LIMIT). A
# List/Set literal is still forbidden everywhere: nothing here needs one, and unlike a dict lookup, an
# accidentally-mutated list would be a real hidden-state risk.
ALLOWED_MODULE_DICTS = {"_CHECK_OF", "_FIXED_LIMIT"}


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_level_mutable_state_beyond_constants(module):
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in tree.body:
        value = getattr(node, "value", None)
        if isinstance(value, (ast.List, ast.Set, ast.ListComp, ast.SetComp)):
            targets = [t.id for t in getattr(node, "targets", []) if isinstance(t, ast.Name)]
            assert targets == ["__all__"], f"{module.name}: mutable list/set module state {targets}"
        if isinstance(value, (ast.Dict, ast.DictComp)):
            targets = [t.id for t in getattr(node, "targets", []) if isinstance(t, ast.Name)]
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets = [node.target.id]
            assert targets and set(targets) <= ALLOWED_MODULE_DICTS, f"{module.name}: unexpected dict module state {targets}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_direct_calls_to_io_or_dynamic_code_builtins(module):
    tree = ast.parse(module.read_text(encoding="utf-8"))
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert called & {"open", "print", "input", "exec", "eval", "compile", "__import__", "globals", "hash", "id"} == set()


def test_lower_layers_do_not_depend_on_planning():
    # Dependency direction: contracts <- planning (D-180 will add validation <- planning too, later).
    for path in (SRC / "contracts").glob("*.py"):
        for name, _, _ in imports_of(path):
            assert "planning" not in name.split("."), f"{path.name} imports {name}"


def test_importing_the_planning_package_loads_no_backend_agent_or_protocol_layer():
    # eidos.validation is now an expected, approved transitive load (D-180: eidos.validation.limits) — Python
    # must initialise the eidos.validation package (running its __init__.py, which imports .pipeline/.stages
    # too) before any of its submodules; that is a fact about import mechanics, not a call. What must still
    # never load: every layer above or beside planning that Step 4 has no reason to touch.
    code = (
        "import sys\n"
        "sys.path.insert(0, 'src')\n"
        "import eidos.planning\n"
        "loaded = sorted(m for m in sys.modules if m.startswith((\n"
        "    'eidos.agents', 'eidos.providers', 'eidos.backends', 'eidos.a2a', 'eidos.recording',\n"
        "    'eidos.capabilities', 'eidos.runtime', 'eidos.compiler',\n"
        ")) or m.split('.')[0] in ('langgraph', 'langchain', 'httpx'))\n"
        "print(loaded)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=PLANNING.parents[2])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
