"""Static guards on ``eidos.policy`` (decisions.md D-203, invariant 14, CLAUDE.md §8; V1.2 Step 2).

The governance layer is deterministic and pure: no I/O, network, subprocess, clock, randomness, model call or hidden state, and no knowledge of
any transport, provider, SDK or vendor. It depends only on ``eidos.contracts`` and ``eidos.capabilities``; it imports no agent, adapter or
backend, and no core layer imports it. It is not a general policy engine, so it is also held to exactly the modules that implement tool admission.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
POLICY = SRC / "policy"
MODULES = sorted(POLICY.glob("*.py"))

FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "datetime", "http", "importlib", "io", "logging", "multiprocessing", "os", "pathlib", "pickle", "random",
    "requests", "secrets", "shelve", "shutil", "socket", "sqlite3", "ssl", "subprocess", "sys", "tempfile", "threading", "time", "urllib",
    "uuid", "httpx", "aiohttp", "numpy", "networkx", "langgraph", "langchain", "langsmith", "ollama", "openai", "anthropic",
}
ALLOWED_ROOTS = {"__future__", "collections", "enum", "hashlib", "json", "typing", "pydantic", "eidos"}
ALLOWED_EIDOS = {"eidos.contracts", "eidos.capabilities"}
VENDOR_NAMES = {
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere", "ollama", "qdrant", "a2a", "mcp", "rag", "laya", "dspy",
    "langgraph", "langchain", "langsmith",
}
LOWER_LAYERS = (
    "contracts", "validation", "compiler", "runtime", "state", "planning", "expansion", "memory", "telemetry", "capabilities", "backends",
    "recording", "baseline", "providers", "selectors", "a2a",
)


def imports_of(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    return found


def test_the_package_is_exactly_the_modules_that_implement_tool_admission():
    assert [module.name for module in MODULES] == ["__init__.py", "tool_admission.py"]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_io_network_process_clock_randomness_or_vendor_library_is_imported(module):
    roots = {name.split(".")[0] for name in imports_of(module) if not name.startswith(".")}
    assert roots & FORBIDDEN_IMPORTS == set()
    assert roots <= ALLOWED_ROOTS, f"{module.name} imports {sorted(roots - ALLOWED_ROOTS)}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_contracts_and_the_capabilities_are_depended_on_never_an_agent_adapter_or_backend(module):
    for name in imports_of(module):
        if name.startswith("eidos"):
            assert ".".join(name.split(".")[:2]) in ALLOWED_EIDOS, f"{module.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_transport_provider_sdk_or_vendor_name_appears(module):
    words = set(re.findall(r"[a-z0-9]+", module.read_text(encoding="utf-8").lower()))
    assert words & VENDOR_NAMES == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_direct_call_to_io_process_or_dynamic_code_and_no_wall_clock_or_random_text(module):
    text = module.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "print", "eval", "exec", "compile", "input", "__import__"}, node.func.id
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            assert "__main__" not in ast.dump(node.test)
    for forbidden in ("datetime.now", "time.monotonic", "time.time", "uuid.uuid4", "random.", "os.environ"):
        assert forbidden not in text, forbidden


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_level_mutable_state(module):
    for node in ast.parse(module.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                continue
            assert not isinstance(node.value, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp))


def test_admission_raises_nothing_for_a_domain_outcome_only_a_programming_error():
    tree = ast.parse((POLICY / "tool_admission.py").read_text(encoding="utf-8"))
    (function,) = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "admit_tool_call"]
    raises = [n for n in ast.walk(function) if isinstance(n, ast.Raise)]
    assert len(raises) == 1 and isinstance(raises[0].exc, ast.Call) and raises[0].exc.func.id == "ValueError"  # the negative-budget check


def test_admission_never_reads_the_schema_pin_or_a_provider_claim():
    # The pin is for noticing a provider's schema change when the provider is contacted; admission is decided by the allowlist alone.
    text = (POLICY / "tool_admission.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(("#", '"', "'")))
    assert "input_schema_digest" not in code
    assert "annotation" not in code and "readOnlyHint" not in text


@pytest.mark.parametrize("package", LOWER_LAYERS)
def test_no_lower_layer_or_adapter_imports_the_policy_package(package):
    root = SRC / package
    paths = [root] if root.is_file() else (sorted(root.rglob("*.py")) if root.is_dir() else [])
    for path in paths:
        for name in imports_of(path):
            assert not name.startswith("eidos.policy"), f"{path.relative_to(SRC)} imports {name}"


def test_importing_the_policy_package_loads_no_agent_adapter_transport_or_workflow_library():
    code = (
        "import sys; sys.path.insert(0, 'src'); import eidos.policy\n"
        "print(sorted(m for m in sys.modules if m.startswith(('eidos.agents', 'eidos.providers', 'eidos.backends', 'eidos.a2a', 'eidos.recording', "
        "'eidos.selectors', 'eidos.baseline', 'eidos.replanning', 'eidos.mcp')) or m.split('.')[0] in ('langgraph', 'langchain', 'langsmith', 'httpx', 'requests')))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=SRC.parents[1])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_the_tool_types_added_to_agents_and_capabilities_import_no_policy_and_no_transport():
    for path in (SRC / "capabilities" / "tools.py", SRC / "agents" / "tool.py"):
        for name in imports_of(path):
            assert not name.startswith(("eidos.policy", "eidos.mcp", "eidos.providers", "eidos.a2a", "eidos.backends")), f"{path.name} imports {name}"
