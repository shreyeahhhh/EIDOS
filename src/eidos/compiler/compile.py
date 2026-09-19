"""compile_plan — the deterministic boundary from a validated Plan to its compiled form.

decisions.md: D-112 (compile only ``agent`` and ``VERIFY``; reject the rest),
D-114 (input is a ``Plan`` plus an accepted ``PlanValidationReport``; the
compiler re-checks the structural properties it depends on and stays a separate
authority from V0.2), D-115 (backend-neutral: imports no runtime and no
execution backend), D-117 (``level`` counts nodes on the longest predecessor chain),
D-123 (writes nothing to MissionState, emits nothing).

``compile_plan`` never raises for an invalid plan or report; it returns a
``CompileReport``. It never repairs, drops or transforms a step: a plan with any
violation yields no compiled form at all, never a partial one.

What it checks, and what it does not:

- Evidence: a report is present, accepted, and for this plan. The report binds
  to a plan only by ``plan_id``, so this is evidence, not proof (D-114).
- Structure the compiler itself depends on: unique step ids, resolved
  dependencies, no dependency cycle. Re-checked here rather than trusted, because
  a ``Plan`` can be produced without validation (``model_copy(update=...)``).
- Representability: every step is an ``agent`` or a ``VERIFY`` step.
- It does **not** re-check capabilities, resource ceilings, complexity limits or
  policy. Those are V0.2's responsibilities and it has neither the mission nor
  the limits to do them.

Determinism: every ordering derives from ``Plan.steps`` order; dicts are used for
lookup only and are never iterated to produce output.
"""

from collections import deque
from enum import Enum

from eidos.contracts import AgentStep, ControlStep, Plan, PlanStepKind, StepId
from eidos.validation import PlanValidationReport

from .ir import CompiledNode, CompiledPlan, VerifyNode, WorkNode
from .results import CompileFailureCode, CompileReport, CompileViolation


class _Shape(Enum):
    WORK = "work"
    VERIFY = "verify"
    UNSUPPORTED = "unsupported"
    MALFORMED = "malformed"


def compile_plan(plan: Plan, validation_report: PlanValidationReport | None) -> CompileReport:
    """Compile ``plan``, or report exactly why it cannot be compiled."""
    shapes = tuple(_classify(step) for step in plan.steps)
    dependency_violations, levels = _analyse_dependencies(plan)

    violations = (
        *_evidence_violations(plan, validation_report),
        *dependency_violations,
        *_step_violations(plan, shapes),
    )
    if violations or levels is None:
        return CompileReport(plan_id=plan.plan_id, violations=violations)

    nodes: list[CompiledNode] = []
    for position, step in enumerate(plan.steps):
        common = dict(
            step_id=step.step_id,
            position=position,
            level=levels[position],
            predecessors=tuple(dict.fromkeys(step.depends_on)),  # a repeated entry is one edge
        )
        if shapes[position] is _Shape.WORK:
            nodes.append(WorkNode(capability=step.capability, **common))
        else:
            nodes.append(VerifyNode(**common))

    compiled = CompiledPlan(
        tenant_id=plan.tenant_id,
        mission_id=plan.mission_id,
        plan_id=plan.plan_id,
        plan_version=plan.version,
        nodes=tuple(nodes),
    )
    return CompileReport(plan_id=plan.plan_id, compiled=compiled)


# --- evidence ---------------------------------------------------------------------


def _evidence_violations(
    plan: Plan, report: PlanValidationReport | None
) -> list[CompileViolation]:
    if not isinstance(report, PlanValidationReport):
        return [
            CompileViolation(
                code=CompileFailureCode.MISSING_VALIDATION,
                message=(
                    "no PlanValidationReport was supplied; compilation requires an accepted "
                    "validation report (D-114)"
                ),
            )
        ]
    violations: list[CompileViolation] = []
    if not report.accepted:
        violations.append(
            CompileViolation(
                code=CompileFailureCode.VALIDATION_NOT_ACCEPTED,
                message=(
                    "the validation report is not accepted (a stage failed or did not run); "
                    "compilation requires an accepted report (D-114)"
                ),
            )
        )
    if report.plan_id != plan.plan_id:
        reported = "no plan" if report.plan_id is None else f"plan {str(report.plan_id)!r}"
        violations.append(
            CompileViolation(
                code=CompileFailureCode.VALIDATION_PLAN_MISMATCH,
                message=(
                    f"the validation report is for {reported}, not for plan {str(plan.plan_id)!r}"
                ),
            )
        )
    return violations


# --- structure the compiler depends on ----------------------------------------------


def _analyse_dependencies(plan: Plan) -> tuple[list[CompileViolation], list[int] | None]:
    """Violations, plus each step's level (by position) when the graph is sound.

    Levels are computed by a Kahn pass, which also finds cycles: a step never
    settled is on a cycle or downstream of one.
    """
    violations: list[CompileViolation] = []
    position_of: dict[StepId, int] = {}  # lookup only
    reported_duplicates: dict[StepId, None] = {}  # membership only
    for position, step in enumerate(plan.steps):
        if step.step_id in position_of:
            if step.step_id not in reported_duplicates:
                reported_duplicates[step.step_id] = None
                violations.append(
                    CompileViolation(
                        code=CompileFailureCode.DUPLICATE_STEP_ID,
                        message=f"step_id {step.step_id!r} is used by more than one step",
                        step_ids=(step.step_id,),
                    )
                )
        else:
            position_of[step.step_id] = position

    for step in plan.steps:
        reported: dict[StepId, None] = {}
        for dependency in step.depends_on:
            if dependency not in position_of and dependency not in reported:
                reported[dependency] = None
                violations.append(
                    CompileViolation(
                        code=CompileFailureCode.UNKNOWN_DEPENDENCY,
                        message=f"step {step.step_id!r} depends on unknown step {dependency!r}",
                        step_ids=(step.step_id,),
                    )
                )
    if violations:
        return violations, None  # the graph is undefined; do not look for cycles in it

    predecessors = [
        list(dict.fromkeys(position_of[dep] for dep in step.depends_on)) for step in plan.steps
    ]
    levels, unsettled = _levels(predecessors)
    if unsettled:
        listed = ", ".join(repr(plan.steps[i].step_id) for i in unsettled)
        violations.append(
            CompileViolation(
                code=CompileFailureCode.DEPENDENCY_CYCLE,
                message=f"steps {listed} are on, or downstream of, a dependency cycle",
                step_ids=tuple(plan.steps[i].step_id for i in unsettled),
            )
        )
        return violations, None
    return violations, levels


def _levels(predecessors: list[list[int]]) -> tuple[list[int], list[int]]:
    """Kahn's algorithm. Returns each step's level and the steps that never settled.

    A step's level is ``1 + max(predecessor levels)``, or 1 for a root. The result
    does not depend on processing order; unsettled steps are returned in plan order.
    """
    count = len(predecessors)
    remaining = [len(p) for p in predecessors]
    successors: list[list[int]] = [[] for _ in range(count)]
    for step, preds in enumerate(predecessors):
        for pred in preds:
            successors[pred].append(step)

    levels = [0] * count
    settled = [False] * count
    queue = deque(step for step in range(count) if remaining[step] == 0)
    while queue:
        step = queue.popleft()
        settled[step] = True
        levels[step] = 1 + max((levels[p] for p in predecessors[step]), default=0)
        for successor in successors[step]:
            remaining[successor] -= 1
            if remaining[successor] == 0:
                queue.append(successor)
    return levels, [step for step in range(count) if not settled[step]]


# --- representability -----------------------------------------------------------------


def _classify(step: object) -> _Shape:
    """Which compiled node a step becomes, or why it cannot become one.

    Default-deny: a control kind that is not ``VERIFY`` is unsupported, so a kind
    added to ``PlanStepKind`` later is rejected until it is deliberately supported.
    """
    if isinstance(step, AgentStep):
        if step.kind is PlanStepKind.AGENT and isinstance(step.capability, str):
            return _Shape.WORK
        return _Shape.MALFORMED
    if isinstance(step, ControlStep):
        if step.kind is PlanStepKind.VERIFY:
            return _Shape.VERIFY
        if isinstance(step.kind, PlanStepKind) and step.kind is not PlanStepKind.AGENT:
            return _Shape.UNSUPPORTED
    return _Shape.MALFORMED


def _step_violations(plan: Plan, shapes: tuple[_Shape, ...]) -> list[CompileViolation]:
    violations: list[CompileViolation] = []
    for step, shape in zip(plan.steps, shapes):
        if shape is _Shape.UNSUPPORTED:
            violations.append(
                CompileViolation(
                    code=CompileFailureCode.UNSUPPORTED_STEP_KIND,
                    message=(
                        f"step {step.step_id!r} has kind {step.kind.value!r}, which V0.3 does "
                        f"not compile (D-112): {_unsupported_reason(step.kind)}"
                    ),
                    step_ids=(step.step_id,),
                    step_kind=step.kind,
                )
            )
        elif shape is _Shape.MALFORMED:
            violations.append(
                CompileViolation(
                    code=CompileFailureCode.MALFORMED_STEP,
                    message=(
                        f"step {step.step_id!r} is not a well-formed plan step: its kind and "
                        "shape disagree, which a validly constructed Plan cannot produce"
                    ),
                    step_ids=(step.step_id,),
                )
            )
    return violations


def _unsupported_reason(kind: PlanStepKind) -> str:
    if kind is PlanStepKind.HUMAN_APPROVAL:
        return "it is not compiled in V0.3 (D-124), and whether it is a work step stays open (D-055)"
    if kind is PlanStepKind.RETRY:
        return (
            "it is conditional and no predicate language exists (D-012, Open), and how it relates "
            "to a runtime retry policy is undecided (D-125)"
        )
    return "it is conditional and no predicate language exists (D-012, Open)"
