"""The agent descriptor and the capability registry (decisions.md D-134, D-144).

An agent is described by exactly three things — ``agent_id``, a version and the capabilities it serves. The rest of
§7's metadata (supported inputs and outputs, permissions, tools, historical statistics, availability) is not built:
the statistics belong to telemetry (V0.9), the rest to V0.6, V0.7 and V1.2.

``agent_id`` is a fixed, UUID-backed value supplied by whoever registers the agent (D-053): nothing here generates
one, so nothing here is random.

The registry resolves a capability to the one agent that serves it, deterministically and by exact string. It is an
immutable value; its result never depends on the order agents were listed in. Registering is refused, not repaired,
when it would be ambiguous or would go outside the V0.4 vocabulary:

- two agents may not share an ``agent_id``;
- a capability outside the V0.4 set may not be served (the set is closed at V0.4, D-132);
- one capability is served by **one** agent (so a resolution is never a choice).
"""

from pydantic import Field, model_validator

from eidos.contracts import AgentId, CapabilityId, EidosModel

from .vocabulary import V04_CAPABILITIES


class AgentDescriptor(EidosModel):
    agent_id: AgentId
    version: str = Field(min_length=1)
    capabilities: tuple[CapabilityId, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_capabilities_are_distinct(self) -> "AgentDescriptor":
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("an agent lists each capability at most once")
        return self


class CapabilityRegistry(EidosModel):
    agents: tuple[AgentDescriptor, ...]

    @model_validator(mode="after")
    def _check_registrations_are_unambiguous(self) -> "CapabilityRegistry":
        seen_agents: dict[AgentId, None] = {}  # membership only
        served_by: dict[CapabilityId, AgentId] = {}  # lookup only, never iterated
        for agent in self.agents:
            if agent.agent_id in seen_agents:
                raise ValueError(f"agent_id {str(agent.agent_id)!r} is registered twice")
            seen_agents[agent.agent_id] = None
            for capability in agent.capabilities:
                if capability not in V04_CAPABILITIES:
                    raise ValueError(f"capability {capability!r} is not in the V0.4 vocabulary")
                if capability in served_by:
                    raise ValueError(f"capability {capability!r} would be served by two agents")
                served_by[capability] = agent.agent_id
        return self

    def resolve(self, capability: CapabilityId) -> AgentId | None:
        """The agent serving ``capability`` (exact string), or ``None`` — never a guess, never the nearest match."""
        for agent in self.agents:
            if capability in agent.capabilities:
                return agent.agent_id
        return None
