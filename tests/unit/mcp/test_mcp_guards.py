"""Static guards on ``eidos.mcp`` (decisions.md D-203, D-207, invariants 9 and 14, CLAUDE.md §3 and §8; V1.2 Step 5).

The MCP package is transport and nothing else: hand-rolled, standard library only, no SDK, no admission policy, no state, no recorder, and the only place
in EIDOS that starts a process. No other package imports it. These are checks on the source, so they hold however the client is later extended.
"""

import ast
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "eidos"
MCP = SRC / "mcp"
MODULES = sorted(MCP.glob("*.py"))

FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "datetime", "http", "importlib", "logging", "multiprocessing", "os", "pathlib", "pickle", "random", "requests", "secrets",
    "shelve", "shutil", "socket", "sqlite3", "ssl", "sys", "tempfile", "urllib", "uuid", "httpx", "aiohttp", "numpy", "networkx", "langgraph", "langchain",
    "langsmith", "ollama", "openai", "anthropic", "mcp", "fastmcp",
}
ALLOWED_ROOTS = {
    "protocol.py": {"__future__", "collections", "dataclasses", "hashlib", "json", "typing", "eidos"},
    "stdio.py": {"__future__", "collections", "queue", "subprocess", "threading", "time", "typing", "pydantic", "eidos"},
    "__init__.py": {"__future__", "eidos"},
}
ALLOWED_EIDOS = {"eidos.agents", "eidos.capabilities", "eidos.contracts", "eidos.mcp"}
# The vocabulary of a tool port and nothing of the gate, the store or an agent: transport speaks in ToolRequest, ToolResult and ToolFailure.
ALLOWED_AGENT_NAMES = {"ToolDocument", "ToolFailure", "ToolFailureKind", "ToolOutcome", "ToolPort", "ToolRequest", "ToolResult", "bound_result"}
VENDOR_NAMES = {"anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere", "ollama", "qdrant", "a2a", "langgraph", "langchain", "langsmith"}
# Nothing that is a decision of EIDOS's own policy may be named in code here: admission is decided before a request reaches this package.
POLICY_NAMES = {
    "admit_tool_call", "ToolAdmission", "ToolDenial", "ToolDenialCode", "ToolInvocationRecord", "allowed_actions", "autonomy_level", "AutonomyLevel",
    "max_tool_calls", "read_only", "action_id",
}
# What a server says about itself, and so what is never read.
SERVER_CLAIMS = {"annotations", "readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint", "serverInfo", "instructions"}


def imports_of(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    return found


def names_in_code(path: Path) -> set[str]:
    """Every identifier, attribute and string literal used as code, not the prose of a docstring."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {id(node.body[0].value) for node in ast.walk(tree) if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and node.body
                  and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)}
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            found.add(node.value)
    return found


def test_the_package_is_exactly_the_modules_that_implement_the_client():
    assert [module.name for module in MODULES] == ["__init__.py", "protocol.py", "stdio.py"]


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_standard_library_a_module_needs_is_imported_and_no_sdk_no_network_library_and_no_socket(module):
    roots = {name.split(".")[0] for name in imports_of(module) if not name.startswith(".")}
    assert roots & FORBIDDEN_IMPORTS == set()
    assert roots <= ALLOWED_ROOTS[module.name], f"{module.name} imports {sorted(roots - ALLOWED_ROOTS[module.name])}"


def test_the_protocol_module_is_pure_it_starts_no_process_and_opens_no_thread_queue_or_clock():
    roots = {name.split(".")[0] for name in imports_of(MCP / "protocol.py")}
    assert roots & {"subprocess", "threading", "queue", "time", "os", "sys", "socket"} == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_tool_port_vocabulary_the_capabilities_and_the_contracts_are_depended_on_never_policy_state_recording_or_the_gate(module):
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").startswith("eidos"):
            assert ".".join(node.module.split(".")[:2]) in ALLOWED_EIDOS, f"{module.name} imports {node.module}"
            if node.module == "eidos.agents":
                assert {alias.name for alias in node.names} <= ALLOWED_AGENT_NAMES, f"{module.name} imports {[a.name for a in node.names]}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("eidos"), f"{module.name} imports {alias.name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_admission_policy_is_not_here_no_decision_of_eidoss_own_is_named_in_the_code(module):
    assert names_in_code(module) & POLICY_NAMES == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_nothing_a_server_says_about_itself_is_read_no_annotation_no_identity_no_instruction(module):
    assert names_in_code(module) & SERVER_CLAIMS == set()


def test_no_source_file_anywhere_in_eidos_reads_a_tool_annotation():
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "readOnlyHint" not in text and "destructiveHint" not in text, path.relative_to(SRC)


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_vendor_name_appears_in_the_package(module):
    words = set(re.findall(r"[a-z0-9]+", module.read_text(encoding="utf-8").lower()))
    assert words & VENDOR_NAMES == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_shell_no_dynamic_code_no_file_no_print_and_no_wall_clock(module):
    text = module.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "print", "eval", "exec", "compile", "input", "__import__"}, node.func.id
        if isinstance(node, ast.keyword) and node.arg == "shell":
            assert isinstance(node.value, ast.Constant) and node.value.value is False
    for forbidden in ("os.system", "os.popen", "shell=True", "time.time", "datetime", "random.", "uuid."):
        assert forbidden not in text, forbidden


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_module_level_mutable_state(module):
    for node in ast.parse(module.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
                continue
            assert not isinstance(node.value, (ast.List, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)), module.name
            if isinstance(node.value, ast.Dict):  # the fixed request metadata: a constant table, not state a module ever changes
                assert getattr(targets[0], "id", "") in {"CLIENT_INFO", "_META"}, module.name


def test_the_mcp_package_is_the_only_place_that_starts_a_process():
    for path in sorted(SRC.rglob("*.py")):
        if MCP in path.parents:
            continue
        imported = {name.split(".")[0] for name in imports_of(path) if not name.startswith(".")}
        assert "subprocess" not in imported, f"{path.relative_to(SRC)} imports subprocess"


def test_no_other_package_imports_the_mcp_package():
    for path in sorted(SRC.rglob("*.py")):
        if MCP in path.parents:
            continue
        for name in imports_of(path):
            assert not name.startswith(("eidos.mcp", ".mcp")), f"{path.relative_to(SRC)} imports {name}"


def test_no_dependency_was_added_for_it_the_project_declares_no_mcp_or_sdk_package():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = list(project["project"].get("dependencies", ()))
    for extra in project["project"].get("optional-dependencies", {}).values():
        declared.extend(extra)
    names = {re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].strip().lower().replace("_", "-") for spec in declared}
    assert not any("mcp" in name for name in names), sorted(names)


def test_importing_the_mcp_package_loads_no_state_recorder_backend_provider_planner_or_workflow_library():
    # eidos.agents, whose port vocabulary this package uses, brings its own gate and the policy layer with it; the source-level guards above are what
    # keep this package's own code from naming either.
    code = (
        "import sys; sys.path.insert(0, 'src'); import eidos.mcp\n"
        "print(sorted(m for m in sys.modules if m.startswith(('eidos.state', 'eidos.recording', 'eidos.backends', 'eidos.providers', "
        "'eidos.a2a', 'eidos.planning', 'eidos.replanning')) or m.split('.')[0] in ('langgraph', 'langchain', 'langsmith', "
        "'httpx', 'requests', 'mcp')))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_the_research_agent_and_the_gate_name_no_transport_however_it_is_provided():
    for name in ("research.py", "tool_gate.py", "tool.py"):
        words = set(re.findall(r"[a-z0-9]+", (SRC / "agents" / name).read_text(encoding="utf-8").lower()))
        assert words & {"mcp", "stdio", "subprocess", "jsonrpc"} == set(), name
