"""Plain, versioned SQL migrations (decisions.md D-230; ``docs/13`` section 2.2). No ORM.

The applier runs every ``migrations/NNNN_*.sql`` file whose version is not yet in ``eidos.schema_migrations``, in order, each in its own transaction together with the row that records it.
A transaction-level advisory lock serialises concurrent appliers (a transaction-level lock is released at the transaction's end, so it holds under any Supabase pooler mode). Nothing is
ever rewritten or rolled back: a migration that has been applied is history.

Run it with ``python -m eidos.persistence.migrate``; the connection string is read from ``EIDOS_DATABASE_URL`` and is never logged.
"""

import os
import sys
from importlib import resources

import psycopg

_LOCK_KEY = 8_113_402_651_044_207  # any fixed number: it names "the EIDOS migration applier" for pg_advisory_xact_lock


def available() -> list[tuple[str, str]]:
    """``[(version, sql)]`` in order, from the package's ``migrations`` directory."""
    found = []
    for entry in sorted(resources.files("eidos.persistence").joinpath("migrations").iterdir(), key=lambda e: e.name):
        if entry.name.endswith(".sql"):
            found.append((entry.name[: -len(".sql")], entry.read_text(encoding="utf-8")))
    return found


def apply_migrations(connection_string: str) -> list[str]:
    """Apply every pending migration. Returns the versions applied by this call, in order."""
    applied_now: list[str] = []
    with psycopg.connect(connection_string, prepare_threshold=None) as bootstrap:  # one transaction under the same lock: ``create ... if not exists`` is not safe against a concurrent creator
        bootstrap.execute("select pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
        bootstrap.execute("create schema if not exists eidos")
        bootstrap.execute("create table if not exists eidos.schema_migrations (version text primary key, applied_at timestamptz not null default now())")
    for version, sql in available():
        with psycopg.connect(connection_string, prepare_threshold=None) as connection:  # one transaction: the migration and its record commit together
            connection.execute("select pg_advisory_xact_lock(%s)", (_LOCK_KEY,))
            if connection.execute("select 1 from eidos.schema_migrations where version = %s", (version,)).fetchone() is not None:
                continue
            connection.execute(sql)
            connection.execute("insert into eidos.schema_migrations (version) values (%s)", (version,))
            applied_now.append(version)
    return applied_now


def main() -> int:
    connection_string = os.environ.get("EIDOS_DATABASE_URL")
    if not connection_string:
        print("EIDOS_DATABASE_URL is not set", file=sys.stderr)
        return 2
    applied = apply_migrations(connection_string)
    print("applied: " + (", ".join(applied) if applied else "nothing (up to date)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
