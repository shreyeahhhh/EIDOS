"""Binding: which agent will perform each work node (D-134, invariant 11).

Plans request capabilities, not named agents (invariant 11). Binding is the step that, once a plan is validated and
compiled, resolves each work node's capability to an agent through the registry. It happens when the run is
constructed, **before anything is dispatched**. V0.2 validation is unchanged and does not learn which agents exist
(D-102); binding is a third authority with its own typed failure family, separate from ``ViolationCode`` and
``CompileFailureCode``, for the reason D-114 separates validation from compilation.

Only work nodes are bound. A ``VERIFY`` node is bound to the ``Verifier`` port by node kind, never by capability
(D-133), so it never appears here and never causes a violation.

``bind_plan`` never raises for a plan it cannot bind: an unbound capability is a report, with **every** unbound step
named (not only the first), in plan order. It is deterministic and does no I/O.
"""

from enum import StrEnum

from pydantic import Field, model_validator

from eidos.compiler import CompiledPlan, WorkNode
from eidos.contracts import AgentId, CapabilityId, EidosModel, PlanId, StepId

from .registry import CapabilityRegistry


class BindFailureCode(StrEnum):
    UNBOUND_CAPABILITY = "unbound_capability"  # no registered agent serves the requested capability (exact string)


class BindViolation(EidosModel):
    code: BindFailureCode
    message: str = Field(min_length=1)
    step_id: StepId
    capability: CapabilityId


class NodeBinding(EidosModel):
    step_id: StepId
    capability: CapabilityId
    agent_id: AgentId


class BindReport(EidosModel):
    """Either every work node bound, or the unbound ones named. Never both, and never a partial binding."""

    plan_id: PlanId
    bindings: tuple[NodeBinding, ...] = ()
    violations: tuple[BindViolation, ...] = ()

    @model_validator(mode="after")
    def _check_a_failed_report_binds_nothing(self) -> "BindReport":
        if self.violations and self.bindings:
            raise ValueError("a report with violations binds nothing: a partial binding would be half-honoured")
        return self

    @property
    def succeeded(self) -> bool:
        return not self.violations

    def agent_for(self, step_id: StepId) -> AgentId | None:
        for binding in self.bindings:
            if binding.step_id == step_id:
                return binding.agent_id
        return None


def bind_plan(compiled: CompiledPlan, registry: CapabilityRegistry) -> BindReport:
    """Resolve every work node's capability to an agent, or report every one that cannot be."""
    bindings: list[NodeBinding] = []
    violations: list[BindViolation] = []
    for node in compiled.nodes:
        if not isinstance(node, WorkNode):
            continue  # VERIFY is bound by node kind (D-133)
        agent_id = registry.resolve(node.capability)
        if agent_id is None:
            violations.append(
                BindViolation(
                    code=BindFailureCode.UNBOUND_CAPABILITY,
                    message=(
                        f"step {str(node.step_id)!r} requests capability {str(node.capability)!r}, "
                        "which no registered agent serves"
                    ),
                    step_id=node.step_id,
                    capability=node.capability,
                )
            )
        else:
            bindings.append(NodeBinding(step_id=node.step_id, capability=node.capability, agent_id=agent_id))
    if violations:
        return BindReport(plan_id=compiled.plan_id, violations=tuple(violations))
    return BindReport(plan_id=compiled.plan_id, bindings=tuple(bindings))
