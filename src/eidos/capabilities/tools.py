"""The tool descriptor and the tool registry (decisions.md D-203; V1.2 Step 2).

A tool is one entry in a **pinned allowlist** that EIDOS itself writes. Nothing a tool provider says about itself is read
here: whether a tool is read-only, which action it performs, what arguments it takes and how long it may run are all
stated by the entry, never inferred from anything the provider reports (D-203 ruling 2, invariant 14). Admitting or
refusing a call is not this module's job; that is ``eidos.policy``. This module only says what an allowlist entry is.

``tool_id`` is ``<provider_id>/<tool_name>``. A tool name is unique only within its provider, and a provider's own
self-description is not to be relied on, so the provider id is a value EIDOS configures. Both parts are restricted to
letters, digits, underscore, hyphen and dot, so the join is never ambiguous and the identifier is safe to hash and to
put in a reference.

The argument schema is deliberately tiny: flat, scalar, named arguments, each a string or an integer with explicit
bounds and no defaults. ``minimum`` and ``maximum`` bound a string's length in characters and an integer's value.

The registry resolves by exact string, never by nearest match, and its answers do not depend on the order entries were
listed in. A tool serves one of the existing capabilities; no capability is added (D-203 ruling 7, D-132).

Constraints: deterministic, no I/O, no network, no clock, no randomness, no hidden state. It depends only on
``eidos.contracts``; no core layer imports it and it imports no agent, provider or backend.
"""

from enum import StrEnum

from pydantic import Field, model_validator

from eidos.contracts import ActionId, CapabilityId, EidosModel

from .vocabulary import V04_CAPABILITIES

_IDENTIFIER = r"^[A-Za-z0-9_.-]{1,128}$"
_SHA256_HEX = r"^[0-9a-f]{64}$"


class ToolArgumentKind(StrEnum):
    STRING = "string"
    INTEGER = "integer"


class ToolArgumentSpec(EidosModel):
    """One named argument a tool takes. ``minimum``/``maximum`` bound a string's length or an integer's value; both are required."""

    name: str = Field(pattern=_IDENTIFIER)
    kind: ToolArgumentKind
    required: bool
    minimum: int
    maximum: int

    @model_validator(mode="after")
    def _check_the_bounds_make_sense_for_the_kind(self) -> "ToolArgumentSpec":
        if self.minimum > self.maximum:
            raise ValueError("an argument's minimum may not exceed its maximum")
        if self.kind is ToolArgumentKind.STRING and (self.minimum < 0 or self.maximum < 1):
            raise ValueError("a string argument's length bounds are at least 0 and at most 1 or more")
        return self


class ToolDescriptor(EidosModel):
    """One allowlist entry. Every field is stated by EIDOS; ``read_only`` in particular is the entry's own declaration,
    and a provider's claim about itself never reaches this model.

    ``input_schema_digest`` pins the provider's declared input schema (a SHA-256 in lowercase hex) so a later change to
    that schema can be noticed when the provider is contacted. Admission never reads it.
    """

    provider_id: str = Field(pattern=_IDENTIFIER)
    tool_name: str = Field(pattern=_IDENTIFIER)
    capability: CapabilityId
    action_id: ActionId = Field(min_length=1)
    read_only: bool
    arguments: tuple[ToolArgumentSpec, ...]
    timeout_seconds: float = Field(gt=0)
    max_result_bytes: int = Field(gt=0)
    input_schema_digest: str = Field(pattern=_SHA256_HEX)

    @property
    def tool_id(self) -> str:
        return f"{self.provider_id}/{self.tool_name}"

    @model_validator(mode="after")
    def _check_argument_names_are_distinct(self) -> "ToolDescriptor":
        names = [argument.name for argument in self.arguments]
        if len(set(names)) != len(names):
            raise ValueError("a tool lists each argument at most once")
        return self


class ToolRegistry(EidosModel):
    """The pinned allowlist: exactly the tools EIDOS has listed, and nothing else."""

    tools: tuple[ToolDescriptor, ...]

    @model_validator(mode="after")
    def _check_registrations_are_unambiguous(self) -> "ToolRegistry":
        seen: dict[str, None] = {}  # membership only
        for tool in self.tools:
            if tool.tool_id in seen:
                raise ValueError(f"tool_id {tool.tool_id!r} is registered twice")
            seen[tool.tool_id] = None
            if tool.capability not in V04_CAPABILITIES:
                raise ValueError(f"capability {tool.capability!r} is not in the V0.4 vocabulary")
        return self

    def resolve(self, tool_id: str) -> ToolDescriptor | None:
        """The entry whose ``tool_id`` is exactly ``tool_id``, or ``None`` — never a guess, never the nearest match."""
        for tool in self.tools:
            if tool.tool_id == tool_id:
                return tool
        return None

    def for_capability(self, capability: CapabilityId) -> tuple[ToolDescriptor, ...]:
        """Every entry serving ``capability``, ordered by ``tool_id`` so the answer never depends on registration order."""
        return tuple(sorted((tool for tool in self.tools if tool.capability == capability), key=lambda tool: tool.tool_id))
