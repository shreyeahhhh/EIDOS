"""Factories for V0.3 compiler tests.

Two kinds of validation report are needed, and they are deliberately different:

- ``validated_report`` runs the real V0.2 pipeline against a state built around
  the plan, so a test can show that V0.2 genuinely accepted a plan that the
  compiler then rejects (a ROUTE step, for instance).
- ``forged_report`` builds a report by hand — accepted or not, for any plan id —
  without running validation. It is how tests give the compiler *evidence that
  lies* (a report claiming acceptance for a plan that is cyclic), which the
  compiler must not trust for structure (decisions.md D-114).
"""

from uuid import UUID

from eidos.contracts import AgentStep, PlanId, StepId
from eidos.validation import (
    PlanValidationReport,
    StageResult,
    StageStatus,
    SystemLimits,
    ValidationStage,
    Violation,
    ViolationCode,
    validate_plan,
)

from eidos_factories import (
    make_agent_step,
    make_mission_state,
    make_plan,
    make_reliability_contract,
    make_task_genome,
)
from eidos_validation_factories import make_system_limits


def plan_of(spec: dict[str, str], **plan_overrides):
    """A plan of ``agent`` steps from ``{"name": "dep1 dep2"}``, in dict order."""
    steps = tuple(
        make_agent_step(step_id=StepId(name), depends_on=tuple(StepId(d) for d in deps.split()))
        for name, deps in spec.items()
    )
    return make_plan(steps=steps, **plan_overrides)


def forged_report(
    plan_id: PlanId | None,
    *,
    skipped: ValidationStage | None = None,
    failed_cycle: bool = False,
) -> PlanValidationReport:
    """A hand-built report. By default every stage passes (POLICY is NOT_APPLICABLE),
    so it is *accepted* — whatever the plan it names actually contains.

    ``skipped`` marks one stage SKIPPED and ``failed_cycle`` marks CYCLE FAILED; either
    makes the report unaccepted.
    """
    stages = []
    for stage in ValidationStage:
        if stage is skipped:
            stages.append(
                StageResult(stage=stage, status=StageStatus.SKIPPED, detail="forged for a test")
            )
        elif stage is ValidationStage.CYCLE and failed_cycle:
            violation = Violation(
                stage=stage,
                code=ViolationCode.CYCLE_DETECTED,
                message="forged for a test",
                step_ids=(StepId("forged"),),
            )
            stages.append(
                StageResult(stage=stage, status=StageStatus.FAILED, violations=(violation,))
            )
        elif stage is ValidationStage.POLICY:
            stages.append(
                StageResult(
                    stage=stage, status=StageStatus.NOT_APPLICABLE, detail="no policy check (D-110)"
                )
            )
        else:
            stages.append(StageResult(stage=stage, status=StageStatus.PASSED))
    return PlanValidationReport(plan_id=plan_id, stages=tuple(stages))


def forged_accepted_report(plan) -> PlanValidationReport:
    return forged_report(plan.plan_id)


def validated_report(plan, *, limits: SystemLimits | None = None) -> PlanValidationReport:
    """The real V0.2 report for ``plan``, against a mission built around the plan's ids.

    The mission requires exactly the capabilities the plan's work steps request, so
    V0.2's capability stage is satisfied; nothing else about the plan is adjusted.
    """
    contract = make_reliability_contract(tenant_id=plan.tenant_id)
    required = tuple(
        dict.fromkeys(step.capability for step in plan.steps if isinstance(step, AgentStep))
    )
    genome = make_task_genome(contract=contract, required_capabilities=required)
    state = make_mission_state(
        tenant_id=plan.tenant_id,
        mission_id=plan.mission_id,
        reliability_contract=contract,
        task_genome=genome,
    )
    return validate_plan(plan, state, limits or make_system_limits())


def fixed_plan_id(n: int) -> PlanId:
    return PlanId(UUID(int=n))
