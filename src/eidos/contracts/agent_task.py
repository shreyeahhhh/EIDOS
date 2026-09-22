"""AgentTask — handoff §8.

decisions.md: D-033 (nested model; does NOT carry tenant_id), D-036 (status semantics — **resolved by D-166**: the real ten-value A2A `TaskState`
vocabulary, plus one EIDOS-observed value, `TIMED_OUT`), D-048 (V0.1 shape: `agent_id` and `status` required; four fields optional, kept
future-compatible for V0.6), D-053 (`agent_id` is UUID-backed, not exempted by any decision), D-081 (`status` was an opaque string in V0.1 — no
enumeration, so D-036's eventual state set was not pre-empted; **discharged by D-166**), D-095 (`a2a_task_id` and `a2a_context_id` are externally
assigned opaque strings, exempt from the UUID-backed default, since the remote A2A system assigns them and EIDOS only mirrors them), D-096
(`last_event` is a reference — `EventId` or `None` — never an embedded `MissionEvent`), D-098 (`latest_artifact` is `ArtifactRef` or `None`; no
`Artifact` model is created, since the handoff never defines what an artifact contains), D-168 (`plan_id`, `step_id` and `started_at`, all optional
and additive, correlating a mirrored remote task to the plan node it serves).

The ten ``AgentTaskStatus`` members name the real A2A ``TaskState`` concepts — verified against the published A2A Protocol Specification
(a2a-protocol.org, v1.0), not invented — plus one EIDOS-observed value, ``TIMED_OUT``, that no wire message ever carries: it is what an adapter
concludes when no terminal report arrives within its own configured deadline (D-173 item 2). **The exact literal JSON string an A2A v1.0 server puts
on the wire for each state is unverified for the JSON-RPC/REST binding specifically** — the canonical schema is protobuf-generated
(`TASK_STATE_SUBMITTED`-style), while an older, pre-unification example showed plain lowercase. D-166 fixes this enum's member *names* and their
meaning; translating a real wire string into one of these members is the A2A client's job (a later V0.6 step, not built), not this contract's, so
nothing here claims to reproduce the literal wire form.

Neither this module nor any other in ``eidos.contracts`` imports ``eidos.runtime``: the separate, explicit mapping from ``AgentTaskStatus`` to
``NodeStatus`` that D-166 calls for lives in ``eidos.state`` (``eidos.state.agent_tasks``), which is the layer already permitted to know about A2A
task correlation and state.
"""

from enum import StrEnum

from ._base import EidosModel
from ._validators import UtcDateTime
from .identifiers import (
    A2AContextId,
    A2ATaskId,
    AgentId,
    ArtifactRef,
    EventId,
    PlanId,
    StepId,
)


class AgentTaskStatus(StrEnum):
    """The real A2A ``TaskState`` vocabulary (D-166, resolving D-036), plus one EIDOS-observed value.

    Four are terminal in the protocol itself: ``COMPLETED``, ``FAILED``, ``CANCELED``, ``REJECTED``. Two are interrupted but not terminal:
    ``INPUT_REQUIRED``, ``AUTH_REQUIRED`` — V0.6's minimal slice builds no interactive or authenticated flow, but the state must still be
    representable, never silently dropped (the remote's exact reported state is preserved, never collapsed early). ``SUBMITTED``, ``WORKING`` and
    ``UNSPECIFIED`` are not terminal. ``TIMED_OUT`` is EIDOS's own conclusion and is never a wire value.
    """

    SUBMITTED = "SUBMITTED"
    WORKING = "WORKING"
    INPUT_REQUIRED = "INPUT_REQUIRED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    UNSPECIFIED = "UNSPECIFIED"
    TIMED_OUT = "TIMED_OUT"


class AgentTask(EidosModel):
    agent_id: AgentId
    status: AgentTaskStatus

    a2a_task_id: A2ATaskId | None = None
    a2a_context_id: A2AContextId | None = None
    latest_artifact: ArtifactRef | None = None
    last_event: EventId | None = None

    plan_id: PlanId | None = None
    step_id: StepId | None = None
    started_at: UtcDateTime | None = None
