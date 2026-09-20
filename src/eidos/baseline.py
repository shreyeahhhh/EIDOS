"""The single-pass baseline runner (decisions.md D-131, D-133, D-134, D-140).

One pass, no CLI, no API. Given a mission, a **supplied** plan and the pieces to run it, it does exactly this, in order, and stops
at the first gate that refuses:

    validate (V0.2)  ->  compile  ->  bind capabilities to agents  ->  execute

Nothing generates plans (D-131): there is no planner, no candidate strategy and no system-driven replan. A replan is a caller-supplied
new plan, run by calling this again (D-119). Nothing is dispatched until validation, compilation and binding have all succeeded, so an
unbound capability is refused **before** any agent is called (D-134).

The runner is backend-neutral: it is handed an executor *factory* (the reference ``SequentialExecutor``, or an execution-backend
class) and never imports a backend or a provider. It needs no model of its own: the agents it is handed hold the model seam.

It reads ``MissionState`` once, through ``context_from_state`` (D-113), and writes nothing to it (D-123). The **artifact store belongs
to the caller**: supply documents to it, under the mission's ``execution_id``, before calling (D-145). The ``AdmissionGuard`` is required
and has no default (D-140). Two things it deliberately does not do: it does not report a "final answer" (D-041 stays Open), and it does
not claim the reliability contract was satisfied (D-146) — ``RunResult.verified`` keeps its meaning.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pydantic import model_validator

from eidos.agents import WorkAgent
from eidos.capabilities import BindReport, CapabilityRegistry, bind_plan
from eidos.compiler import CompiledPlan, CompileReport, WorkNode, compile_plan
from eidos.contracts import AgentId, EidosModel, MissionState, Plan, PlanId
from eidos.runtime import (
    AdmissionGuard,
    ExecutionContext,
    PriorOutcomes,
    RunRejection,
    RunResult,
    Verifier,
    WorkResult,
    context_from_state,
)
from eidos.validation import PlanValidationReport, SystemLimits, validate_plan


class Executor(Protocol):
    """What the reference executor and an execution backend both offer."""

    def run(
        self, compiled: CompiledPlan, context: ExecutionContext, prior: PriorOutcomes | None = None
    ) -> RunResult | RunRejection: ...


ExecutorFactory = Callable[..., Executor]  # called with work_executor=, verifier= and admission_guard=


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkDispatcher:
    """A ``WorkExecutor`` over the binding: it hands each work node to the agent the binding chose for it."""

    binding: BindReport
    agents: Mapping[AgentId, WorkAgent]

    def execute(self, context: ExecutionContext, node: WorkNode) -> WorkResult:
        agent_id = self.binding.agent_for(node.step_id)
        if agent_id is None:
            return WorkResult.failed(f"no agent is bound to step {str(node.step_id)!r}")
        agent = self.agents.get(agent_id)
        if agent is None:
            return WorkResult.failed(f"agent {str(agent_id)!r}, bound to step {str(node.step_id)!r}, was not supplied")
        return agent.run(context, node)


class BaselineStage(StrEnum):
    VALIDATION = "validation"
    COMPILATION = "compilation"
    BINDING = "binding"
    EXECUTION = "execution"


class BaselineReport(EidosModel):
    """Everything one pass produced, up to the gate that stopped it. Later stages are ``None`` when an earlier one refused."""

    plan_id: PlanId
    validation: PlanValidationReport
    compilation: CompileReport | None = None
    binding: BindReport | None = None
    run: RunResult | RunRejection | None = None

    @model_validator(mode="after")
    def _check_each_stage_ran_only_if_the_one_before_it_succeeded(self) -> "BaselineReport":
        earlier_ok = self.validation.accepted
        for name, value, ok in (
            ("compilation", self.compilation, self.compilation is not None and self.compilation.succeeded),
            ("binding", self.binding, self.binding is not None and self.binding.succeeded),
        ):
            if value is not None and not earlier_ok:
                raise ValueError(f"{name} ran although the stage before it did not succeed")
            if value is None and earlier_ok:
                raise ValueError(f"{name} is missing although the stage before it succeeded")
            earlier_ok = earlier_ok and ok
        if self.run is not None and not earlier_ok:
            raise ValueError("a run exists although an earlier stage did not succeed")
        if self.run is None and earlier_ok:
            raise ValueError("no run although every earlier stage succeeded")
        return self

    @property
    def stopped_at(self) -> BaselineStage | None:
        """The first gate that refused, or ``None`` when the plan reached execution (whatever the run's outcome)."""
        if not self.validation.accepted:
            return BaselineStage.VALIDATION
        if self.compilation is None or not self.compilation.succeeded:
            return BaselineStage.COMPILATION
        if self.binding is None or not self.binding.succeeded:
            return BaselineStage.BINDING
        return None

    @property
    def dispatched_anything(self) -> bool:
        return isinstance(self.run, RunResult) and bool(self.run.dispatched)


def run_baseline(
    *,
    state: MissionState,
    plan: Plan,
    limits: SystemLimits,
    registry: CapabilityRegistry,
    agents: Mapping[AgentId, WorkAgent],
    verifier: Verifier,
    admission_guard: AdmissionGuard,
    executor_factory: ExecutorFactory,
    prior: PriorOutcomes | None = None,
) -> BaselineReport:
    """Drive ``plan`` through validate, compile, bind and execute; stop at the first gate that refuses. Never raises for a bad plan."""
    validation = validate_plan(plan, state, limits)
    if not validation.accepted:
        return BaselineReport(plan_id=plan.plan_id, validation=validation)

    compilation = compile_plan(plan, validation)
    if not compilation.succeeded:
        return BaselineReport(plan_id=plan.plan_id, validation=validation, compilation=compilation)
    compiled = compilation.compiled

    binding = bind_plan(compiled, registry)
    if not binding.succeeded:
        return BaselineReport(plan_id=plan.plan_id, validation=validation, compilation=compilation, binding=binding)

    executor = executor_factory(
        work_executor=WorkDispatcher(binding=binding, agents=agents),
        verifier=verifier,
        admission_guard=admission_guard,
    )
    run = executor.run(compiled, context_from_state(state, compiled), prior)
    return BaselineReport(
        plan_id=plan.plan_id, validation=validation, compilation=compilation, binding=binding, run=run
    )
