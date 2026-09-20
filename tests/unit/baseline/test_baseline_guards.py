"""Static guards on the single-pass runner (decisions.md D-131, D-140; CLAUDE.md §8; invariants 9 and 10).

The runner is backend-neutral and provider-free, does no I/O, names no vendor or domain, has no CLI or API, and no core layer imports it.
"""

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
BASELINE = SRC / "baseline.py"

FORBIDDEN_IMPORTS = {
    "argparse", "asyncio", "click", "concurrent", "datetime", "fastapi", "flask", "http", "importlib", "io", "logging",
    "multiprocessing", "os", "pathlib", "pickle", "random", "requests", "secrets", "shutil", "socket", "sqlite3", "ssl",
    "subprocess", "sys", "tempfile", "threading", "time", "urllib", "uuid", "httpx", "langgraph", "langchain", "langsmith",
    "ollama", "openai", "anthropic",
}
ALLOWED_ROOTS = {"collections", "dataclasses", "enum", "typing", "pydantic", "eidos"}
ALLOWED_EIDOS = {
    "eidos.agents", "eidos.capabilities", "eidos.compiler", "eidos.contracts", "eidos.runtime", "eidos.validation",
}
VENDOR_NAMES = {
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere", "ollama", "qdrant", "a2a", "mcp",
    "langgraph", "langchain", "langsmith",
}
# Invariant 10: no domain workflow is hardcoded. Words from the handoff's example domains must not appear.
DOMAIN_WORDS = {"migration", "infrastructure", "website", "bridge", "software", "repository", "deployment"}
CORE_PACKAGES = ("contracts", "validation", "compiler", "runtime", "backends", "agents", "capabilities")


def imports() -> list[str]:
    found = []
    for node in ast.walk(ast.parse(BASELINE.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    return found


def test_no_io_network_clock_randomness_backend_or_provider_is_imported():
    roots = {name.split(".")[0] for name in imports() if not name.startswith(".")}
    assert roots & FORBIDDEN_IMPORTS == set()
    assert roots <= ALLOWED_ROOTS, sorted(roots - ALLOWED_ROOTS)


def test_only_the_layers_the_runner_composes_are_imported_and_never_a_backend_or_provider():
    for name in imports():
        if name.startswith("eidos"):
            assert ".".join(name.split(".")[:2]) in ALLOWED_EIDOS, name
            assert "backends" not in name and "providers" not in name, name


def test_no_vendor_or_domain_word_appears_in_the_runner():
    words = set(re.findall(r"[a-z0-9]+", BASELINE.read_text(encoding="utf-8").lower()))
    assert words & VENDOR_NAMES == set()
    assert words & DOMAIN_WORDS == set()


def test_the_runner_has_no_command_line_no_api_and_executes_no_generated_code():
    tree = ast.parse(BASELINE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "print", "eval", "exec", "compile", "input", "__import__"}, node.func.id
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            assert "__main__" not in ast.dump(node.test), "the runner has no command line"


def test_no_module_level_mutable_state():
    for node in ast.parse(BASELINE.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            assert not isinstance(node.value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp))


@pytest.mark.parametrize("package", CORE_PACKAGES)
def test_no_lower_layer_imports_the_runner(package):
    for path in sorted((SRC / package).rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in {"eidos.baseline"}, f"{path.relative_to(SRC)} imports the runner"
            if isinstance(node, ast.Import):
                assert all(alias.name != "eidos.baseline" for alias in node.names), path.name


def test_importing_the_runner_loads_no_backend_provider_or_workflow_library():
    import subprocess
    import sys

    code = (
        "import sys; sys.path.insert(0, 'src'); import eidos.baseline\n"
        "print(sorted(m for m in sys.modules if m.startswith(('eidos.backends', 'eidos.providers')) "
        "or m.split('.')[0] in ('langgraph', 'langchain', 'langsmith', 'requests', 'httpx')))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=SRC.parents[1])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
