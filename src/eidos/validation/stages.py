"""The individual validation stages — pure functions, one per pipeline stage.

Each stage takes only the narrow inputs it needs, returns a ``StageResult``
(or, for identity binding, the violations that feed the SCHEMA stage), and
never raises for an invalid plan. Only ``pipeline`` sees ``MissionState``.

decisions.md: D-004 (ID-addressed DAG), D-009 (tighten-but-never-exceed;
reject, never clamp), D-042/D-065 (six optional contract budgets; an omitted
one falls back to the system ceiling), D-050/D-104 (depth in nodes, width as
maximum antichain), D-102 (capability validation is mission-scoped), D-103
(no built-in limits: they are always passed in), D-105 (only *declared* agent
calls are checked structurally), D-106 (empty plans pass), D-110 (POLICY is
``NOT_APPLICABLE``).

Every ordering here comes from ``plan.steps`` order or a fixed tuple.
"""

from collections.abc import Sequence

from eidos.contracts import (
    AgentStep,
    CapabilityId,
    MissionId,
    Plan,
    ReliabilityContract,
    StepId,
    TenantId,
)

from .graph import find_cycles, longest_chain_length, max_antichain_width
from .limits import MISSION_BUDGETS, LimitName, SystemLimits
from .results import (
    StageResult,
    StageStatus,
    ValidationStage,
    Violation,
    ViolationCode,
)


def dependency_map(plan: Plan) -> dict[StepId, tuple[StepId, ...]]:
    """``step_id -> depends_on`` in plan order — the input the graph functions take."""
    return {step.step_id: step.depends_on for step in plan.steps}


def _outcome(stage: ValidationStage, violations: Sequence[Violation], detail: str | None = None) -> StageResult:
    status = StageStatus.FAILED if violations else StageStatus.PASSED
    return StageResult(stage=stage, status=status, violations=tuple(violations), detail=detail)


# --- identity binding (reported under SCHEMA) -----------------------------


def identity_violations(plan: Plan, *, mission_id: MissionId, tenant_id: TenantId) -> tuple[Violation, ...]:
    """Violations if the plan's own identity fields do not match the mission validated against.

    Without this, ``validate_plan(plan_of_mission_A, state_of_mission_B)`` would
    quietly check A's plan against B's task genome and contract (D-088).
    """
    violations: list[Violation] = []
    if plan.mission_id != mission_id:
        violations.append(
            Violation(
                stage=ValidationStage.SCHEMA,
                code=ViolationCode.PLAN_MISSION_MISMATCH,
                message=(
                    f"plan.mission_id {str(plan.mission_id)!r} does not match the mission "
                    f"being validated against, {str(mission_id)!r}"
                ),
            )
        )
    if plan.tenant_id != tenant_id:
        violations.append(
            Violation(
                stage=ValidationStage.SCHEMA,
                code=ViolationCode.PLAN_TENANT_MISMATCH,
                message=(
                    f"plan.tenant_id {str(plan.tenant_id)!r} does not match the tenant "
                    f"being validated against, {str(tenant_id)!r}"
                ),
            )
        )
    return tuple(violations)


# --- DEPENDENCY ------------------------------------------------------------


def check_dependencies(plan: Plan) -> StageResult:
    """Step ids are unique and every ``depends_on`` names a step in the plan (D-092/D-093).

    The ``Plan`` contract already enforces both when it is constructed, but a
    ``Plan`` can also be produced without validation (``model_copy(update=...)``,
    ``model_construct``). Re-checking here means a PASSED dependency stage reports
    a check that ran on *this* plan, and it guarantees the graph stages below are
    only ever given a well-defined graph.
    """
    violations: list[Violation] = []
    seen: set[StepId] = set()  # membership only; never iterated
    reported_duplicates: set[StepId] = set()
    for step in plan.steps:
        if step.step_id in seen and step.step_id not in reported_duplicates:
            reported_duplicates.add(step.step_id)
            violations.append(
                Violation(
                    stage=ValidationStage.DEPENDENCY,
                    code=ViolationCode.DUPLICATE_STEP_ID,
                    message=f"step_id {step.step_id!r} is used by more than one step",
                    step_ids=(step.step_id,),
                )
            )
        seen.add(step.step_id)
    for step in plan.steps:
        reported_dependencies: set[StepId] = set()
        for dependency in step.depends_on:
            if dependency not in seen and dependency not in reported_dependencies:
                reported_dependencies.add(dependency)
                violations.append(
                    Violation(
                        stage=ValidationStage.DEPENDENCY,
                        code=ViolationCode.UNKNOWN_DEPENDENCY,
                        message=f"step {step.step_id!r} depends on unknown step {dependency!r}",
                        step_ids=(step.step_id,),
                    )
                )
    return _outcome(ValidationStage.DEPENDENCY, violations)


# --- CYCLE -----------------------------------------------------------------


def check_cycles(plan: Plan) -> StageResult:
    """Reject any dependency cycle, including a step that depends on itself (D-004)."""
    violations = []
    for component in find_cycles(dependency_map(plan)):
        if len(component) == 1:
            message = f"step {component[0]!r} depends on itself"
        else:
            listed = ", ".join(repr(step_id) for step_id in component)
            message = f"steps {listed} form a dependency cycle"
        violations.append(
            Violation(
                stage=ValidationStage.CYCLE,
                code=ViolationCode.CYCLE_DETECTED,
                message=message,
                step_ids=component,
            )
        )
    return _outcome(ValidationStage.CYCLE, violations)


# --- CAPABILITY ------------------------------------------------------------


def check_capabilities(plan: Plan, *, required_capabilities: Sequence[CapabilityId]) -> StageResult:
    """Every ``agent`` step's capability must be one the mission declares it requires (D-102).

    Exact-string membership. No vocabulary, no registry, no case-folding or
    trimming. The converse — every required capability having a step — is not
    required. Control steps carry no capability and are not checked.
    """
    allowed = frozenset(required_capabilities)  # membership only; never iterated
    violations = [
        Violation(
            stage=ValidationStage.CAPABILITY,
            code=ViolationCode.CAPABILITY_NOT_REQUIRED,
            message=(
                f"step {step.step_id!r} requests capability {step.capability!r}, which is not in "
                "the mission's required_capabilities"
            ),
            step_ids=(step.step_id,),
            capability=step.capability,
        )
        for step in plan.steps
        if isinstance(step, AgentStep) and step.capability not in allowed
    ]
    return _outcome(ValidationStage.CAPABILITY, violations)


# --- POLICY ----------------------------------------------------------------


def check_policy() -> StageResult:
    """Reports ``NOT_APPLICABLE``: no policy check is defined (D-110).

    What a policy check would evaluate depends on autonomy semantics that are
    unresolved (D-060, D-061, D-074). No rule is invented here and there is no
    injection mechanism. This is deliberately not ``PASSED``: the stage did not
    approve the plan.
    """
    return StageResult(
        stage=ValidationStage.POLICY,
        status=StageStatus.NOT_APPLICABLE,
        detail=(
            "no policy check is defined at V0.2: autonomy semantics are unresolved "
            "(D-060, D-061, D-074) and none is invented (D-110); this stage did not approve the plan"
        ),
    )


# --- RESOURCE --------------------------------------------------------------


def check_resources(plan: Plan, *, contract: ReliabilityContract, limits: SystemLimits) -> StageResult:
    """Contract budgets against system ceilings, plus the declared agent-call count.

    1. For each of the six mission budgets the contract sets, the value must
       not exceed the system ceiling. Violations reject; nothing is clamped (D-009).
    2. The number of ``agent`` steps the plan **declares** must not exceed the
       effective ``max_agent_calls`` — ``min(system ceiling, contract value)``,
       or the ceiling alone when the contract omits it (D-065).

    Nothing else is inferred from plan structure: retries, replans, tool calls,
    execution time and tokens are checked only as contract-versus-ceiling
    (D-105). The declared count says nothing about actual invocations (D-043).
    """
    violations: list[Violation] = []
    for name in MISSION_BUDGETS:
        value = getattr(contract, name.value)
        ceiling = limits.ceiling(name)
        if value is not None and value > ceiling:
            violations.append(
                Violation(
                    stage=ValidationStage.RESOURCE,
                    code=ViolationCode.CONTRACT_EXCEEDS_CEILING,
                    message=(
                        f"contract {name.value} = {value} exceeds the system ceiling of {ceiling}; "
                        "rejected, not clamped"
                    ),
                    limit_name=name,
                    limit_value=ceiling,
                    observed_value=value,
                )
            )

    ceiling = limits.ceiling(LimitName.MAX_AGENT_CALLS)
    contract_value = contract.max_agent_calls
    effective = ceiling if contract_value is None else min(ceiling, contract_value)
    declared = sum(1 for step in plan.steps if isinstance(step, AgentStep))
    if declared > effective:
        violations.append(
            Violation(
                stage=ValidationStage.RESOURCE,
                code=ViolationCode.AGENT_CALLS_EXCEEDED,
                message=(
                    f"plan declares {declared} agent steps, more than the effective "
                    f"max_agent_calls of {effective} (system ceiling {ceiling}, contract "
                    f"{'not set' if contract_value is None else contract_value}); "
                    "this counts declared steps, not actual invocations"
                ),
                limit_name=LimitName.MAX_AGENT_CALLS,
                limit_value=effective,
                observed_value=declared,
            )
        )
    return _outcome(ValidationStage.RESOURCE, violations)


# --- COMPLEXITY ------------------------------------------------------------


def check_complexity(plan: Plan, *, limits: SystemLimits) -> StageResult:
    """``max_nodes``, ``max_depth`` (in nodes, D-104) and ``max_parallel_branches`` (D-050).

    An empty plan has 0 nodes, depth 0 and width 0 and passes (D-106).

    Skips, always stated in ``detail``:
    - A cyclic plan has no defined depth or width. If ``max_nodes`` also holds,
      nothing could be verified about depth or width, so the stage is SKIPPED,
      never PASSED. The cycle itself is the CYCLE stage's finding.
    - A plan over ``max_nodes`` is rejected without computing the width, which
      can cost quadratic time in the step count. Depth is linear and is still
      checked.
    """
    graph = dependency_map(plan)
    node_count = len(graph)
    violations: list[Violation] = []
    not_evaluated: list[str] = []

    node_limit = limits.max_nodes
    oversize = node_count > node_limit
    if oversize:
        violations.append(
            Violation(
                stage=ValidationStage.COMPLEXITY,
                code=ViolationCode.MAX_NODES_EXCEEDED,
                message=f"plan has {node_count} steps, more than max_nodes of {node_limit}",
                limit_name=LimitName.MAX_NODES,
                limit_value=node_limit,
                observed_value=node_count,
            )
        )

    depth = longest_chain_length(graph)
    if depth is None:
        not_evaluated.append("max_depth and max_parallel_branches (the plan is cyclic)")
    else:
        if depth > limits.max_depth:
            violations.append(
                Violation(
                    stage=ValidationStage.COMPLEXITY,
                    code=ViolationCode.MAX_DEPTH_EXCEEDED,
                    message=(
                        f"longest dependency path is {depth} steps, more than max_depth of "
                        f"{limits.max_depth}"
                    ),
                    limit_name=LimitName.MAX_DEPTH,
                    limit_value=limits.max_depth,
                    observed_value=depth,
                )
            )
        if oversize:
            not_evaluated.append("max_parallel_branches (the plan exceeds max_nodes)")
        else:
            width = max_antichain_width(graph)  # acyclic: the depth above was defined
            if width is not None and width > limits.max_parallel_branches:
                violations.append(
                    Violation(
                        stage=ValidationStage.COMPLEXITY,
                        code=ViolationCode.MAX_PARALLEL_BRANCHES_EXCEEDED,
                        message=(
                            f"plan allows {width} mutually independent steps at once, more than "
                            f"max_parallel_branches of {limits.max_parallel_branches}"
                        ),
                        limit_name=LimitName.MAX_PARALLEL_BRANCHES,
                        limit_value=limits.max_parallel_branches,
                        observed_value=width,
                    )
                )

    detail = "not evaluated: " + "; ".join(not_evaluated) if not_evaluated else None
    if violations:
        return StageResult(
            stage=ValidationStage.COMPLEXITY,
            status=StageStatus.FAILED,
            violations=tuple(violations),
            detail=detail,
        )
    if not_evaluated:
        return StageResult(stage=ValidationStage.COMPLEXITY, status=StageStatus.SKIPPED, detail=detail)
    return StageResult(stage=ValidationStage.COMPLEXITY, status=StageStatus.PASSED)
