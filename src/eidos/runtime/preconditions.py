"""Run preconditions — checked before anything is dispatched.

decisions.md: D-113 (the run is bound to one frozen context), D-120 (invalid prior state
produces a typed rejection and is never silently adapted — not dropped, reordered,
repaired or partly honoured), D-123 (nothing is written).

These checks are about *whether a run may start at all*, so they are independent of how
a backend schedules nodes. They live here, rather than in the executor, so that every
backend applies exactly the same ones and cannot drift from the reference.

The first failing check wins, in this fixed order: tenant, mission, plan, plan version,
then prior state. Nothing is adapted to make a mismatch fit.
"""

from eidos.compiler import CompiledPlan
from eidos.contracts import StepId

from .context import ExecutionContext
from .results import NodeStatus, PriorOutcomes, RunRejection, RunRejectionCode


def check_run_preconditions(
    compiled: CompiledPlan, context: ExecutionContext, prior: PriorOutcomes | None
) -> RunRejection | None:
    """``None`` if the run may start; otherwise the typed reason it may not."""
    if context.tenant_id != compiled.tenant_id:
        return RunRejection(
            code=RunRejectionCode.WRONG_TENANT,
            message=(
                f"the context is for tenant {str(context.tenant_id)!r}, but the compiled plan "
                f"belongs to tenant {str(compiled.tenant_id)!r}"
            ),
        )
    if context.mission_id != compiled.mission_id:
        return RunRejection(
            code=RunRejectionCode.WRONG_MISSION,
            message=(
                f"the context is for mission {str(context.mission_id)!r}, but the compiled plan "
                f"belongs to mission {str(compiled.mission_id)!r}"
            ),
        )
    if context.plan_id != compiled.plan_id:
        return RunRejection(
            code=RunRejectionCode.WRONG_PLAN,
            message=(
                f"the context is for plan {str(context.plan_id)!r}, not for the compiled "
                f"plan {str(compiled.plan_id)!r}"
            ),
        )
    if context.plan_version != compiled.plan_version:
        return RunRejection(
            code=RunRejectionCode.WRONG_PLAN_VERSION,
            message=(
                f"the context is for plan version {context.plan_version}, but the compiled "
                f"plan is version {compiled.plan_version}"
            ),
        )
    if prior is None:
        return None
    return _check_prior(compiled, context, prior)


def _invalid_prior(message: str, *step_ids: StepId) -> RunRejection:
    return RunRejection(
        code=RunRejectionCode.INVALID_PRIOR_STATE, message=message, step_ids=tuple(step_ids)
    )


def _check_prior(
    compiled: CompiledPlan, context: ExecutionContext, prior: PriorOutcomes
) -> RunRejection | None:
    # 1. The prior must belong to this execution and this plan version.
    for name in ("tenant_id", "mission_id", "execution_id", "plan_id", "plan_version"):
        if getattr(prior, name) != getattr(context, name):
            return _invalid_prior(
                f"the prior outcomes' {name} is {str(getattr(prior, name))!r}, but this run's "
                f"context has {str(getattr(context, name))!r}"
            )

    node_by_id = {node.step_id: node for node in compiled.nodes}  # lookup only

    # 2. Each prior outcome must be a SUCCEEDED outcome of a real node of the right kind.
    for outcome in prior.outcomes:
        if outcome.status is not NodeStatus.SUCCEEDED:
            return _invalid_prior(
                f"prior outcome for {outcome.step_id!r} is {outcome.status.value}; only "
                "succeeded outcomes are valid prior state",
                outcome.step_id,
            )
        node = node_by_id.get(outcome.step_id)
        if node is None:
            return _invalid_prior(
                f"prior outcome names step {outcome.step_id!r}, which is not a node of this plan",
                outcome.step_id,
            )
        if outcome.kind is not node.kind:
            return _invalid_prior(
                f"prior outcome for {outcome.step_id!r} is of kind {outcome.kind.value!r}, but "
                f"the node is {node.kind.value!r}",
                outcome.step_id,
            )

    # 3. A node cannot have succeeded unless every predecessor did: prior state that says
    #    otherwise contradicts the plan's own edges.
    carried = {outcome.step_id: None for outcome in prior.outcomes}  # membership only
    for node in compiled.nodes:
        if node.step_id not in carried:
            continue
        for predecessor in node.predecessors:
            if predecessor not in carried:
                return _invalid_prior(
                    f"prior marks {node.step_id!r} succeeded, but its predecessor "
                    f"{predecessor!r} has no succeeded prior outcome",
                    node.step_id,
                    predecessor,
                )
    return None
