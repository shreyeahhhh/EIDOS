"""Plan and PlanStep — handoff §13.

decisions.md: D-004 (canonical ID-addressed DAG; step-id namespace is per
plan version), D-047 (V0.1 defines structure only — kinds, step ids,
capability, edges, DAG — no predicate/condition language and no
conditional payload), D-049 (a capability-bearing work-step category
distinct from control-flow steps), D-050 (SEQUENTIAL/PARALLEL are not
canonical kinds; ordering is expressed by depends_on edges alone), D-053/
D-092 (StepId is an opaque string, exempt from the UUID-backed default, and
is unique within one Plan instance/version — not across a mission's
versions), D-077 (Plan/PlanStep required-optional split), D-079 (tenant_id
default), D-080 (CapabilityId), D-082 (version is a positive integer from
1; steps is an immutable ordered collection), D-088 (Plan.mission_id stays
required — a deliberate asymmetry with D-068, since a plan is a
mission-specific versioned artifact that should self-identify outside
MissionState), D-093 (steps is not a map keyed by step_id; uniqueness is
validated separately, which is what the model_validator below does), D-101
(the work-step kind is literally "agent").

PlanStep is a discriminated union of AgentStep and ControlStep rather than
one flat class with a runtime branch, so that "a control step carrying a
capability" and "a work step without one" are unrepresentable rather than
merely rejected by a rule (docs/05_plan_dsl.md's explicit wording; approved
as A3, 2026-09-18).

The two Plan-level failures that are not schema failures — a duplicate step_id
and an unresolved depends_on — raise the typed ValueError subclasses
DuplicateStepIdError and UnknownDependencyError, so a caller can tell them
apart from each other and from a structural failure without matching message
text (D-107). Both remain ValueErrors with unchanged messages.

What this module does NOT do (out of V0.1 scope):
  - cycle detection — depends_on is checked for referential existence only,
    never for cycles, including trivial self-dependency (V0.2, D-004/D-093)
  - any predicate, condition or routing semantics for ROUTE/RETRY/REPLAN/
    TERMINATE (D-012, Open)
  - normalizing a nested/tree-shaped authoring surface into this DAG form
    (deferred sugar layer, D-004/D-050)
"""

from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from ._base import EidosModel
from .enums import PlanStepKind
from .identifiers import (
    CapabilityId,
    DEFAULT_TENANT_ID,
    MissionId,
    PlanId,
    StepId,
    TenantId,
)


class DuplicateStepIdError(ValueError):
    """Two steps in one Plan share a step_id (decisions.md D-092/D-093, D-107)."""

    def __init__(self, step_id: StepId) -> None:
        self.step_id = step_id
        super().__init__(
            f"duplicate step_id {step_id!r} within plan "
            "(decisions.md D-092/D-093: step_id must be unique "
            "within one Plan)"
        )


class UnknownDependencyError(ValueError):
    """A step's depends_on names a step_id not in the Plan (decisions.md D-004, D-107)."""

    def __init__(self, step_id: StepId, dependency: StepId) -> None:
        self.step_id = step_id
        self.dependency = dependency
        super().__init__(
            f"step {step_id!r} depends_on unknown step_id "
            f"{dependency!r} (referential integrity only — cycle "
            "detection is not V0.1 scope, decisions.md D-004)"
        )


class _PlanStepBase(EidosModel):
    step_id: StepId
    depends_on: tuple[StepId, ...]


class AgentStep(_PlanStepBase):
    """The capability-bearing work-step kind (decisions.md D-101)."""

    kind: Literal[PlanStepKind.AGENT] = PlanStepKind.AGENT
    capability: CapabilityId


class ControlStep(_PlanStepBase):
    """A control-flow step. Never carries a capability (decisions.md D-049)."""

    kind: Literal[
        PlanStepKind.ROUTE,
        PlanStepKind.VERIFY,
        PlanStepKind.RETRY,
        PlanStepKind.REPLAN,
        PlanStepKind.HUMAN_APPROVAL,
        PlanStepKind.TERMINATE,
    ]


PlanStep = Annotated[Union[AgentStep, ControlStep], Field(discriminator="kind")]


class Plan(EidosModel):
    tenant_id: TenantId = Field(default=DEFAULT_TENANT_ID)
    plan_id: PlanId
    mission_id: MissionId
    version: int = Field(ge=1)
    parent_plan_id: PlanId | None = None
    replan_reason: str | None = None
    steps: tuple[PlanStep, ...]

    @model_validator(mode="after")
    def _check_step_ids_unique(self) -> "Plan":
        seen: set[StepId] = set()
        for step in self.steps:
            if step.step_id in seen:
                raise DuplicateStepIdError(step.step_id)
            seen.add(step.step_id)
        return self

    @model_validator(mode="after")
    def _check_depends_on_resolve(self) -> "Plan":
        step_ids = {step.step_id for step in self.steps}
        for step in self.steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    raise UnknownDependencyError(step.step_id, dep)
        return self
