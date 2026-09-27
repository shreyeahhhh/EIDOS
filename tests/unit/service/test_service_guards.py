"""Static guards on the product backend's boundaries (decisions.md D-229 to D-234; invariants 1, 2 and 9; ``CLAUDE.md`` section 8; V1.4-B).

Three new packages and one direction of dependency: ``eidos.api`` (HTTP) calls ``eidos.service`` (use cases) which runs the unchanged core, and ``eidos.persistence`` (PostgreSQL) implements the
service's ports. New libraries stay behind their one boundary, the core imports none of the three, FastAPI never touches the log or the reducer, there is no ORM, and the migrations deny every API
role by construction.
"""

import ast
import re
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
            assert node.name in {"lifespan", "raw_body", "_service_error", "_unauthenticated", "_auth_unavailable", "_bad_request", "_unexpected"}, node.name
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
    """No Next.js, Docker, Render, Kubernetes, separate worker service or Qdrant was added in V1.4-B (the owner's approved scope)."""
    for name in ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "render.yaml", "package.json", "next.config.js", "Procfile"):
        assert not (ROOT / name).exists(), name
    for directory in ("frontend", "web", "k8s", "kubernetes", "deploy", "worker"):
        assert not (ROOT / directory).exists() and not (SRC / directory).exists(), directory
    assert not any("qdrant" in p.read_text(encoding="utf-8").lower() for p in SRC.rglob("*.py"))


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
