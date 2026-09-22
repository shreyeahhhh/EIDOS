"""``check_feasibility`` — the deterministic feasibility gate (decisions.md D-178 to D-182; V0.7 Step 4).

**Strategy feasibility is not Plan validation.** A ``Strategy`` has no ``StepId``, no dependency edge, no concrete
node — so SCHEMA, DEPENDENCY, CYCLE and POLICY (V0.2's other four stages) have nothing to check here, and this
module does not run them, duplicate them, or import the functions that do (``eidos.validation.stages`` is never
imported; only ``eidos.validation.limits`` — plain ceiling numbers, not validation logic — and ``eidos.contracts``
are). The eventual concrete ``Plan`` a selected strategy expands into (V0.8+, not built) still goes through the
complete, unmodified V0.2 pipeline and V0.3 compiler — this gate never grants a shortcut around either.

**Three checks, each a narrower, strategy-level analogue of an existing V0.2 stage — D-180's own approved reuse,
no new numeric limit invented anywhere:**

1. **CAPABILITY** (a narrower analogue of V0.2's own capability stage): every capability named in any stage must
   be one of ``task_genome.required_capabilities`` (D-102's own mission-scoped set). **The converse is not
   required** — a mission may declare a capability no particular candidate happens to use, exactly the asymmetry
   V0.2's own capability stage already documents for ``Plan``.
2. **COMPLEXITY** (a narrower analogue of V0.2's own complexity stage): the number of stages against ``max_depth``,
   the widest single stage against ``max_parallel_branches``, and the total capability occurrences across every
   stage against ``max_nodes``. These are **strategy-level estimates** — a stage is not yet a concrete node, and
   ``verification`` is not counted (unlike a real, compiled ``VERIFY`` node would be) — the real ``Plan`` a
   selected strategy expands into is checked exactly, for real, later, unchanged.
3. **RESOURCE** (a narrower analogue of V0.2's own resource stage): the same total capability occurrences against
   the *effective* ``max_agent_calls`` — ``min(system ceiling, contract value)``, or the ceiling alone when the
   contract omits it — the identical formula V0.2's own resource stage already uses. At the ``Plan`` level,
   COMPLEXITY's node count and RESOURCE's declared-agent-step count differ (a compiled plan can hold non-agent
   nodes, e.g. ``VERIFY``); at the ``Strategy`` level every stage entry *is* a capability occurrence, so the same
   total legitimately feeds both checks — not a shortcut, a fact about what a ``Strategy`` can currently represent
   (D-179).

**Typed violations, never a bare bool, never raised for ordinary infeasibility** — mirrors
``eidos.validation.results``'s own design rule almost verbatim: a violation's ``code`` and its ``check`` are
cross-validated so a mislabelled report is unconstructible, not merely wrong. ``check_feasibility`` trusts its
``strategy`` argument is already a valid, pydantic-constructed ``Strategy`` (the same convention every V0.2 stage
function already follows for ``Plan`` — it does not re-validate the type of what it is handed).
"""

from enum import StrEnum

from pydantic import Field, model_validator

from eidos.contracts import CapabilityId, EidosModel, ReliabilityContract, StrategyId, TaskGenome
from eidos.validation.limits import LimitName, SystemLimits

from .strategy import Strategy


class FeasibilityCheck(StrEnum):
    """The three strategy-level analogues D-180 approves. Enum definition order is check order."""

    CAPABILITY = "capability"
    COMPLEXITY = "complexity"
    RESOURCE = "resource"


class FeasibilityViolationCode(StrEnum):
    """Closed set of reasons a Strategy is infeasible. Deliberately a separate, narrower vocabulary from
    ``eidos.validation.results.ViolationCode`` — most of that enum's members (schema, dependency, cycle) describe
    a concrete ``Plan``'s own document shape, which a ``Strategy`` does not have."""

    CAPABILITY_NOT_AVAILABLE = "capability_not_available"
    MAX_DEPTH_EXCEEDED = "max_depth_exceeded"
    MAX_PARALLEL_BRANCHES_EXCEEDED = "max_parallel_branches_exceeded"
    MAX_NODES_EXCEEDED = "max_nodes_exceeded"
    AGENT_CALLS_EXCEEDED = "agent_calls_exceeded"


_CHECK_OF: dict[FeasibilityViolationCode, FeasibilityCheck] = {
    FeasibilityViolationCode.CAPABILITY_NOT_AVAILABLE: FeasibilityCheck.CAPABILITY,
    FeasibilityViolationCode.MAX_DEPTH_EXCEEDED: FeasibilityCheck.COMPLEXITY,
    FeasibilityViolationCode.MAX_PARALLEL_BRANCHES_EXCEEDED: FeasibilityCheck.COMPLEXITY,
    FeasibilityViolationCode.MAX_NODES_EXCEEDED: FeasibilityCheck.COMPLEXITY,
    FeasibilityViolationCode.AGENT_CALLS_EXCEEDED: FeasibilityCheck.RESOURCE,
}

# Every code but CAPABILITY_NOT_AVAILABLE names exactly one SystemLimits dimension.
_FIXED_LIMIT: dict[FeasibilityViolationCode, LimitName] = {
    FeasibilityViolationCode.MAX_DEPTH_EXCEEDED: LimitName.MAX_DEPTH,
    FeasibilityViolationCode.MAX_PARALLEL_BRANCHES_EXCEEDED: LimitName.MAX_PARALLEL_BRANCHES,
    FeasibilityViolationCode.MAX_NODES_EXCEEDED: LimitName.MAX_NODES,
    FeasibilityViolationCode.AGENT_CALLS_EXCEEDED: LimitName.MAX_AGENT_CALLS,
}


class FeasibilityViolation(EidosModel):
    """One reason a ``Strategy`` was rejected."""

    check: FeasibilityCheck
    code: FeasibilityViolationCode
    message: str = Field(min_length=1)
    stage_index: int | None = None  # set only for CAPABILITY_NOT_AVAILABLE — a Strategy has no step_id to name
    capability: CapabilityId | None = None  # set only for CAPABILITY_NOT_AVAILABLE
    limit_name: LimitName | None = None
    limit_value: int | None = None  # the ceiling (or effective ceiling) that applied
    observed_value: int | None = None  # the strategy's own value

    @model_validator(mode="after")
    def _check_code_matches_check(self) -> "FeasibilityViolation":
        if _CHECK_OF[self.code] is not self.check:
            raise ValueError(f"code {self.code.value!r} belongs to check {_CHECK_OF[self.code].value!r}, not {self.check.value!r}")
        return self

    @model_validator(mode="after")
    def _check_field_shape(self) -> "FeasibilityViolation":
        if self.code is FeasibilityViolationCode.CAPABILITY_NOT_AVAILABLE:
            if self.capability is None or self.stage_index is None:
                raise ValueError("capability_not_available requires capability and stage_index")
            if self.limit_name is not None or self.limit_value is not None or self.observed_value is not None:
                raise ValueError("capability_not_available must not carry limit fields")
            return self
        if self.capability is not None or self.stage_index is not None:
            raise ValueError(f"code {self.code.value!r} must not carry capability or stage_index")
        if self.limit_name is not _FIXED_LIMIT[self.code]:
            raise ValueError(f"code {self.code.value!r} must name limit {_FIXED_LIMIT[self.code].value!r}")
        if self.limit_value is None or self.observed_value is None:
            raise ValueError(f"code {self.code.value!r} requires limit_value and observed_value")
        return self


class FeasibilityReport(EidosModel):
    """Every reason ``strategy_id`` was found infeasible — empty means feasible. Never a bare bool."""

    strategy_id: StrategyId
    violations: tuple[FeasibilityViolation, ...] = ()

    @property
    def feasible(self) -> bool:
        return not self.violations


def _capability_violations(strategy: Strategy, task_genome: TaskGenome) -> list[FeasibilityViolation]:
    allowed = frozenset(task_genome.required_capabilities)  # membership only, never iterated
    violations: list[FeasibilityViolation] = []
    for stage_index, stage in enumerate(strategy.stages):
        for capability in stage.capabilities:
            if capability not in allowed:
                violations.append(FeasibilityViolation(
                    check=FeasibilityCheck.CAPABILITY,
                    code=FeasibilityViolationCode.CAPABILITY_NOT_AVAILABLE,
                    message=(
                        f"stage {stage_index} names capability {capability!r}, "
                        "which is not in the mission's required_capabilities"
                    ),
                    stage_index=stage_index,
                    capability=capability,
                ))
    return violations


def _complexity_violations(strategy: Strategy, limits: SystemLimits, total_capabilities: int) -> list[FeasibilityViolation]:
    violations: list[FeasibilityViolation] = []

    stage_count = len(strategy.stages)
    if stage_count > limits.max_depth:
        violations.append(FeasibilityViolation(
            check=FeasibilityCheck.COMPLEXITY, code=FeasibilityViolationCode.MAX_DEPTH_EXCEEDED,
            message=f"strategy has {stage_count} stages, more than max_depth of {limits.max_depth}",
            limit_name=LimitName.MAX_DEPTH, limit_value=limits.max_depth, observed_value=stage_count,
        ))

    max_width = max((len(stage.capabilities) for stage in strategy.stages), default=0)
    if max_width > limits.max_parallel_branches:
        violations.append(FeasibilityViolation(
            check=FeasibilityCheck.COMPLEXITY, code=FeasibilityViolationCode.MAX_PARALLEL_BRANCHES_EXCEEDED,
            message=(
                f"strategy's widest stage runs {max_width} capabilities in parallel, "
                f"more than max_parallel_branches of {limits.max_parallel_branches}"
            ),
            limit_name=LimitName.MAX_PARALLEL_BRANCHES, limit_value=limits.max_parallel_branches, observed_value=max_width,
        ))

    if total_capabilities > limits.max_nodes:
        violations.append(FeasibilityViolation(
            check=FeasibilityCheck.COMPLEXITY, code=FeasibilityViolationCode.MAX_NODES_EXCEEDED,
            message=f"strategy allocates {total_capabilities} capability occurrences, more than max_nodes of {limits.max_nodes}",
            limit_name=LimitName.MAX_NODES, limit_value=limits.max_nodes, observed_value=total_capabilities,
        ))

    return violations


def _resource_violations(
    reliability_contract: ReliabilityContract, limits: SystemLimits, total_capabilities: int
) -> list[FeasibilityViolation]:
    ceiling = limits.ceiling(LimitName.MAX_AGENT_CALLS)
    contract_value = reliability_contract.max_agent_calls
    effective = ceiling if contract_value is None else min(ceiling, contract_value)
    if total_capabilities <= effective:
        return []
    return [FeasibilityViolation(
        check=FeasibilityCheck.RESOURCE, code=FeasibilityViolationCode.AGENT_CALLS_EXCEEDED,
        message=(
            f"strategy allocates {total_capabilities} capability occurrences, more than the effective "
            f"max_agent_calls of {effective} (system ceiling {ceiling}, contract "
            f"{'not set' if contract_value is None else contract_value})"
        ),
        limit_name=LimitName.MAX_AGENT_CALLS, limit_value=effective, observed_value=total_capabilities,
    )]


def check_feasibility(
    strategy: Strategy, task_genome: TaskGenome, reliability_contract: ReliabilityContract, limits: SystemLimits
) -> FeasibilityReport:
    """Every reason ``strategy`` is infeasible for ``task_genome`` under ``reliability_contract``/``limits`` —
    empty ``violations`` means feasible. Deterministic, side-effect free; never raises for ordinary infeasibility."""
    total_capabilities = sum(len(stage.capabilities) for stage in strategy.stages)
    violations = [
        *_capability_violations(strategy, task_genome),
        *_complexity_violations(strategy, limits, total_capabilities),
        *_resource_violations(reliability_contract, limits, total_capabilities),
    ]
    return FeasibilityReport(strategy_id=strategy.strategy_id, violations=tuple(violations))
