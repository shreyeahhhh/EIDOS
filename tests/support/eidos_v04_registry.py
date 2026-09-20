"""The V0.4 agent identifiers and the registry D-144 rules: Research serves research, Analysis serves the other three.

Pure and backend-free, so unit tests can use it with LangGraph blocked (decisions.md D-116).
"""

from uuid import UUID

from eidos.agents import AnalysisAgent, ResearchAgent
from eidos.capabilities import AgentDescriptor, CapabilityRegistry
from eidos.contracts import AgentId

RESEARCH_AGENT_ID = AgentId(UUID(int=501))
ANALYSIS_AGENT_ID = AgentId(UUID(int=502))


def make_registry() -> CapabilityRegistry:
    """The mapping D-144 rules: Research serves research; Analysis serves architecture, security and cost."""
    return CapabilityRegistry(
        agents=(
            AgentDescriptor(agent_id=RESEARCH_AGENT_ID, version="1", capabilities=ResearchAgent.CAPABILITIES),
            AgentDescriptor(agent_id=ANALYSIS_AGENT_ID, version="1", capabilities=AnalysisAgent.CAPABILITIES),
        )
    )
