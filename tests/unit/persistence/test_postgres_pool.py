"""How the PostgreSQL pool is opened (decisions.md D-241).

A pooled connection that the remote end dropped while idle looks open until it is used; the first request then waits for the operating system to give up (about 20 s) and fails 503. These tests pin
the settings that prevent that. They run without a database: the pool class is replaced by one that records how it was built. (What a real dead connection does is psycopg_pool's own tested
behaviour once ``check`` is set; the ``-m postgres`` suite exercises the real pool against a real database.)
"""

import pytest
from psycopg_pool import ConnectionPool

import eidos.persistence.postgres as postgres


class RecordingPool:
    built: list["RecordingPool"] = []
    check_connection = staticmethod(ConnectionPool.check_connection)  # the code under test reads this off whatever class it is given

    def __init__(self, conninfo, **kwargs):
        self.conninfo, self.arguments = conninfo, kwargs
        self.opened = self.closed = False
        RecordingPool.built.append(self)

    def open(self, wait=False, timeout=None):
        self.opened = True

    def close(self):
        self.closed = True


@pytest.fixture
def pool(monkeypatch):
    RecordingPool.built = []
    monkeypatch.setattr(postgres, "ConnectionPool", RecordingPool)
    postgres.PostgresStorage.open("postgresql://user@db.example.com:5432/postgres")
    (built,) = RecordingPool.built
    assert built.opened
    return built


def test_a_connection_is_tested_as_it_is_handed_out_so_a_dead_one_is_replaced_not_used(pool):
    assert pool.arguments["check"] == ConnectionPool.check_connection


def test_idle_connections_are_kept_alive_and_a_send_to_a_dead_peer_is_bounded(pool):
    options = pool.arguments["kwargs"]
    assert (options["keepalives"], options["keepalives_idle"], options["keepalives_interval"], options["keepalives_count"]) == (1, 30, 10, 3)
    assert options["tcp_user_timeout"] == 10_000  # milliseconds: well under the ~20 s a dead socket otherwise costs


def test_the_existing_settings_are_unchanged(pool):
    options = pool.arguments["kwargs"]
    assert options["prepare_threshold"] is None  # no server-side prepared statements: any Supabase connection mode works (D-230)
    assert options["connect_timeout"] == 10
    assert options["options"] == "-c statement_timeout=10000"
    assert (pool.arguments["min_size"], pool.arguments["max_size"]) == (1, 8)
    assert pool.arguments["open"] is False


def test_a_pool_that_cannot_open_is_closed_and_is_a_typed_failure_with_a_fixed_message(monkeypatch):
    from psycopg_pool import PoolTimeout

    from eidos.service import StorageError

    class NeverOpens(RecordingPool):
        def open(self, wait=False, timeout=None):
            raise PoolTimeout("no connection")

    RecordingPool.built = []
    monkeypatch.setattr(postgres, "ConnectionPool", NeverOpens)
    with pytest.raises(StorageError) as caught:
        postgres.PostgresStorage.open("postgresql://user@db.example.com:5432/postgres")
    (built,) = RecordingPool.built
    assert built.closed
    assert str(caught.value) == "the database could not be reached"  # a fixed message: nothing about the connection string reaches it
