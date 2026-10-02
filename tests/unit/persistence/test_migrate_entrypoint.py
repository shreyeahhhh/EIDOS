"""``python -m eidos.persistence.migrate`` is the container's startup step (``Dockerfile``); it must run clean, and the package's public names must still resolve."""

import os
import subprocess
import sys

import eidos.persistence as persistence


def test_the_migration_entry_point_emits_no_runtime_warning():
    environment = {key: value for key, value in os.environ.items() if key != "EIDOS_DATABASE_URL"}
    completed = subprocess.run(
        [sys.executable, "-m", "eidos.persistence.migrate"], env=environment, capture_output=True, text=True, timeout=60, check=False
    )
    assert completed.returncode == 2  # no connection string: it stops before touching any database
    assert "EIDOS_DATABASE_URL is not set" in completed.stderr
    assert "RuntimeWarning" not in completed.stderr


def test_the_migration_names_are_still_public_on_the_package():
    from eidos.persistence import apply_migrations, available
    from eidos.persistence import migrate

    assert apply_migrations is migrate.apply_migrations
    assert available is migrate.available
    assert {"apply_migrations", "available"} <= set(persistence.__all__)


def test_an_unknown_attribute_still_raises_attribute_error():
    assert not hasattr(persistence, "no_such_name")
