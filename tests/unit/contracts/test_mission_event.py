"""MissionEvent (decisions.md D-011, D-067, D-083, D-086, D-090, D-097)."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from eidos.contracts import DEFAULT_TENANT_ID, EventId, MissionEvent, MissionEventType, MissionId

from eidos_factories import make_mission_event, utc_now


def test_valid_construction():
    event = make_mission_event()
    assert event.type == MissionEventType.MISSION_CREATED


def test_tenant_id_defaults_when_omitted():
    event = MissionEvent(
        event_id=EventId(uuid4()),
        mission_id=MissionId(uuid4()),
        sequence=1,
        occurred_at=utc_now(),
        recorded_at=utc_now(),
        type=MissionEventType.MISSION_CREATED,
    )
    assert event.tenant_id == DEFAULT_TENANT_ID


@pytest.mark.parametrize("bad_sequence", [0, -1])
def test_sequence_below_one_is_rejected(bad_sequence):
    # decisions.md D-097: the mission event sequence begins at 1.
    with pytest.raises(ValidationError):
        make_mission_event(sequence=bad_sequence)


def test_sequence_one_is_accepted():
    event = make_mission_event(sequence=1)
    assert event.sequence == 1


def test_naive_occurred_at_is_rejected():
    with pytest.raises(ValidationError, match="D-083"):
        make_mission_event(occurred_at=datetime(2026, 1, 1))


def test_naive_recorded_at_is_rejected():
    with pytest.raises(ValidationError, match="D-083"):
        make_mission_event(recorded_at=datetime(2026, 1, 1))


def test_non_utc_offset_timestamp_is_rejected():
    non_utc = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    with pytest.raises(ValidationError, match="D-083"):
        make_mission_event(occurred_at=non_utc)


def test_utc_timestamp_is_accepted():
    event = make_mission_event(occurred_at=utc_now())
    assert event.occurred_at.tzinfo is not None


def test_occurred_at_may_equal_recorded_at_for_an_internal_event():
    # decisions.md D-086: for EIDOS-internal events, occurred_at is set
    # equal to recorded_at by the caller at acceptance. V0.1 does not
    # enforce this equality itself (no internal/external classification
    # exists yet — D-037), it only requires both to be present and valid.
    now = utc_now()
    event = make_mission_event(occurred_at=now, recorded_at=now)
    assert event.occurred_at == event.recorded_at


def test_occurred_at_may_differ_from_recorded_at_for_an_external_event():
    producer_time = utc_now() - timedelta(seconds=5)
    ingestion_time = utc_now()
    event = make_mission_event(occurred_at=producer_time, recorded_at=ingestion_time)
    assert event.occurred_at != event.recorded_at


def test_missing_occurred_at_is_rejected():
    with pytest.raises(ValidationError):
        make_mission_event(occurred_at=None)


def test_missing_recorded_at_is_rejected():
    with pytest.raises(ValidationError):
        make_mission_event(recorded_at=None)


def test_type_must_be_one_of_the_defined_event_types():
    with pytest.raises(ValidationError):
        make_mission_event(type="SOMETHING_INVENTED")


def test_no_payload_field_exists():
    # decisions.md D-067: V0.1 MissionEvent is the envelope only.
    with pytest.raises(ValidationError):
        make_mission_event(payload={"anything": "at all"})


def test_model_is_immutable():
    event = make_mission_event()
    with pytest.raises(ValidationError):
        event.sequence = 2


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        make_mission_event(unexpected_field=123)
