"""Support for the PostgreSQL tests (decisions.md D-230; V1.4-B). They run only when selected with ``-m postgres`` and need a real, disposable database at ``EIDOS_TEST_DATABASE_URL``.

The default suite never touches a database and needs no credential. A selected PostgreSQL test never skips: without the variable it fails, naming it. Point the variable at a database that
holds nothing you want: the fixture drops and recreates the ``eidos`` schema. Never point it at a real project.
"""

import os

import psycopg

from eidos.persistence import PostgresStorage, apply_migrations

_TABLES = "eidos.artifacts, eidos.mission_events, eidos.missions, eidos.tenant_members, eidos.tenants"


def database_url() -> str:
    url = os.environ.get("EIDOS_TEST_DATABASE_URL", "").strip()
    assert url, "EIDOS_TEST_DATABASE_URL is not set: a PostgreSQL test needs a disposable database (it drops and recreates the eidos schema); it never skips"
    return url


def reset_schema() -> str:
    url = database_url()
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute("drop schema if exists eidos cascade")
    apply_migrations(url)
    return url


def open_storage(url: str) -> PostgresStorage:
    return PostgresStorage.open(url, max_size=4)


def truncate(storage: PostgresStorage) -> None:
    with storage._transaction() as connection:
        connection.execute(f"truncate {_TABLES} cascade")
