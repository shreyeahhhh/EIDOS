"""``EventRecord``: one V0.1 ``MissionEvent`` envelope and the one typed payload its ``type`` selects (decisions.md D-153).

The envelope is unchanged and still has no payload field (D-067). A record is constructible only if its payload is the class for the
envelope's type, so a mismatch is refused at construction, and an event type with no payload class (the seven V0.5 does not emit) cannot form
a record at all. A record is also refused when its payload names another tenant or mission than its envelope does: the log holds one
mission's events, and nothing that disagrees about identity gets in.

Records serialize strictly: ``model_dump_json`` and ``model_validate_json`` round-trip to an equal record, and the discriminator makes a
payload of the wrong shape a validation error rather than a guess.
"""

from typing import Annotated

from pydantic import Field, model_validator

from eidos.contracts import EidosModel, MissionEvent

from .payloads import (
    EmittedPayload,
    MissionCreatedPayload,
    PlanGeneratedPayload,
)

Payload = Annotated[EmittedPayload, Field(discriminator="event_type")]


class EventRecord(EidosModel):
    event: MissionEvent
    payload: Payload

    @model_validator(mode="after")
    def _check_the_payload_is_the_one_for_the_type(self) -> "EventRecord":
        if self.payload.event_type is not self.event.type:
            raise ValueError(
                f"the payload is for {self.payload.event_type.value}, but the event is {self.event.type.value}"
            )
        return self

    @model_validator(mode="after")
    def _check_the_payload_names_the_envelope_tenant_and_mission(self) -> "EventRecord":
        payload, event = self.payload, self.event
        if isinstance(payload, MissionCreatedPayload):
            if payload.task_genome.tenant_id != event.tenant_id:
                raise ValueError("the task genome's tenant is not the event's tenant")
            if payload.reliability_contract.tenant_id != event.tenant_id:
                raise ValueError("the reliability contract's tenant is not the event's tenant")
        elif isinstance(payload, PlanGeneratedPayload):
            if payload.plan.tenant_id != event.tenant_id:
                raise ValueError("the plan's tenant is not the event's tenant")
            if payload.plan.mission_id != event.mission_id:
                raise ValueError("the plan's mission is not the event's mission")
        return self
