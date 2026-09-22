"""Static guards on ``eidos.providers`` and on the dependency and test-gating rules (decisions.md D-135, D-136).

This is the one package where a vendor name may appear. It uses the standard library only, implements the model port and nothing
else, and nothing outside it imports it.
"""

import ast
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "eidos"
PROVIDERS = SRC / "providers"
MODULES = sorted(PROVIDERS.glob("*.py"))

# A vendor SDK or third-party HTTP client would be a new dependency (D-136); files, processes and randomness are not this package's business.
FORBIDDEN_IMPORTS = {
    "requests", "httpx", "httpx2", "aiohttp", "urllib3", "ollama", "openai", "anthropic", "langchain", "langgraph", "langsmith",
    "os", "sys", "pathlib", "io", "shutil", "subprocess", "tempfile", "pickle", "random", "secrets", "uuid", "logging", "asyncio",
}
ALLOWED_ROOTS = {"http", "json", "socket", "time", "urllib", "dataclasses", "eidos", "typing", "enum"}
ALLOWED_EIDOS = {"eidos.agents"}


def imports_of(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    return found


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_standard_library_http_pieces_and_the_agents_port_are_imported(module):
    roots = {name.split(".")[0] for name in imports_of(module) if not name.startswith(".")}
    assert roots & FORBIDDEN_IMPORTS == set()
    assert roots <= ALLOWED_ROOTS, f"{module.name} imports {sorted(roots - ALLOWED_ROOTS)}"
    for name in imports_of(module):
        if name.startswith("eidos"):
            assert ".".join(name.split(".")[:2]) in ALLOWED_EIDOS, f"{module.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_a_provider_opens_no_file_prints_nothing_and_executes_no_generated_code(module):
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "print", "eval", "exec", "compile", "input", "__import__"}, node.func.id


def test_the_adapter_reads_no_environment_and_has_no_default_endpoint():
    source = (PROVIDERS / "ollama.py").read_text(encoding="utf-8")
    assert "environ" not in source and "getenv" not in source  # nothing is ambient (D-135)
    assert not re.search(r"(localhost|127\.0\.0\.1|11434)", source), "an endpoint is the caller's choice, never a default"


# --- nothing depends on a provider ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target", ["contracts", "validation", "compiler", "runtime", "backends", "agents", "capabilities"]
)
def test_no_other_package_imports_a_provider(target):
    for path in sorted((SRC / target).rglob("*.py")):
        for name in imports_of(path):
            assert "providers" not in name.split("."), f"{path.relative_to(SRC)} imports {name}"


def test_the_runner_and_the_agents_are_never_handed_a_provider_by_import():
    assert all("providers" not in name for name in imports_of(SRC / "baseline.py"))


# --- D-136: no new dependency, and real-model tests are an explicit opt-in --------------------------------------------------------


def pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_provider_added_no_dependency_and_no_extra():
    project = pyproject()["project"]
    assert project["dependencies"] == ["pydantic>=2"]
    # D-171 (V0.6 Step 5) added a second optional extra, "a2a" (httpx, the one dependency eidos.a2a needs) — the
    # same shape as "langgraph" (D-116): an extra eidos.providers itself contributes nothing to and never imports.
    assert set(project["optional-dependencies"]) == {"langgraph", "a2a", "dev"}
    assert project["optional-dependencies"]["dev"] == ["pytest", "eidos[langgraph]", "eidos[a2a]"]


def test_real_model_tests_are_registered_and_excluded_from_the_default_run_never_skipped():
    options = pyproject()["tool"]["pytest"]["ini_options"]
    assert any(marker.startswith("real_model") for marker in options["markers"])
    assert "-m not real_model" in options["addopts"] or "not real_model" in options["addopts"]
    real = (ROOT / "tests" / "integration" / "providers" / "test_ollama_real.py").read_text(encoding="utf-8")
    assert "pytest.skip" not in real and "skipif" not in real and "importorskip" not in real  # CLAUDE.md section 6
    assert "pytest.mark.real_model" in real
