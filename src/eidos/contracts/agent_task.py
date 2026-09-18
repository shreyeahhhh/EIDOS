"""AgentTask — handoff §8.

decisions.md: D-033 (nested model; does NOT carry tenant_id), D-036 (status
semantics — the state set and legal transitions — remain Open; nothing in
this codebase may branch on its value until D-036 defines the lifecycle),
D-048 (V0.1 shape: agent_id and status required; four fields optional, kept
future-compatible for V0.6), D-053 (agent_id is UUID-backed, not exempted
by any decision), D-081 (status is an opaque string in V0.1 — no
enumeration, so D-036's eventual state set is not pre-empted), D-095
(a2a_task_id and a2a_context_id are externally assigned opaque strings,
exempt from the UUID-backed default, since the remote A2A system assigns
them and EIDOS only mirrors them), D-096 (last_event is a reference —
EventId or None — never an embedded MissionEvent), D-098 (latest_artifact
is ArtifactRef or None; no Artifact model is created, since the handoff
never defines what an artifact contains).
"""

from .identifiers import (
    A2AContextId,
    A2ATaskId,
    AgentId,
    ArtifactRef,
    EventId,
)
from ._base import EidosModel


class AgentTask(EidosModel):
    agent_id: AgentId
    status: str

    a2a_task_id: A2ATaskId | None = None
    a2a_context_id: A2AContextId | None = None
    latest_artifact: ArtifactRef | None = None
    last_event: EventId | None = None
