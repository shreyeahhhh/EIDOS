"""Static guards on ``eidos.tools`` (decisions.md D-238): the one package that makes outbound requests on a user's behalf is held to the same discipline as the providers.

Standard library only (no HTTP client library to inherit a redirect or proxy behaviour from); nothing ambient (no environment, file, process or logging); no import of the layers that wire it; no
core layer, agent or runtime imports it; and no way to execute what a page says.
"""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "eidos"
TOOLS = SRC / "tools"
MODULES = sorted(TOOLS.glob("*.py"))

FORBIDDEN_IMPORTS = {
    "requests", "httpx", "httpx2", "aiohttp", "urllib3", "pycurl", "mechanize", "selenium", "playwright", "bs4", "lxml", "html5lib",
    "os", "sys", "pathlib", "io", "shutil", "subprocess", "tempfile", "pickle", "marshal", "random", "secrets", "uuid", "logging", "asyncio", "importlib", "ctypes",
}
ALLOWED_ROOTS = {"concurrent", "dataclasses", "hashlib", "html", "http", "ipaddress", "re", "socket", "ssl", "time", "typing", "urllib", "collections", "eidos"}
ALLOWED_EIDOS = {"eidos.agents", "eidos.capabilities", "eidos.contracts"}
NOT_IMPORTED_BY_TOOLS = {"api", "service", "persistence", "providers", "recording", "state", "runtime", "compiler", "backends", "mcp", "knowledge"}


def imports_of(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    return found


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_only_the_standard_library_and_the_tool_port_are_imported(module):
    names = [name for name in imports_of(module) if not name.startswith(".")]
    roots = {name.split(".")[0] for name in names}
    assert roots & FORBIDDEN_IMPORTS == set()
    assert roots <= ALLOWED_ROOTS, f"{module.name} imports {sorted(roots - ALLOWED_ROOTS)}"
    for name in names:
        if name.startswith("eidos"):
            assert ".".join(name.split(".")[:2]) in ALLOWED_EIDOS, f"{module.name} imports {name}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.name)
def test_nothing_ambient_no_environment_no_file_no_print_no_generated_code(module):
    tree = ast.parse(module.read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not names & {"environ", "getenv", "getenvb", "environb"}  # the code, not its docstrings: nothing is read from the process environment
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "print", "eval", "exec", "compile", "input", "__import__"}, node.func.id


def test_the_fetcher_never_follows_redirects_by_itself_and_never_uses_a_high_level_opener():
    source = (TOOLS / "safe_https.py").read_text(encoding="utf-8")
    for forbidden in ("urlopen", "build_opener", "HTTPRedirectHandler", "ProxyHandler", "install_opener", "urllib.request", "requests.", "set_tunnel", "proxies"):
        assert forbidden not in source, forbidden  # a proxy would be a way around the address checks
    assert "http.client.HTTPSConnection" in source and "wrap_socket" in source  # the connection is built by hand, to the address that was checked


def test_tls_is_verified_and_never_switched_off():
    source = (TOOLS / "safe_https.py").read_text(encoding="utf-8")
    assert "create_default_context" in source
    for forbidden in ("CERT_NONE", "check_hostname = False", "_create_unverified_context", "verify=False", "PROTOCOL_TLS_SERVER"):
        assert forbidden not in source, forbidden


def test_only_get_is_ever_sent_and_no_header_comes_from_the_caller():
    source = (TOOLS / "safe_https.py").read_text(encoding="utf-8")
    assert re.findall(r'connection\.request\(\s*"(\w+)"', source) == ["GET"]
    assert "Authorization" not in source and "Cookie" not in source


@pytest.mark.parametrize("target", ["contracts", "validation", "compiler", "runtime", "backends", "agents", "capabilities", "state", "recording", "policy", "service", "persistence", "providers"])
def test_no_other_package_imports_the_tools_except_through_the_composition_root(target):
    for path in sorted((SRC / target).rglob("*.py")):
        for name in imports_of(path):
            assert name.split(".")[:2] != ["eidos", "tools"], f"{path.relative_to(SRC)} imports {name}"  # (``eidos.capabilities.tools`` is an unrelated module of the same name)


def test_the_api_package_reaches_the_tools_only_from_its_composition_root():
    importers = [path.name for path in sorted((SRC / "api").glob("*.py")) if any(name.split(".")[:2] == ["eidos", "tools"] for name in imports_of(path))]
    assert importers == ["main.py"]


def test_real_network_tests_are_registered_and_excluded_from_the_default_run_never_skipped():
    import tomllib

    options = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
    assert any(marker.startswith("web_fetch") for marker in options["markers"])
    assert "not web_fetch" in options["addopts"]
    real = (ROOT / "tests" / "integration" / "tools" / "test_web_fetch_real.py").read_text(encoding="utf-8")
    assert "pytest.skip" not in real and "skipif" not in real and "importorskip" not in real  # CLAUDE.md section 6
    assert "pytest.mark.web_fetch" in real


def test_the_tool_added_no_dependency():
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["dependencies"] == ["pydantic>=2"]
    assert set(project["optional-dependencies"]) == {"langgraph", "a2a", "api", "postgres", "dev"}
