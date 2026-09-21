"""MissionEvent — handoff §10, §33.

decisions.md: D-011 (event_id is the idempotency key; sequence is a
monotonic per-mission sequence assigned by EIDOS at acceptance, starting
at 1 — D-097; no A2A-specific producer ordering in V0.1), D-067 (V0.1 is
the envelope only — no payload field; a typed discriminated payload keyed
by event type is the intended future direction, not built here), D-077
(every envelope field is required), D-079 (tenant_id default), D-083
(timezone-aware UTC; naive rejected), D-086 (occurred_at is required and
represents the domain occurrence time — the producer's timestamp for
externally produced events, or equal to recorded_at for EIDOS-internal
events, set by the caller at acceptance; this model does not enforce that
equality itself, since V0.1 has no internal/external event classification
— that split is D-037, still Open), D-090 (type is exactly one of the
thirteen §33 event types, plus the three local-execution types D-154 adds — sixteen).
"""

from pydantic import Field

from ._base import EidosModel
from ._validators import UtcDateTime
from .enums import MissionEventType
from .identifiers import DEFAULT_TENANT_ID, EventId, MissionId, TenantId


class MissionEvent(EidosModel):
    event_id: EventId
    tenant_id: TenantId = Field(default=DEFAULT_TENANT_ID)
    mission_id: MissionId
    sequence: int = Field(ge=1)
    occurred_at: UtcDateTime
    recorded_at: UtcDateTime
    type: MissionEventType
