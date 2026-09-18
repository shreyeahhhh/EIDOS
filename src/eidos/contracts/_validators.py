"""Shared field-level validation helpers for EIDOS V0.1 contracts.

decisions.md D-083: all timestamps are explicit timezone-aware UTC datetime
values; naive timestamps are rejected. Pydantic's strict mode (see _base.py)
already rejects anything that is not an actual ``datetime.datetime``
instance, but it does not by itself reject a naive one — that check is
added here.

This module performs validation only. It does not normalize, convert, or
otherwise transform a value (CLAUDE.md A6: "Do not add unrelated
normalization/transformation behavior") — a non-UTC aware datetime is
rejected, never silently converted to UTC.
"""

from datetime import datetime, timedelta
from typing import Annotated

from pydantic import AfterValidator


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError(
            "timestamp must be timezone-aware; naive datetimes are rejected "
            "(decisions.md D-083)"
        )
    if value.utcoffset() != timedelta(0):
        raise ValueError(
            "timestamp must be in UTC (offset zero); got offset "
            f"{value.utcoffset()!r} (decisions.md D-083)"
        )
    return value


UtcDateTime = Annotated[datetime, AfterValidator(_require_utc)]
