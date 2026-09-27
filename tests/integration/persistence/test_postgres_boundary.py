"""What the PostgreSQL adapter and the migration runner do when there is no database (decisions.md D-230; V1.4-B). These run in the default suite: they need the driver, never a server."""

import pytest

from eidos.persistence import PostgresStorage, available
from eidos.persistence import migrate
from eidos.service import StorageError

PASSWORD = "password-that-must-never-be-echoed-0123456789"


def test_an_unreachable_database_is_a_storage_error_that_names_neither_the_host_nor_the_password():
    with pytest.raises(StorageError) as raised:
        PostgresStorage.open(f"postgresql://someone:{PASSWORD}@127.0.0.1:1/postgres", connect_timeout_seconds=1)
    assert PASSWORD not in str(raised.value) and "127.0.0.1" not in str(raised.value) and "someone" not in str(raised.value)


def test_the_migration_runner_needs_the_variable_names_it_and_never_prints_a_connection_string(monkeypatch, capsys):
    monkeypatch.delenv("EIDOS_DATABASE_URL", raising=False)
    assert migrate.main() == 2
    captured = capsys.readouterr()
    assert "EIDOS_DATABASE_URL" in captured.err and captured.out == ""


def test_the_shipped_migrations_are_readable_as_package_data_in_order():
    found = available()
    assert [version for version, _ in found] == sorted(version for version, _ in found) and found[0][0] == "0001_init"
    assert "create table eidos.missions" in found[0][1]
