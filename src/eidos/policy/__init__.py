"""Deterministic governance — at V1.2 only tool admission (decisions.md D-203, invariant 14).

    decision = admit_tool_call(registry=..., tool_id=..., arguments=..., execution_id=..., plan_id=..., allowed_actions=...,
                               autonomy_level=..., max_tool_calls=..., prior_invocations=...)      # a ToolAdmission: invoke, serve stored, or deny

This is **not** a general policy engine: autonomy levels 2 to 4, human approval, failure recovery and execution-budget enforcement are
deferred and unassigned (D-203). It is a small, pure layer: no I/O, no network, no clock, no randomness, no model call and no hidden state.
It depends only on ``eidos.contracts`` and ``eidos.capabilities``; it imports no agent, provider, transport or backend, and no core layer
imports it.
"""

from .tool_admission import (
    ArgumentViolation,
    ArgumentViolationCode,
    ToolAdmission,
    ToolDecision,
    ToolDenial,
    ToolDenialCode,
    ToolInvocationRecord,
    admit_tool_call,
    args_digest,
)

__all__ = [
    "ArgumentViolation",
    "ArgumentViolationCode",
    "ToolAdmission",
    "ToolDecision",
    "ToolDenial",
    "ToolDenialCode",
    "ToolInvocationRecord",
    "admit_tool_call",
    "args_digest",
]
