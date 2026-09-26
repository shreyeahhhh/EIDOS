"""Static guards on ``eidos.agents`` (decisions.md D-135, D-140; CLAUDE.md §8; invariants 3, 9).

The agents package is vendor-free, does no I/O beyond its ports, never reaches a provider, and no core layer
ever imports it. These are checks on the source, so they hold however the agents are later implemented.

The package may depend on ``eidos.policy`` (the tool-admission seam, D-205) and, since V1.3 Step 3, on the knowledge boundary (D-222): two modules since Step 7 (D-228), each
with a fixed set of names, taken from the package root, one way only.
"""

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[3] / "src" / "eidos"
AGENTS = SRC / "agents"
MODULES = sorted(AGENTS.glob("*.py"))

# I/O, network, clock, randomness, process state and every workflow or model library: an agent is read-only (D-140).
FORBIDDEN_IMPORTS = {
    "asyncio", "concurrent", "datetime", "http", "importlib", "io", "logging", "multiprocessing", "os", "pathlib",
    "pickle", "random", "requests", "secrets", "shelve", "shutil", "socket", "sqlite3", "ssl", "subprocess", "sys",
    "tempfile", "time", "urllib", "uuid", "httpx", "aiohttp", "numpy", "networkx", "langgraph", "langchain",
    "langsmith", "ollama", "openai", "anthropic",
}
# The only third-party or standard-library modules the agents package may import.
ALLOWED_ROOTS = {"__future__", "collections", "dataclasses", "enum", "re", "threading", "typing", "pydantic", "eidos"}
ALLOWED_EIDOS = {"eidos.contracts", "eidos.runtime", "eidos.compiler", "eidos.capabilities", "eidos.agents", "eidos.policy", "eidos.knowledge"}
# D-205 ruling 4: a deliberate extension, for the eidos.agents -> eidos.policy tool-admission seam and nothing wider. Pinned below so a
# further dependency (a transport, a recorder, a provider) cannot be added here without changing this line on purpose.
PRE_ADMISSION_ALLOWED_EIDOS = {"eidos.contracts", "eidos.runtime", "eidos.compiler", "eidos.capabilities", "eidos.agents"}
# D-222 point 4 (the owner's import-guard ruling, 2026-09-25): the second deliberate extension, for the eidos.agents -> eidos.knowledge boundary. Only the
# evidence ledger module depends on it, only on these names and only from the package root; eidos.knowledge never imports eidos.agents (its own guard test).
# Step 7 (D-228, the deliberate revision D-224 reading 10 said a later step would make): the knowledge gate is the second boundary module, with its own pinned names, and the
# Research agent and every other module still import nothing of eidos.knowledge: Research depends on the gate's protocol, not on the port or on any retriever.
KNOWLEDGE_BOUNDARY_MODULES = {"evidence_ledger.py", "knowledge_gate.py"}
APPROVED_KNOWLEDGE_NAMES = {
    "evidence_ledger.py": {
        "DocumentRef",
        "EvidenceRecord",
        "EvidenceRefusal",
        "EvidenceRefusalCode",
        "IndependenceResolution",
        "legacy_supplied_record",
        "legacy_tool_record",
        "merge_evidence",
        "resolve_independence",
    },
    "knowledge_gate.py": {
        "KB_ID_PATTERN",
        "EvidenceRecord",
        "EvidenceRefusal",
        "KnowledgePort",
        "KnowledgeSnapshot",
        "RetrievalFailure",
        "RetrievalFailureKind",
        "RetrievalRequest",
        "RetrievalResult",
        "canonical_query_text",
        "evidence_from_snapshot",
        "merge_evidence",
        "result_problem",
    },
}

VENDOR_NAMES = {
    "anthropic", "claude", "openai", "gpt", "gemini", "mistral", "llama", "cohere", "ollama", "qdrant", "a2a", "mcp",
    "langgraph", "langchain", "langsmith",
}
CORE_PACKAGES = ("contracts", "validation", "compiler", "runtime", "backends")


def imports_of(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    return found


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_io_network_clock_randomness_or_model_library_is_imported(module):
    roots = {name.split(".")[0] for name in imports_of(module) if not name.startswith(".")}
    assert roots & FORBIDDEN_IMPORTS == set()
    assert roots <= ALLOWED_ROOTS, f"{module.name} imports {sorted(roots - ALLOWED_ROOTS)}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_eidos_layers_an_agent_may_depend_on_are_imported(module):
    for name in imports_of(module):
        if name.startswith("eidos"):
            assert ".".join(name.split(".")[:2]) in ALLOWED_EIDOS, f"{module.name} imports {name}"
            assert "providers" not in name and "backends" not in name, f"{module.name} imports {name}"


def test_the_only_layers_added_to_what_an_agent_may_depend_on_are_the_tool_admission_seam_and_the_knowledge_boundary():
    assert ALLOWED_EIDOS - PRE_ADMISSION_ALLOWED_EIDOS == {"eidos.policy", "eidos.knowledge"}
    assert PRE_ADMISSION_ALLOWED_EIDOS <= ALLOWED_EIDOS


def eidos_names_imported(path: Path) -> set[str]:
    """Every dotted ``eidos`` name a module imports, including a name taken with ``from eidos import x``."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if alias.name.split(".")[0] == "eidos")
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.split(".")[0] == "eidos":
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_two_boundary_modules_depend_on_the_knowledge_package(module):
    depends = {name for name in eidos_names_imported(module) if name == "eidos.knowledge" or name.startswith("eidos.knowledge.")}
    assert bool(depends) == (module.name in KNOWLEDGE_BOUNDARY_MODULES), f"{module.name} imports {sorted(depends)}"


@pytest.mark.parametrize("module_name", sorted(KNOWLEDGE_BOUNDARY_MODULES))
def test_each_boundary_module_takes_exactly_its_approved_knowledge_names_from_the_package_root_and_nothing_else(module_name):
    tree = ast.parse((AGENTS / module_name).read_text(encoding="utf-8"))
    knowledge_imports = [
        node for node in ast.walk(tree)
        if (isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").startswith("eidos.knowledge"))
        or (isinstance(node, ast.Import) and any(alias.name.startswith("eidos.knowledge") for alias in node.names))
    ]
    (statement,) = knowledge_imports
    assert isinstance(statement, ast.ImportFrom) and statement.module == "eidos.knowledge"
    assert {alias.name for alias in statement.names} == APPROVED_KNOWLEDGE_NAMES[module_name]
    assert all(alias.asname is None for alias in statement.names)


def test_the_research_agent_reaches_knowledge_only_through_the_gates_protocol_and_names_no_retriever_implementation_or_process():
    assert not [name for name in eidos_names_imported(AGENTS / "research.py") if name.startswith("eidos.knowledge")]
    words = set(re.findall(r"[a-z0-9]+", (AGENTS / "research.py").read_text(encoding="utf-8").lower()))
    assert words & {"semanticknowledgeport", "lexicalknowledgeport", "isolatedembedder", "embedder", "subprocess", "worker", "torch", "transformers"} == set()
    assert "knowledgeaccess" in words  # what it does depend on


@pytest.mark.parametrize("module", sorted((SRC / "policy").glob("*.py")), ids=lambda m: m.name)
def test_the_admission_seam_points_one_way_policy_never_imports_an_agent_or_anything_above_the_capabilities(module):
    for name in imports_of(module):
        if name.startswith("eidos"):
            assert ".".join(name.split(".")[:2]) in {"eidos.contracts", "eidos.capabilities", "eidos.policy"}, f"{module.name} imports {name}"


def test_the_tool_seam_types_themselves_stay_free_of_the_admission_package_and_every_transport():
    # The extension permits an agent module to call admission; it does not let the seam's own request/result types depend on it.
    for name in imports_of(AGENTS / "tool.py"):
        assert not name.startswith(("eidos.policy", "eidos.mcp", "eidos.providers", "eidos.backends", "eidos.a2a", "eidos.recording")), name


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_no_vendor_or_model_name_appears_in_the_agents_package(module):
    words = set(re.findall(r"[a-z0-9]+", module.read_text(encoding="utf-8").lower()))
    assert words & VENDOR_NAMES == set()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_an_agent_module_opens_no_file_prints_nothing_and_executes_no_generated_code(module):
    # Invariant 3 and D-140: nothing a model returns is ever executed, and an agent takes no action.
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "print", "eval", "exec", "compile", "input", "__import__"}, (
                f"{module.name}: {node.func.id}()"
            )


@pytest.mark.parametrize("package", CORE_PACKAGES)
def test_no_core_layer_imports_agents_capabilities_or_providers(package):
    for path in sorted((SRC / package).rglob("*.py")):
        for name in imports_of(path):
            parts = name.split(".")
            assert not (parts[0] == "eidos" and len(parts) > 1 and parts[1] in {"agents", "capabilities", "providers"}), (
                f"{path.relative_to(SRC)} imports {name}"
            )


def test_importing_the_agents_package_loads_no_provider_backend_or_workflow_library():
    import subprocess
    import sys

    code = (
        "import sys; sys.path.insert(0, 'src'); import eidos.agents\n"
        "print(sorted(m for m in sys.modules if m.split('.')[0] in ('langgraph', 'langchain', 'langsmith', 'requests', 'httpx') "
        "or m.startswith('eidos.providers') or m.startswith('eidos.backends')))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=SRC.parents[1])
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
