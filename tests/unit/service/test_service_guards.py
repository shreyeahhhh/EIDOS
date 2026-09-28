"""Static guards on the product backend's boundaries (decisions.md D-229 to D-234, D-236; invariants 1, 2 and 9; ``CLAUDE.md`` section 8; V1.4-B).

Three new packages and one direction of dependency: ``eidos.api`` (HTTP) calls ``eidos.service`` (use cases) which runs the unchanged core, and ``eidos.persistence`` (PostgreSQL) implements the
service's ports. New libraries stay behind their one boundary, the core imports none of the three, FastAPI never touches the log or the reducer, there is no ORM, and the migrations deny every API
role by construction.

D-236 (V1.6): the "nothing deferred was built" and "no credential is committed" guards below were written at V1.4-B, when the repository was backend-only, and scanned the raw filesystem. Both were
made git-aware (``_committable_files()``) rather than weakened, once ``frontend`` (V1.5, an owner decision, not a violation) made their original raw-filesystem assumption stop matching reality.
"""

import ast
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src" / "eidos"
API, SERVICE, PERSISTENCE = SRC / "api", SRC / "service", SRC / "persistence"
NEW_PACKAGES = ("api", "service", "persistence")
CORE_PACKAGES = sorted(p.name for p in SRC.iterdir() if (p.is_dir() and p.name not in NEW_PACKAGES and p.name != "__pycache__"))
HTTP_LIBRARIES = {"fastapi", "starlette", "uvicorn", "jwt", "httpx"}
DATABASE_LIBRARIES = {"psycopg", "psycopg_pool", "psycopg2", "asyncpg"}
ORMS = {"sqlalchemy", "sqlmodel", "alembic", "tortoise", "peewee", "django", "databases", "ormar", "pony"}


def imports_of(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append(("." * node.level) + (node.module or ""))
    return found


def roots(path: Path) -> set[str]:
    return {name.split(".")[0] for name in imports_of(path) if not name.startswith(".")}


def eidos_targets(path: Path) -> set[str]:
    """The top-level ``eidos`` package (or module) each import of this file reaches, with relative imports resolved against the file's own place in the tree."""
    found: set[str] = set()
    here = list(path.relative_to(SRC).parts[:-1])  # the file's package, below ``eidos``
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[1] for alias in node.names if alias.name.startswith("eidos."))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module == "eidos":
                    found.update(alias.name for alias in node.names)
                elif node.module and node.module.startswith("eidos."):
                    found.add(node.module.split(".")[1])
            else:
                base = here[: len(here) - (node.level - 1)] if node.level > 1 else here
                target = base + (node.module.split(".") if node.module else [])
                if target:
                    found.add(target[0])
    return found


def modules(package: Path) -> list[Path]:
    return sorted(package.rglob("*.py"))


# --- the direction of dependency ------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("package", CORE_PACKAGES)
def test_no_core_package_imports_the_service_the_api_or_the_persistence_layer(package):
    for path in sorted((SRC / package).rglob("*.py")):
        assert not set(eidos_targets(path)) & set(NEW_PACKAGES), f"{path.relative_to(SRC)} imports {sorted(set(eidos_targets(path)) & set(NEW_PACKAGES))}"
    for path in sorted(SRC.glob("*.py")):  # the top-level modules (replanning, baseline, recording, ...) are core too
        assert not set(eidos_targets(path)) & set(NEW_PACKAGES), path.name


@pytest.mark.parametrize("module", modules(SERVICE), ids=lambda m: m.name)
def test_the_service_imports_no_http_no_jwt_no_database_driver_and_neither_of_its_neighbours(module):
    assert roots(module) & (HTTP_LIBRARIES | DATABASE_LIBRARIES | ORMS) == set(), module.name
    assert eidos_targets(module) & {"api", "persistence", "providers"} == set(), module.name  # ports point outward: it is implemented by them, and it names no vendor
    assert "knowledge" not in eidos_targets(module), module.name  # the knowledge package is imported by three boundary modules only (its own guard); the service hands a retriever over structurally


@pytest.mark.parametrize("module", modules(PERSISTENCE), ids=lambda m: m.name)
def test_the_persistence_layer_imports_a_database_driver_and_no_http_and_not_the_api(module):
    assert roots(module) & (HTTP_LIBRARIES | ORMS) == set(), module.name
    assert eidos_targets(module) & {"api", "providers", "runtime", "replanning", "recording"} == set(), module.name


@pytest.mark.parametrize("module", modules(API), ids=lambda m: m.name)
def test_the_api_imports_no_database_driver_and_no_orm(module):
    assert roots(module) & (DATABASE_LIBRARIES | ORMS) == set(), module.name


def test_only_the_api_package_imports_fastapi_and_the_jwt_library_and_only_persistence_imports_the_driver():
    for path in SRC.rglob("*.py"):
        package = path.relative_to(SRC).parts[0]
        found = roots(path)
        if package != "api":
            assert not found & {"fastapi", "starlette", "uvicorn", "jwt"}, path.relative_to(SRC)
        if package != "persistence":
            assert not found & DATABASE_LIBRARIES, path.relative_to(SRC)
        assert not found & ORMS, path.relative_to(SRC)


def test_the_routes_and_the_error_and_auth_modules_reach_no_runtime_internals():
    """FastAPI never touches the log, the reducer or the runtime (invariant 2): a route calls the service and nothing else of EIDOS but identifiers and the request body's type."""
    allowed = {"contracts", "service"}
    for name in ("app.py", "auth.py", "errors.py"):
        assert eidos_targets(API / name) - {"api"} <= allowed, (name, eidos_targets(API / name))
    names = {node.id for node in ast.walk(ast.parse((API / "app.py").read_text(encoding="utf-8"))) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(ast.parse((API / "app.py").read_text(encoding="utf-8"))) if isinstance(node, ast.Attribute)}
    assert not names & {"EventLog", "MissionState", "replay", "accept", "reduce", "Recorder", "run_with_replanning", "execution_record", "EventProposal"}, names


def test_the_composition_root_is_the_only_api_module_that_wires_persistence_and_a_provider():
    for path in modules(API):
        reached = eidos_targets(path)
        if path.name == "main.py":
            assert {"persistence", "providers"} <= reached
        else:
            assert not reached & {"persistence", "providers"}, path.name


# --- nothing in the new packages builds or mutates MissionState -------------------------------------------------------------------------------


@pytest.mark.parametrize("module", modules(SERVICE) + modules(PERSISTENCE) + modules(API), ids=lambda m: f"{m.parent.name}/{m.name}")
def test_no_new_module_constructs_mission_state_or_skips_validation(module):
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            assert target not in {"MissionState", "model_construct", "model_copy", "eval", "exec", "__import__"}, f"{module.name} calls {target}"


@pytest.mark.parametrize(
    "module", [p for p in modules(SERVICE) + modules(API) + modules(PERSISTENCE) if p.name not in {"durable.py", "spec.py"}], ids=lambda m: f"{m.parent.name}/{m.name}"
)
def test_only_the_durable_log_and_the_carrier_state_accept_events_and_nothing_else_here_does(module):
    """``EventLog.accept`` is the reducer's only door. Two modules use it: ``durable.py`` (the run's log) and ``spec.py`` (``initial_state`` folds one ``MISSION_CREATED`` through a throwaway log to obtain the
    carrier state the runtime is handed, because only the reducer may construct a ``MissionState``). Nothing else in the new packages calls ``accept`` or ``reduce``."""
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Attribute) and node.attr in {"accept", "reduce", "apply_event"}:
            pytest.fail(f"{module.name} calls .{node.attr}")


def test_the_durable_log_is_an_event_log_and_persists_only_what_the_reducer_applied():
    from eidos.service import DurableEventLog
    from eidos.state import EventLog

    assert issubclass(DurableEventLog, EventLog)
    source = (SERVICE / "durable.py").read_text(encoding="utf-8")
    assert "super().accept(" in source and "applied" in source


def test_run_status_appears_in_no_core_package():
    for package in CORE_PACKAGES:
        for path in (SRC / package).rglob("*.py"):
            assert "run_status" not in path.read_text(encoding="utf-8"), path.relative_to(SRC)
    for path in SRC.glob("*.py"):
        assert "run_status" not in path.read_text(encoding="utf-8"), path.name


# --- the api's handlers are plain functions ---------------------------------------------------------------------------------------------------


def test_route_handlers_are_plain_functions_because_the_runtime_is_synchronous():
    """A synchronous handler runs in FastAPI's thread pool. The only coroutines are the exception handlers, the lifespan and the body reader."""
    tree = ast.parse((API / "app.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            assert node.name in {"lifespan", "raw_body", "_service_error", "_unauthenticated", "_auth_unavailable", "_bad_request", "_framework_error", "_unexpected"}, node.name
        if isinstance(node, ast.FunctionDef) and any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in {"get", "post"} for d in node.decorator_list):
            assert node.name in {"healthz", "create_mission", "start_mission", "get_mission", "get_execution", "get_events", "get_result", "get_evidence"}, node.name


# --- no ORM, no new service, no deferred build -------------------------------------------------------------------------------------------------


def pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_new_libraries_are_optional_extras_behind_their_boundaries_and_the_base_install_is_unchanged():
    project = pyproject()["project"]
    extras = project["optional-dependencies"]
    assert not any(re.match(r"(fastapi|uvicorn|pyjwt|psycopg)", dependency.lower()) for dependency in project["dependencies"])
    assert [re.split(r"[<>=\[]", d)[0].lower() for d in extras["api"]] == ["fastapi", "uvicorn", "pyjwt"]
    assert [re.split(r"[<>=\[]", d)[0].lower() for d in extras["postgres"]] == ["psycopg"]
    everything = " ".join(d.lower() for group in extras.values() for d in group)
    assert not any(orm in everything for orm in ORMS) and "qdrant" not in everything and "docker" not in everything


def test_nothing_deferred_was_built():
    """Still-deferred infrastructure has not appeared without an explicit decision (D-236).

    This guard's own history is exactly the point: at V1.4-B it asserted `frontend` did not exist, which
    was true then and became false, on the owner's own explicit direction, at V1.5-A — a decision
    (V1.5's own commits), not a violation. `frontend` was removed from the forbidden list below for that
    reason, once (V1.6, D-236); it must not quietly grow further. Docker, Kubernetes, a separate worker
    service and Qdrant remain genuinely unbuilt as this is written, so those checks are unchanged and
    stay meaningful: this test's job was never "the repository looks like V1.4-B forever", it is "nothing
    got built before the owner decided it should be" — checked against what is *currently* decided, not
    frozen at V1.4-B's finish line.
    """
    for name in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "render.yaml", "package.json", "next.config.js", "Procfile"):
        assert not (ROOT / name).exists(), name
    for directory in ("web", "k8s", "kubernetes", "deploy", "worker"):
        assert not (ROOT / directory).exists() and not (SRC / directory).exists(), directory
    assert not any("qdrant" in p.read_text(encoding="utf-8").lower() for p in SRC.rglob("*.py"))


def test_the_one_approved_exception_to_the_above_is_frontend_and_nothing_else_snuck_in_beside_it():
    """Pins the V1.6/D-236 change itself: `frontend` is a real, owner-approved directory (V1.5), and it is
    the *only* thing this suite now treats differently from a fresh V1.4-B checkout. If Docker work lands
    (the rest of V1.6, not yet started) it earns its own decision and its own update here — this test is
    not an invitation to quietly widen the exception list."""
    assert (ROOT / "frontend").is_dir()
    assert (ROOT / "frontend" / "src" / "app" / "page.tsx").is_file()  # it is the real frontend, not an empty placeholder directory
    for name in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "render.yaml"):
        assert not (ROOT / name).exists(), f"{name} exists but V1.6's Docker work has not been approved as built yet"


def test_there_are_exactly_three_new_packages_and_no_worker_or_frontend_module():
    assert sorted(p.name for p in SRC.iterdir() if p.is_dir() and p.name != "__pycache__" and p.name in {"api", "service", "persistence", "worker", "frontend", "web", "deploy"}) == ["api", "persistence", "service"]


# --- the migrations ---------------------------------------------------------------------------------------------------------------------------


MIGRATIONS = sorted((PERSISTENCE / "migrations").glob("*.sql"))


def test_migrations_are_plain_sql_numbered_without_a_gap_and_shipped_with_the_package():
    assert MIGRATIONS and [m.name[:4] for m in MIGRATIONS] == [f"{n:04d}" for n in range(1, len(MIGRATIONS) + 1)]
    assert all(re.fullmatch(r"\d{4}_[a-z0-9_]+\.sql", m.name) for m in MIGRATIONS)
    assert pyproject()["tool"]["setuptools"]["package-data"]["eidos.persistence"] == ["migrations/*.sql"]


@pytest.mark.parametrize("migration", MIGRATIONS, ids=lambda m: m.name)
def test_every_table_a_migration_creates_has_row_level_security_and_no_policy_so_the_api_roles_are_denied(migration):
    sql = migration.read_text(encoding="utf-8").lower()
    created = re.findall(r"create table (?:if not exists )?(eidos\.\w+)", sql)
    assert created
    for table in created:
        assert f"alter table {table} enable row level security" in sql, table
    assert "create policy" not in sql  # RLS with no policy is deny-all for the roles it applies to
    assert "revoke all on schema eidos" in sql and "anon" in sql and "authenticated" in sql and "service_role" in sql
    assert "disable row level security" not in sql and "grant " not in sql


@pytest.mark.parametrize("migration", MIGRATIONS, ids=lambda m: m.name)
def test_a_migration_never_holds_a_mission_state_a_status_the_reducer_folds_or_a_secret(migration):
    sql = migration.read_text(encoding="utf-8").lower()
    assert not re.search(r"\b(mission_state|state_version|mission_status|execution_record|confidence|score)\b", sql)
    assert not re.search(r"(password|secret|api_key|token)\b", re.sub(r"--.*", "", sql))
    assert "drop table" not in sql and "truncate" not in sql and "delete from" not in sql  # a migration is history and never destroys data


def test_the_reserved_nil_tenant_is_refused_by_the_schema_as_well_as_by_the_code():
    sql = (PERSISTENCE / "migrations" / "0001_init.sql").read_text(encoding="utf-8")
    assert "tenant_id <> '00000000-0000-0000-0000-000000000000'" in sql


def _sql_statements(path: Path) -> list[str]:
    """The literal text of every SQL string handed to ``execute`` (an f-string keeps its literal parts and drops its placeholders)."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "execute" and node.args:
            argument = node.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                found.append(argument.value)
            elif isinstance(argument, ast.JoinedStr):
                found.append("".join(part.value for part in argument.values if isinstance(part, ast.Constant)))
    return found


def test_every_query_on_a_tenant_owned_table_in_the_postgres_adapter_names_its_tenant():
    """A statement on ``missions``, ``mission_events`` or ``artifacts`` carries the tenant in its predicate or its row, so a missing filter cannot go unnoticed (D-233).

    The one exception is startup recovery, which marks every tenant's orphaned runs interrupted and is not reachable from a request.
    """
    statements = _sql_statements(PERSISTENCE / "postgres.py")
    owned = [sql for sql in statements if re.search(r"eidos\.(missions|mission_events|artifacts)", sql)]
    assert len(owned) >= 8
    for sql in owned:
        if "set run_status = 'interrupted'" in sql:
            assert "where run_status in ('queued', 'running')" in sql
            continue
        assert "tenant_id" in sql, sql
        if sql.lstrip().lower().startswith(("select", "update", "delete")):
            assert "tenant_id = %s" in sql, sql  # a read or an update is filtered by the tenant, not merely mentioning it


def test_the_postgres_adapter_never_builds_sql_from_a_value():
    """Every value reaches the database as a bound parameter; the only text interpolated into a statement is a fixed column list."""
    source = (PERSISTENCE / "postgres.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "execute" and node.args and isinstance(node.args[0], ast.JoinedStr):
            placeholders = [part.value.id for part in node.args[0].values if isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Name)]
            assert set(placeholders) <= {"_MISSION_COLUMNS", "_ARTIFACT_COLUMNS"}, placeholders
            assert all(isinstance(part, ast.Constant) or isinstance(part.value, ast.Name) for part in node.args[0].values)
    assert "% (" not in source and ".format(" not in source


def test_the_carrier_state_is_built_by_one_function_that_folds_one_created_event_and_nothing_else_in_spec_py_accepts():
    tree = ast.parse((SERVICE / "spec.py").read_text(encoding="utf-8"))
    accepting = [
        function.name for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef) and any(isinstance(n, ast.Attribute) and n.attr == "accept" for n in ast.walk(function))
    ]
    assert accepting == ["initial_state"]


@pytest.mark.parametrize("package", [API, SERVICE, PERSISTENCE], ids=lambda p: p.name)
def test_no_new_package_imports_the_knowledge_package(package):
    for path in modules(package):
        assert "knowledge" not in eidos_targets(path), path.name


# --- no credential in the repository -----------------------------------------------------------------------------------------------------------


_SKIP_DIRECTORIES = {".git", "__pycache__", ".venv", "venv", "env", ".pytest_cache", "node_modules", ".ruff_cache", "eidos.egg-info"}
_SECRET_SHAPES = {
    "a private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "a JWT (three base64url segments)": re.compile(r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}"),
    "an AWS access key id": re.compile(r"AKIA[0-9A-Z]{16}"),
    "an API secret key (sk-...)": re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    "a GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "a Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    "a Supabase project host": re.compile(r"\b[a-z0-9]{20}\.supabase\.(?:co|com)\b"),
}
_URL_WITH_PASSWORD = re.compile(r"(?:postgres(?:ql)?|mysql|redis|mongodb)://[^:/@\s\"']+:([^@\s\"']+)@")
_CANARIES = ("hunter2", "{PASSWORD}", "{secret}")  # deliberate fake values that tests plant to prove a secret is never echoed

# The one deliberately committed, secret-free environment template (V1.5-A): frontend/.gitignore carries
# its own named exception for it (`.env*` then `!.env.local.example`), and it is real product
# documentation, not a commit risk. Every other `.env*`/key/cert file these guards find is exactly what
# it looks like. Grow this set only for another reviewed, genuinely secret-free template — never to quiet
# a real failure (D-236).
_ALLOWED_ENV_FILES = frozenset({"frontend/.env.local.example"})


def _committable_files() -> list[Path]:
    """Every file git would track, or would itself offer to add — the same universe `git status`/`git add .`
    show, including every nested ``.gitignore`` (``frontend/.gitignore``'s own rules for `node_modules`,
    `.next/`, `.env*` and its one named exception all apply automatically, exactly as they would for a
    real `git add`).

    Deliberately not a raw filesystem walk (D-236): a build artifact, a lock file a running dev server
    holds open, or a file `.gitignore` already excludes (`frontend/.env.local`, in particular — real on a
    developer's disk, and never a commit risk) is not "in the repository" in the sense either guard below
    actually cares about. Scanning the raw filesystem instead only made these guards fragile against
    whatever a machine happens to be doing (a locked build-tool file could fail the whole suite) without
    making them any more protective — a secret that is genuinely at risk of being committed is, by
    definition, something `git status` would already show.
    """
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT, capture_output=True, check=True, text=True,
    ).stdout
    return [ROOT / name for name in output.split("\0") if name]


def _repository_files():
    for path in sorted(_committable_files()):
        if path.is_file() and not (set(path.relative_to(ROOT).parts) & _SKIP_DIRECTORIES) and path.suffix in {".py", ".md", ".toml", ".sql", ".txt", ".cfg", ".ini", ".yml", ".yaml", ".json", ".env", ".example", ""}:
            yield path


def test_no_credential_key_token_or_password_url_is_committed():
    """The audit's secrets scan, kept: no private key block, JWT, cloud or platform token, Supabase project host or connection string with a password anywhere in the tree (tests plant a few deliberate fake
    canary values to prove a secret is never echoed; those are the only allowed exceptions)."""
    found = []
    for path in _repository_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in _SECRET_SHAPES.items():
            if pattern.search(text):
                found.append(f"{path.relative_to(ROOT)}: {label}")
        for match in _URL_WITH_PASSWORD.finditer(text):
            if not any(canary in match.group(0) for canary in _CANARIES):
                found.append(f"{path.relative_to(ROOT)}: a connection string with a password")
    assert found == []


def test_no_environment_or_key_file_is_in_the_tree_and_the_ignore_file_keeps_it_that_way():
    """No real ``.env``/key/cert file is committed or committable (D-236: over ``_committable_files()``, so
    a gitignored local file like ``frontend/.env.local`` — real on a developer's disk, never a commit
    risk — correctly never appears here at all, exactly as it never would in ``git status``). The one
    deliberate exception is ``frontend/.env.local.example`` (``_ALLOWED_ENV_FILES``): a real, secret-free,
    intentionally tracked template that ``frontend/.gitignore`` itself names as an exception to its own
    broad ``.env*`` rule (V1.5-A) — and which the secrets-content scan above still checks like any other
    committed file.
    """
    risky = {}
    for path in _committable_files():
        if not path.is_file() or (set(path.relative_to(ROOT).parts) & _SKIP_DIRECTORIES):
            continue
        relative = str(path.relative_to(ROOT)).replace("\\", "/")
        if relative in _ALLOWED_ENV_FILES:
            continue
        name = path.name
        if name == ".env" or name.startswith(".env.") or name.endswith((".pem", ".key", ".p12", ".pfx")):
            risky[relative] = name
    assert not risky, risky
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {".env", ".env.*", "*.pem", "*.key"} <= {line.strip() for line in ignored}


def test_the_one_allowed_env_template_is_named_explicitly_tracked_and_itself_holds_no_secret():
    """Regression coverage for the D-236 exception itself: it names exactly one file, that file is real and
    genuinely tracked by git (not merely believed to exist), and — independently of the suffix-based scan
    above, which does cover it — its content holds no real secret shape. Growing ``_ALLOWED_ENV_FILES``
    without this holding is exactly the loophole D-236 must not reopen."""
    assert _ALLOWED_ENV_FILES == {"frontend/.env.local.example"}
    template = ROOT / "frontend" / ".env.local.example"
    assert template.is_file()
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "frontend/.env.local.example"], cwd=ROOT, capture_output=True, text=True)
    assert tracked.returncode == 0, "the allowed template must actually be tracked by git, not just present on disk"
    text = template.read_text(encoding="utf-8")
    for label, pattern in _SECRET_SHAPES.items():
        assert not pattern.search(text), label
    assert not _URL_WITH_PASSWORD.search(text)


def test_the_production_source_holds_no_literal_secret_and_reads_its_configuration_from_the_environment_only():
    literal = re.compile(r"(?i)(password|passwd|secret|api_key|apikey|token)\s*=\s*[\"'][^\"']{6,}[\"']")
    for package in (API, SERVICE, PERSISTENCE):
        for path in modules(package):
            assert not literal.search(path.read_text(encoding="utf-8")), path.relative_to(SRC)
    assert "environ" in (API / "main.py").read_text(encoding="utf-8")  # the one place configuration enters, and only by name
