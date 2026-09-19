"""The compiled form of a Plan — an immutable, backend-neutral representation.

decisions.md: D-112 (only ``agent`` and ``VERIFY`` compile, so only those two
node classes exist — an unsupported kind is *unrepresentable* here rather than
a placeholder), D-114 (the compiler's input and output are separate authorities
from V0.2 validation), D-115 (this package is backend-neutral and imports no
execution backend), D-117 (a node's ``level`` is the length of its longest predecessor
chain, counted in nodes: 1 for a root), D-124 (``VERIFY`` is a control kind that
compiles to a ``VerifyNode``).

What this module deliberately does not carry: execution-backend objects, agent or model
bindings, budgets, retry or timeout fields, conditions or predicates, edge
objects, parent-plan lineage, MissionState, or any mutable collection. Lineage
(``parent_plan_id``, ``replan_reason``) stays in ``Plan``, the single source of
truth; the compiled form only says which plan version it was built from.

The model validates itself, so an inconsistent compiled form cannot be built by
hand any more than by the compiler: unique step ids, ``position`` equal to the
node's index, resolved and non-repeating predecessors, predecessors at strictly
lower levels, and ``level`` exactly ``1 + max(predecessor levels)``.

Implementation details (not decisions.md entries): each node carries a ``kind``
discriminator reusing ``PlanStepKind`` so the union round-trips through JSON
without a second vocabulary; a node's predecessors are unique — the compiler
collapses a repeated ``depends_on`` entry, which is the same edge.
"""

from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from eidos.contracts import (
    CapabilityId,
    EidosModel,
    MissionId,
    PlanId,
    PlanStepKind,
    StepId,
    TenantId,
)

# The step kinds V0.3 compiles (D-112). A tuple: fixed order, immutable.
SUPPORTED_STEP_KINDS: tuple[PlanStepKind, ...] = (PlanStepKind.AGENT, PlanStepKind.VERIFY)


class _NodeBase(EidosModel):
    step_id: StepId
    position: int = Field(ge=0)  # index of the originating step in Plan.steps
    level: int = Field(ge=1)  # 1 + max(predecessor levels); 1 for a root (D-117)
    predecessors: tuple[StepId, ...]  # resolved step ids; the plan's depends_on edges


class WorkNode(_NodeBase):
    """A work step: performs work through a requested capability (invariant 11)."""

    kind: Literal[PlanStepKind.AGENT] = PlanStepKind.AGENT
    capability: CapabilityId


class VerifyNode(_NodeBase):
    """A verification step (D-124). Carries no capability."""

    kind: Literal[PlanStepKind.VERIFY] = PlanStepKind.VERIFY


CompiledNode = Annotated[Union[WorkNode, VerifyNode], Field(discriminator="kind")]


class CompiledPlan(EidosModel):
    """One Plan version, compiled. Nodes are in ``Plan.steps`` order."""

    tenant_id: TenantId
    mission_id: MissionId
    plan_id: PlanId
    plan_version: int = Field(ge=1)
    nodes: tuple[CompiledNode, ...]

    @model_validator(mode="after")
    def _check_nodes_are_consistent(self) -> "CompiledPlan":
        level_of = _check_unique_ids(self.nodes)
        _check_positions(self.nodes)
        _check_predecessors_resolve(self.nodes, level_of)
        _check_predecessors_strictly_lower(self.nodes, level_of)
        _check_levels_are_exact(self.nodes, level_of)
        return self


def _check_unique_ids(nodes: tuple[CompiledNode, ...]) -> dict[StepId, int]:
    """Map step id -> level, rejecting a repeated id. Used for lookup only, never iterated."""
    level_of: dict[StepId, int] = {}
    for node in nodes:
        if node.step_id in level_of:
            raise ValueError(f"duplicate step_id {node.step_id!r} in compiled nodes")
        level_of[node.step_id] = node.level
    return level_of


def _check_positions(nodes: tuple[CompiledNode, ...]) -> None:
    for index, node in enumerate(nodes):
        if node.position != index:
            raise ValueError(
                f"node {node.step_id!r} has position {node.position}, "
                f"but it is at index {index} of the compiled nodes"
            )


def _check_predecessors_resolve(
    nodes: tuple[CompiledNode, ...], level_of: dict[StepId, int]
) -> None:
    for node in nodes:
        listed: dict[StepId, None] = {}  # membership only
        for predecessor in node.predecessors:
            if predecessor not in level_of:
                raise ValueError(
                    f"node {node.step_id!r} has predecessor {predecessor!r}, "
                    "which is not a node of this compiled plan"
                )
            if predecessor in listed:
                raise ValueError(
                    f"node {node.step_id!r} lists predecessor {predecessor!r} more than once"
                )
            listed[predecessor] = None


def _check_predecessors_strictly_lower(
    nodes: tuple[CompiledNode, ...], level_of: dict[StepId, int]
) -> None:
    for node in nodes:
        for predecessor in node.predecessors:
            if level_of[predecessor] >= node.level:
                raise ValueError(
                    f"node {node.step_id!r} is at level {node.level} but its predecessor "
                    f"{predecessor!r} is at level {level_of[predecessor]}; "
                    "a predecessor must be at a strictly lower level"
                )


def _check_levels_are_exact(
    nodes: tuple[CompiledNode, ...], level_of: dict[StepId, int]
) -> None:
    for node in nodes:
        expected = 1 + max((level_of[p] for p in node.predecessors), default=0)
        if node.level != expected:
            raise ValueError(
                f"node {node.step_id!r} has level {node.level}, expected {expected} "
                "(1 + the highest predecessor level, or 1 for a root)"
            )
