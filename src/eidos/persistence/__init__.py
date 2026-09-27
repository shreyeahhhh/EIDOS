"""PostgreSQL persistence for the V1.4 product backend (decisions.md D-230, D-233; ``docs/13_product_backend.md`` section 2).

Adapters for the ports ``eidos.service`` defines, and the plain-SQL migrations. **It stores the event stream and what the run's artifacts hold; it stores no ``MissionState``, no
``ExecutionRecord`` and no folded status.** The event log stays the authority (D-157) and a reader replays it. This is the only package that imports psycopg; it is imported by no core layer
and by no service module, and the one composition module in ``eidos.api`` wires it to the service.

    storage = PostgresStorage.open(connection_string)
    repositories = storage.repositories()
"""

from .migrate import apply_migrations, available
from .postgres import PostgresArtifacts, PostgresStorage

__all__ = ["PostgresArtifacts", "PostgresStorage", "apply_migrations", "available"]
