"""The product backend on a real PostgreSQL (decisions.md D-230, D-233; V1.4-B). Selected only with ``-m postgres`` and ``EIDOS_TEST_DATABASE_URL`` (a disposable database: the fixture drops and
recreates the ``eidos`` schema); the default suite never runs it and a selected test never skips.

What is held on the real database: the migrations apply once and in order; row level security is on for every table with no policy and the API roles hold nothing; the schema itself refuses a
row that names another tenant's mission; a whole mission runs over it and a second connection pool (a restart) reads identical answers; and two processes racing to start one mission run it once.
"""

import threading
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import errors as pg_errors

import eidos_postgres_fixture as pg
from eidos.contracts import MissionStatus
from eidos.persistence import apply_migrations, available
from eidos.service import (
    Composition,
    MissionService,
    NotStartable,
    RunManager,
    Role,
    RunStatus,
    TenantRunLimit,
)
from eidos.state import replay

from eidos_service_fixture import ALICE, BOB, TENANT_A, TENANT_B, make_rig, make_spec
from eidos_storage_helpers import NOW, artifact, commit, events_for, make_record

pytestmark = pytest.mark.postgres


@pytest.fixture
def url():
    return pg.reset_schema()


@pytest.fixture
def storage(url):
    opened = pg.open_storage(url)
    yield opened
    opened.close()


def service_over(storage, rig):
    """A second, independent service (its own runner and live set) over another connection pool: what a second process is."""
    repositories = storage.repositories()
    composition = Composition(config=rig.config, model=rig.model, events=repositories.events, sleep=lambda seconds: None)
    runner = RunManager(repositories=repositories, composition=composition, config=rig.config.runner)
    return MissionService(repositories=repositories, runner=runner, composition=composition, config=rig.config), runner


# --- migrations ------------------------------------------------------------------------------------------------------------------------


def test_the_migrations_are_applied_once_in_order_and_a_second_run_applies_nothing(url):
    with psycopg.connect(url) as connection:
        recorded = [row[0] for row in connection.execute("select version from eidos.schema_migrations order by version").fetchall()]
    assert recorded == [version for version, _ in available()]
    assert apply_migrations(url) == []  # up to date
    with psycopg.connect(url) as connection:
        assert [row[0] for row in connection.execute("select version from eidos.schema_migrations order by version").fetchall()] == recorded


def test_two_appliers_at_once_apply_each_migration_exactly_once(url):
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("drop schema eidos cascade")
    results, errors, start = [], [], threading.Barrier(2, timeout=30)

    def apply():
        start.wait()
        try:
            results.append(apply_migrations(url))
        except BaseException as error:  # noqa: BLE001 - a failure in a thread must fail this test, not be swallowed as a warning
            errors.append(error)

    threads = [threading.Thread(target=apply) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    versions = [version for version, _ in available()]
    assert errors == []
    assert sorted(sum(results, [])) == versions  # between them, each exactly once
    with psycopg.connect(url) as connection:
        assert connection.execute("select count(*) from eidos.schema_migrations").fetchone()[0] == len(versions)


# --- deny-all row level security --------------------------------------------------------------------------------------------------------


def test_every_table_has_row_level_security_and_no_policy(url):
    with psycopg.connect(url) as connection:
        tables = connection.execute(
            "select c.relname, c.relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'eidos' and c.relkind = 'r' order by c.relname"
        ).fetchall()
        policies = connection.execute("select count(*) from pg_policies where schemaname = 'eidos'").fetchone()[0]
    assert {name for name, _ in tables} == {"artifacts", "mission_events", "missions", "schema_migrations", "tenant_members", "tenants"}
    assert all(secured for _, secured in tables) and policies == 0


def test_the_api_roles_hold_no_privilege_on_the_schema_and_are_denied_by_the_database_itself(url):
    roles = ("anon", "authenticated", "service_role")
    created = []
    with psycopg.connect(url, autocommit=True) as connection:
        for role in roles:
            if connection.execute("select 1 from pg_roles where rolname = %s", (role,)).fetchone() is None:
                connection.execute(f'create role "{role}" nologin')
                created.append(role)
        connection.execute("drop schema eidos cascade")
    try:
        apply_migrations(url)  # the migration revokes from whichever of the roles exist
        with psycopg.connect(url, autocommit=True) as connection:
            for role in roles:
                assert not connection.execute("select has_schema_privilege(%s, 'eidos', 'usage')", (role,)).fetchone()[0], role
                for table in ("missions", "mission_events", "artifacts", "tenants", "tenant_members"):
                    for privilege in ("select", "insert", "update", "delete"):
                        assert not connection.execute("select has_table_privilege(%s, %s, %s)", (role, f"eidos.{table}", privilege)).fetchone()[0], (role, table, privilege)
            for role in ("anon", "authenticated"):
                connection.execute(f'set role "{role}"')
                with pytest.raises(pg_errors.InsufficientPrivilege):
                    connection.execute("select * from eidos.missions")
                connection.execute("reset role")
    finally:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute("reset role")
            for role in created:
                connection.execute(f'drop owned by "{role}"')
                connection.execute(f'drop role "{role}"')


# --- the schema refuses what the code must never do --------------------------------------------------------------------------------------------


def test_the_schema_refuses_an_event_or_an_artifact_that_names_another_tenants_mission(storage):
    storage.add_tenant(TENANT_A, "a")
    storage.add_tenant(TENANT_B, "b")
    record = make_record(TENANT_A)
    storage.create(record, ())
    (event,) = events_for(record, 1)
    with storage._transaction() as connection:
        with pytest.raises(pg_errors.ForeignKeyViolation):
            connection.execute(
                "insert into eidos.mission_events (mission_id, tenant_id, sequence, event_id, event_type, occurred_at, record) values (%s, %s, 1, %s, 'MISSION_CREATED', now(), '{}'::jsonb)",
                (record.mission_id, TENANT_B, uuid4()),  # the right mission, the wrong tenant
            )
    with storage._transaction() as connection:
        with pytest.raises(pg_errors.ForeignKeyViolation):
            connection.execute(
                "insert into eidos.artifacts (execution_id, tenant_id, ref, kind, content_type, content) values (%s, %s, 'doc:x', 'supplied', 'text/plain', 'c')", (record.execution_id, TENANT_B)
            )
    assert storage.read(TENANT_A, record.mission_id) == () and event is not None


@pytest.mark.parametrize(
    "statement",
    [
        "insert into eidos.tenants (tenant_id, name) values ('00000000-0000-0000-0000-000000000000', 'nil')",
        "insert into eidos.tenants (tenant_id, name) values (gen_random_uuid(), '')",
        "insert into eidos.tenant_members (tenant_id, user_id, role) values ('{tenant}', gen_random_uuid(), 'admin')",
        "update eidos.missions set run_status = 'paused'",
        "update eidos.missions set last_sequence = -1",
    ],
    ids=["nil-tenant", "empty-name", "unknown-role", "unknown-run-status", "negative-sequence"],
)
def test_the_schema_holds_its_own_invariants_whatever_the_code_does(storage, statement):
    storage.add_tenant(TENANT_A, "a")
    storage.create(make_record(TENANT_A), ())
    with storage._transaction() as connection:
        with pytest.raises(pg_errors.CheckViolation):
            connection.execute(statement.format(tenant=TENANT_A))


def test_a_second_primary_artifact_for_a_step_is_refused_by_the_schema(storage):
    from eidos.contracts import ArtifactRef, StepId
    from eidos.service import ArtifactWrite

    storage.add_tenant(TENANT_A, "a")
    record = make_record(TENANT_A)
    storage.create(record, ())
    one = ArtifactWrite(artifact=artifact("artifact:one", "a"), kind="step", step_id=StepId("s1"))
    two = ArtifactWrite(artifact=artifact("artifact:two", "b"), kind="step", step_id=StepId("s1"))
    commit(storage.repositories(), record, (), expected=0, artifacts=(one,))
    with storage._transaction() as connection:
        with pytest.raises(pg_errors.UniqueViolation):
            connection.execute(
                "insert into eidos.artifacts (execution_id, tenant_id, ref, kind, step_id, content_type, content) values (%s, %s, %s, 'step', 's1', 'text/plain', 'b')",
                (record.execution_id, TENANT_A, str(ArtifactRef("artifact:two"))),
            )
    assert two.artifact.ref == ArtifactRef("artifact:two")


# --- a whole mission on the real database ------------------------------------------------------------------------------------------------------


def test_a_whole_mission_runs_over_postgres_and_a_second_pool_answers_every_read_identically(storage, url):
    rig = make_rig(storage=storage)
    context = rig.context("alice")
    mission_id = rig.service.create_mission(context, make_spec())[0].mission_id
    summary = rig.run_to_the_end(context, mission_id)
    assert (summary.run_status, summary.mission_status, summary.verified) == (RunStatus.FINISHED, MissionStatus.COMPLETED, True)
    records = storage.read(TENANT_A, mission_id)
    assert len(records) == summary.last_sequence > 6 and replay(records).rejection is None and replay(records).state.status is MissionStatus.COMPLETED
    with psycopg.connect(url) as connection:  # what is in the tables is the events and the artifacts, and no folded state
        assert connection.execute("select count(*) from eidos.mission_events where mission_id = %s", (mission_id,)).fetchone()[0] == len(records)
        assert connection.execute("select last_sequence from eidos.missions where mission_id = %s", (mission_id,)).fetchone()[0] == len(records)
        assert connection.execute("select count(*) from eidos.artifacts where kind = 'supplied' and execution_id = %s", (rig.storage.get(TENANT_A, mission_id).execution_id,)).fetchone()[0] == 3
    other = pg.open_storage(url)
    try:
        restarted, runner = service_over(other, rig)
        assert restarted.startup() == 0
        for read in ("get_mission", "execution", "events", "result", "evidence"):
            assert getattr(restarted, read)(context, mission_id) == getattr(rig.service, read)(context, mission_id), read
        runner.shutdown()
    finally:
        other.close()


def test_a_run_a_previous_process_left_active_is_interrupted_at_startup_and_its_events_are_kept(storage, url):
    rig = make_rig(storage=storage)
    context = rig.context("alice")
    mission_id = rig.service.create_mission(context, make_spec())[0].mission_id
    record = storage.get(TENANT_A, mission_id)
    complete = events_for(record, 3)
    commit(storage.repositories(), record, complete, expected=0)
    assert storage.transition(TENANT_A, mission_id, expected=(RunStatus.CREATED,), new=RunStatus.RUNNING, reason=None, at=NOW)  # the process died here
    other = pg.open_storage(url)
    try:
        restarted, runner = service_over(other, rig)
        assert restarted.startup() == 1
        summary = restarted.get_mission(context, mission_id)
        assert summary.run_status is RunStatus.INTERRUPTED and summary.last_sequence == 3 and summary.mission_status is MissionStatus.CREATED
        assert other.read(TENANT_A, mission_id) == complete
        with pytest.raises(NotStartable):
            restarted.start_mission(context, mission_id)
        runner.shutdown()
    finally:
        other.close()


def test_two_processes_racing_to_start_one_mission_run_it_once(storage, url):
    rig = make_rig(storage=storage)
    context = rig.context("alice")
    mission_id = rig.service.create_mission(context, make_spec())[0].mission_id
    other = pg.open_storage(url)
    try:
        second, second_runner = service_over(other, rig)
        outcomes, start = [], threading.Barrier(2, timeout=30)

        def race(service):
            start.wait()
            try:
                service.start_mission(context, mission_id)
                outcomes.append("started")
            except (NotStartable, TenantRunLimit) as error:
                outcomes.append(error.code)

        threads = [threading.Thread(target=race, args=(service,)) for service in (rig.service, second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        assert rig.runner.wait_idle(60) and second_runner.wait_idle(60)
        assert outcomes.count("started") == 1 and len(outcomes) == 2
        records = storage.read(TENANT_A, mission_id)
        assert [r.event.sequence for r in records] == list(range(1, len(records) + 1))  # one contiguous log: nobody interleaved
        assert rig.model.calls > 0
        second_runner.shutdown()
    finally:
        other.close()


def test_the_other_tenants_cannot_see_a_mission_on_the_real_database_either(storage):
    rig = make_rig(storage=storage)
    alice, bob = rig.context("alice"), rig.context("bob")
    mission_id = rig.service.create_mission(alice, make_spec())[0].mission_id
    rig.run_to_the_end(alice, mission_id)
    from eidos.service import NotFound

    for read in (rig.service.get_mission, rig.service.execution, rig.service.events, rig.service.result, rig.service.evidence, rig.service.start_mission):
        with pytest.raises(NotFound):
            read(bob, mission_id)
    assert storage.read(TENANT_B, mission_id) == () and storage.artifacts_for(TENANT_B).supplied(storage.get(TENANT_A, mission_id).execution_id) == ()
    assert {m.role for m in storage.repositories().tenancy.memberships_of(ALICE)} == {Role.OWNER} and BOB != ALICE and UUID(int=0) != TENANT_A
