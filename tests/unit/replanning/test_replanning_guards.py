"""Static guards on ``eidos.replanning`` (decisions.md D-199; CLAUDE.md §8; V1.1 Step 4).

An orchestration layer, not a deterministic core one — mirrors ``eidos.recording``'s own stance exactly, one
layer up: it accepts an injected ``Clock``/``IdSource``/``AdmissionGuard`` factory and may use them, but it never
reads the wall clock or draws a random identifier itself. It composes every already-approved V1.0/V1.1 piece —
``eidos.planning``, ``eidos.expansion``, ``eidos.memory``, ``eidos.recording``, ``eidos.telemetry`` — but never
``eidos.selectors``, ``eidos.backends``, ``eidos.a2a``, ``eidos.providers``, or any vendor/workflow library.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
REPLANNING = SRC / "replanning.py"

FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "http", "importlib", "io", "logging", "multiprocessing", "os", "pathlib", "pickle",
    "random", "requests", "secrets", "shelve", "shutil", "socket", "sqlite3", "ssl", "subprocess", "sys",
    "tempfile", "threading", "time", "urllib", "uuid", "httpx", "aiohttp", "numpy", "networkx", "langgraph",
    "langchain", "langsmith", "ollama", "openai", "anthropic",
}
ALLOWED_ROOTS = {"collections", "dataclasses", "enum", "typing", "pydantic", "eidos"}
ALLOWED_EIDOS = {
    "eidos.agents", "eidos.baseline", "eidos.capabilities", "eidos.contracts", "eidos.expansion", "eidos.memory",
    "eidos.planning", "eidos.recording", "eidos.runtime", "eidos.state", "eidos.telemetry", "eidos.validation",
}
VENDOR_NAMES = {
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere", "ollama", "qdrant", "a2a",
    "mcp", "rag", "laya", "dspy", "langgraph", "langchain", "langsmith",
}
CORE_PACKAGES = (
    "contracts", "validation", "compiler", "runtime", "state", "planning", "expansion", "memory", "telemetry",
    "capabilities", "agents", "backends", "recording", "baseline",
)


def imports() -> list[str]:
    found = []
    for node in ast.walk(ast.parse(REPLANNING.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    return found


def test_no_io_network_clock_randomness_or_vendor_library_is_imported():
    roots = {name.split(".")[0] for name in imports() if not name.startswith(".")}
    assert roots & FORBIDDEN_IMPORTS == set()
    assert roots <= ALLOWED_ROOTS, sorted(roots - ALLOWED_ROOTS)


def test_only_the_layers_the_orchestrator_composes_are_imported_never_a_selector_backend_a2a_or_provider():
    for name in imports():
        if name.startswith("eidos"):
            assert ".".join(name.split(".")[:2]) in ALLOWED_EIDOS, name
            for forbidden in ("selectors", "backends", "providers", "a2a", "mcp", "rag"):
                assert forbidden not in name, name


def test_no_vendor_or_domain_word_appears_in_the_orchestrator():
    words = set(re.findall(r"[a-z0-9]+", REPLANNING.read_text(encoding="utf-8").lower()))
    assert words & VENDOR_NAMES == set()


def test_the_orchestrator_never_reads_the_wall_clock_or_draws_a_random_identifier_directly():
    # `clock.now()` (the injected Clock port) is expected and legitimate — this checks the module never reaches
    # for the real, un-injected `datetime`/`time`/`uuid` modules instead, which the import guard above already
    # confirms are not even importable here; this is a second, independent check on the text itself.
    text = REPLANNING.read_text(encoding="utf-8")
    assert "datetime.now" not in text and "time.monotonic" not in text and "uuid.uuid4" not in text


def test_the_orchestrator_has_no_command_line_no_api_and_executes_no_generated_code():
    tree = ast.parse(REPLANNING.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "print", "eval", "exec", "compile", "input", "__import__"}, node.func.id
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            assert "__main__" not in ast.dump(node.test)


def test_run_with_replanning_raises_nothing_for_a_domain_outcome():
    # D-201 item 2: a mission that cannot start is a typed ReplanRejection, never an exception — the same "typed
    # result, not a raise" convention as ReplayRejection, ExperienceLoadRejection and RunRejection. (The rejection
    # model's own construction-time validator may raise, as every pydantic contract does; that is not a domain outcome.)
    tree = ast.parse(REPLANNING.read_text(encoding="utf-8"))
    (function,) = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run_with_replanning"]
    assert [n for n in ast.walk(function) if isinstance(n, ast.Raise)] == []


def test_no_module_level_mutable_state():
    for node in ast.parse(REPLANNING.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                continue
            assert not isinstance(node.value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp))


def test_no_core_or_adapter_layer_imports_the_orchestrator():
    for package in CORE_PACKAGES:
        root = SRC / package
        paths = [root] if root.is_file() else (sorted(root.rglob("*.py")) if root.is_dir() else [])
        for path in paths:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.ImportFrom):
                    assert node.module != "eidos.replanning", f"{path.relative_to(SRC)} imports the orchestrator"
                if isinstance(node, ast.Import):
                    assert all(alias.name != "eidos.replanning" for alias in node.names), path.name


def test_never_calls_deterministic_selector_or_model_assisted_selector_by_name():
    # D-199 ruling 2: the SAME already-configured Selector is reused for every attempt, never a hardcoded one.
    text = REPLANNING.read_text(encoding="utf-8")
    for forbidden in ("DeterministicSelector", "ModelAssistedSelector", "ExperienceInformedSelector"):
        assert forbidden not in text, f"replanning.py names {forbidden} — the caller's own selector must be used unmodified"


def test_never_invents_a_new_mission_failure_cause_or_selector_protocol():
    text = REPLANNING.read_text(encoding="utf-8")
    for forbidden in ("REPLAN_EXHAUSTED", "class Selector", "SelectorProtocol"):
        assert forbidden not in text, f"replanning.py mentions {forbidden!r}"


def test_importing_the_orchestrator_loads_no_selector_backend_a2a_provider_or_workflow_library():
    code = (
        "import sys; sys.path.insert(0, 'src'); import eidos.replanning\n"
        "print(sorted(m for m in sys.modules if m.startswith(('eidos.selectors', 'eidos.backends', 'eidos.providers', 'eidos.a2a')) "
        "or m.split('.')[0] in ('langgraph', 'langchain', 'langsmith', 'requests', 'httpx')))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=SRC.parents[1])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
