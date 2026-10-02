"""PostgreSQL persistence for the V1.4 product backend (decisions.md D-230, D-233; ``docs/13_product_backend.md`` section 2).

Adapters for the ports ``eidos.service`` defines, and the plain-SQL migrations. **It stores the event stream and what the run's artifacts hold; it stores no ``MissionState``, no
``ExecutionRecord`` and no folded status.** The event log stays the authority (D-157) and a reader replays it. This is the only package that imports psycopg; it is imported by no core layer
and by no service module, and the one composition module in ``eidos.api`` wires it to the service.

    storage = PostgresStorage.open(connection_string)
    repositories = storage.repositories()
"""

from typing import TYPE_CHECKING, Any

from .postgres import PostgresArtifacts, PostgresStorage

if TYPE_CHECKING:
    from .migrate import apply_migrations, available

__all__ = ["PostgresArtifacts", "PostgresStorage", "apply_migrations", "available"]

_MIGRATE_NAMES = frozenset({"apply_migrations", "available"})


def __getattr__(name: str) -> Any:
    """Resolve the two migration names on first use: importing ``.migrate`` eagerly here made ``python -m eidos.persistence.migrate`` find the module already in ``sys.modules`` and warn."""
    if name in _MIGRATE_NAMES:
        from . import migrate

        return getattr(migrate, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
