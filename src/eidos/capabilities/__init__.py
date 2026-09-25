"""The V0.4 capability set, the agent registry and binding — milestone V0.4, Step 4 — and, from V1.2 Step 2, the tool allowlist.

decisions.md: D-132 and D-144 (the five lowercase exact-string capability IDs, V0.4 only; D-007 stays Open),
D-133 (``VERIFY`` is bound to the ``Verifier`` port by node kind, not by capability), D-134 (a registry resolves a
capability to an agent; an unbound capability is a typed rejection before dispatch; V0.2 is unchanged), D-203 (a tool is a pinned
allowlist entry that EIDOS writes: ``ToolDescriptor`` and ``ToolRegistry``; no new capability).

    registry = CapabilityRegistry(agents=(AgentDescriptor(agent_id=..., version="1", capabilities=(RESEARCH,)),))
    report = bind_plan(compiled_plan, registry)      # a BindReport: every work node bound, or every unbound one named

Constraints: deterministic, no I/O, no network, no clock, no randomness, no hidden state. It depends only on
``eidos.contracts`` and ``eidos.compiler``; it imports no agent, provider or backend, and no core layer imports it.
"""

from .binding import BindFailureCode, BindReport, BindViolation, NodeBinding, bind_plan
from .registry import AgentDescriptor, CapabilityRegistry
from .tools import ToolArgumentKind, ToolArgumentSpec, ToolDescriptor, ToolRegistry
from .vocabulary import ARCHITECTURE, COST, RESEARCH, SECURITY, V04_CAPABILITIES, VERIFICATION

__all__ = [
    "ARCHITECTURE",
    "AgentDescriptor",
    "BindFailureCode",
    "BindReport",
    "BindViolation",
    "COST",
    "CapabilityRegistry",
    "NodeBinding",
    "RESEARCH",
    "SECURITY",
    "ToolArgumentKind",
    "ToolArgumentSpec",
    "ToolDescriptor",
    "ToolRegistry",
    "V04_CAPABILITIES",
    "VERIFICATION",
    "bind_plan",
]
