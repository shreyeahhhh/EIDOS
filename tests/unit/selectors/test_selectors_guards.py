"""Static guards on ``eidos.selectors`` (decisions.md D-190 to D-193, D-198; CLAUDE.md §2 invariants 1, 2, 9, 11;
V0.8 Step 5, V1.0 Step 4).

Mirrors ``test_providers_guards.py``/``test_recording_guards.py``'s own discipline for a sibling adapter package:
these read the package source, so they fail the moment someone adds a forbidden dependency, a vendor name, a
hidden source of non-determinism, an automatic (silent, unconfigured) fallback to ``DeterministicSelector``
inside ``model_assisted.py`` specifically (D-193), or a dependency on a concept this package has no business
touching (``MissionEvent``, Strategy-to-Plan expansion, Laya) — not merely when behaviour visibly changes.

**V1.0 Step 4 deliberately revises this file, not weakens it.** Written at V0.8 Step 5, before Strategy Memory
existed, this guard correctly forbade ``eidos.selectors`` from depending on it at all, and forbade the literal
string ``"StrategyMemory"`` from appearing anywhere in the package. D-198 makes that original assumption
genuinely false on purpose: ``ExperienceInformedSelector`` is an adapter that legitimately consumes historical
execution experience, exactly as ``ModelAssistedSelector`` legitimately consumes ``eidos.agents.ModelPort`` — the
same "a dependency the core ``eidos.planning`` layer cannot have" reasoning the package's own docstring already
gives, applied to a second dependency. ``eidos.memory`` is now an approved import (below); the
``"StrategyMemory"`` literal-string prohibition is removed, not the underlying discipline — every other
forbidden concept, and the "no automatic fallback" rule for ``model_assisted.py`` specifically, stays exactly as
strict as it was.
"""

import ast
import re
import sys
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
SELECTORS = SRC / "selectors"
MODULES = sorted(SELECTORS.glob("*.py"))

# I/O, network, clock, randomness and process-state modules this adapter has no reason to import: it talks to a
# model only through the already-injected ModelPort, never to a vendor SDK or the network directly (D-193's own
# "independent, not a wrapper" framing does not license a new I/O surface).
FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "datetime", "http", "importlib", "io", "logging", "multiprocessing",
    "os", "pathlib", "pickle", "random", "requests", "secrets", "shelve", "shutil", "socket",
    "sqlite3", "ssl", "subprocess", "sys", "tempfile", "threading", "time", "urllib", "uuid",
    "httpx", "aiohttp", "numpy", "networkx", "langgraph", "langchain", "langsmith",
}
ALLOWED_ROOTS = {"json", "re", "dataclasses", "typing", "eidos"}
# V1.0 Step 4 (D-198) adds eidos.memory: ExperienceInformedSelector legitimately consumes ExperienceStore, the
# same "a dependency the core eidos.planning layer cannot have" reasoning eidos.agents was already approved for.
ALLOWED_EIDOS = {"eidos.agents", "eidos.contracts", "eidos.memory", "eidos.planning"}

# Every vendor name the sibling adapter guards already forbid, applied here too — this package speaks to a
# model only through ModelPort, never to a vendor or protocol library by name.
VENDOR_NAMES = {
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere", "litellm",
    "langgraph", "langchain", "langsmith", "qdrant", "a2a", "mcp", "rag", "laya",
}

# Concepts this package has no business depending on: MissionEvent (D-189's own deferral still applies one layer
# up), Strategy-to-Plan expansion (not built anywhere in this package) and Laya. "StrategyMemory" was forbidden
# here until V1.0 Step 4 (D-198) — ExperienceInformedSelector now legitimately depends on it; see the module
# docstring's own explanation.
FORBIDDEN_CONCEPT_NAMES = {
    "MissionEvent", "PlanDSL", "Laya",
}


def imports_of(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    return found


def test_the_package_has_the_expected_modules():
    assert [m.name for m in MODULES] == ["__init__.py", "experience_informed.py", "model_assisted.py"]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_expected_standard_library_and_no_io_network_or_model_library_is_imported(module):
    roots = {name.split(".")[0] for name in imports_of(module) if not name.startswith(".")}
    assert roots & FORBIDDEN_IMPORTS == set()
    assert roots <= ALLOWED_ROOTS, f"{module.name} imports {sorted(roots - ALLOWED_ROOTS)}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_approved_eidos_dependencies_are_imported(module):
    for name in imports_of(module):
        if name.startswith("eidos") and not name.startswith("."):
            assert ".".join(name.split(".")[:2]) in ALLOWED_EIDOS, f"{module.name} imports {name}"
            assert "providers" not in name and "backends" not in name and "recording" not in name, \
                f"{module.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_vendor_protocol_or_laya_name_appears(module):
    words = set(re.findall(r"[a-z0-9]+", module.read_text(encoding="utf-8").lower()))
    assert words & VENDOR_NAMES == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_forbidden_concept_is_mentioned(module):
    text = module.read_text(encoding="utf-8")
    for name in FORBIDDEN_CONCEPT_NAMES:
        assert name not in text, f"{module.name} mentions {name}"


def test_model_assisted_never_imports_or_calls_deterministic_selector_as_a_silent_fallback():
    # D-193: model_assisted.py never automatically substitutes DeterministicSelector when the model fails.
    # Scoped to model_assisted.py specifically (V1.0 Step 4, D-198) — not weakened: ExperienceInformedSelector's
    # own injected `fallback` is a genuinely different mechanism (explicit, caller-configured, always tested),
    # the one the architecture actually calls for at cold start; D-193's own concern was an automatic, silent
    # substitution inside a single selector's own logic, which model_assisted.py still never does.
    text = (SELECTORS / "model_assisted.py").read_text(encoding="utf-8")
    assert "DeterministicSelector" not in text


def test_no_selector_class_is_defined_in_init_py():
    init_text = (SELECTORS / "__init__.py").read_text(encoding="utf-8")
    assert "class " not in init_text


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_a_selectors_module_opens_no_file_prints_nothing_and_executes_no_generated_code(module):
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "print", "eval", "exec", "compile", "input", "__import__"}, \
                f"{module.name}: {node.func.id}()"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_level_mutable_list_or_set_state(module):
    # A module-level dict lookup table (_FAILURE_KIND_OF) is expected and allowed here, mirroring
    # eidos.validation.results's own CODE_STAGE/_FIXED_LIMIT precedent — only list/set literals are forbidden.
    for node in ast.parse(module.read_text(encoding="utf-8")).body:
        value = getattr(node, "value", None)
        if isinstance(value, (ast.List, ast.Set, ast.ListComp, ast.SetComp)):
            targets = [t.id for t in getattr(node, "targets", []) if isinstance(t, ast.Name)]
            assert targets == ["__all__"], f"{module.name}: mutable list/set module state {targets}"


def test_no_raw_prompt_or_response_is_persisted_anywhere_in_this_package():
    # No telemetry, no recording adapter, no file/db write of any kind (checked above); this is the
    # narrower, explicit check that nothing here even names a persistence concept.
    text = " ".join(m.read_text(encoding="utf-8") for m in MODULES)
    for word in ("telemetry", "persist", "database", "sqlite", "logfile"):
        assert word not in text.lower(), word


def test_no_selector_failure_kind_beyond_the_three_approved_members_is_referenced():
    text = " ".join(m.read_text(encoding="utf-8") for m in MODULES)
    assert "SelectorFailureKind." in text
    for forbidden in ("SelectorFailureKind.EMPTY", "SelectorFailureKind.INVALID", "SelectorFailureKind.NETWORK"):
        assert forbidden not in text


def test_experience_informed_selector_never_imports_a_model_dependency():
    # V1.0 Step 4 (D-198): the experience-informed path is deterministic over stored, already-recorded facts —
    # it must introduce no LLM/model dependency, unlike its sibling model_assisted.py. eidos.agents is an
    # approved package-level dependency (ModelAssistedSelector needs it) but experience_informed.py itself has
    # no reason to import anything from it.
    for name in imports_of(SELECTORS / "experience_informed.py"):
        assert not name.startswith("eidos.agents"), f"experience_informed.py imports {name}"


def test_nothing_in_eidos_planning_imports_eidos_selectors():
    planning = SRC / "planning"
    for path in sorted(planning.glob("*.py")):
        for name in imports_of(path):
            assert "selectors" not in name.split("."), f"{path.name} imports {name}"


@pytest.mark.parametrize("target", ["contracts", "validation", "compiler", "runtime", "state", "capabilities", "memory"])
def test_no_core_layer_imports_eidos_selectors(target):
    layer = SRC / target
    paths = [layer] if layer.is_file() else sorted(layer.rglob("*.py"))
    for path in paths:
        if not path.is_file():
            continue
        for name in imports_of(path):
            assert "selectors" not in name.split("."), f"{path.relative_to(SRC)} imports {name}"


def test_importing_the_planning_package_still_loads_no_selectors_agents_or_model_library():
    # eidos.planning must stay exactly as isolated as it was before this package existed — this package's own
    # existence must never leak into a plain `import eidos.planning`.
    code = (
        "import sys\n"
        "sys.path.insert(0, 'src')\n"
        "import eidos.planning\n"
        "loaded = sorted(m for m in sys.modules if m.startswith((\n"
        "    'eidos.agents', 'eidos.providers', 'eidos.backends', 'eidos.a2a', 'eidos.recording', 'eidos.selectors',\n"
        "    'eidos.capabilities', 'eidos.runtime', 'eidos.compiler',\n"
        ")) or m.split('.')[0] in ('langgraph', 'langchain', 'httpx'))\n"
        "print(loaded)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=SRC.parents[1])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
