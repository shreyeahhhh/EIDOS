"""Factories and scripted ports for V0.3 runtime tests.

The doubles here are deliberately dumb: they return what a test scripted, and they
*record* what they were asked — which is how tests prove a node was (or was not)
dispatched, and in what order. They are test support, so they may hold mutable
recordings; nothing under ``src/eidos/runtime`` may.

Nothing here names a model, provider or agent. A scripted work executor is keyed by
step id, because that is what a test wants to control; the runtime itself only ever
sees a requested capability.
"""

from uuid import UUID

from eidos.compiler import CompiledPlan, compile_plan
from eidos.contracts import ExecutionId, PlanStepKind, ReliabilityContractId, StepId
from eidos.runtime import (
    AdmissionDecision,
    AdmissionRequest,
    ExecutionContext,
    NodeResult,
    NodeStatus,
    SequentialExecutor,
    VerificationResult,
    WorkResult,
)

from eidos_compiler_factories import forged_accepted_report
from eidos_factories import (
    make_agent_step,
    make_control_step,
    make_plan,
    make_reliability_contract,
    make_task_genome,
)

EXECUTION_ID = ExecutionId(UUID(int=9))


def compiled_of(spec: dict[str, str], *, verify: tuple[str, ...] = (), **plan_overrides) -> CompiledPlan:
    """Compile ``{"name": "dep1 dep2"}`` in dict order. Names in ``verify`` are VERIFY steps."""
    steps = []
    for name, deps in spec.items():
        depends_on = tuple(StepId(d) for d in deps.split())
        if name in verify:
            steps.append(make_control_step(step_id=StepId(name), depends_on=depends_on, kind=PlanStepKind.VERIFY))
        else:
            steps.append(make_agent_step(step_id=StepId(name), depends_on=depends_on))
    plan = make_plan(steps=tuple(steps), **plan_overrides)
    report = compile_plan(plan, forged_accepted_report(plan))
    assert report.succeeded, [v.message for v in report.violations]
    return report.compiled


def context_for(compiled: CompiledPlan, **overrides) -> ExecutionContext:
    # The contract and the genome belong to the context's tenant, so an overridden tenant carries both with it.
    contract = make_reliability_contract(
        tenant_id=overrides.get("tenant_id", compiled.tenant_id), contract_id=ReliabilityContractId(UUID(int=11))
    )
    fields = dict(
        tenant_id=compiled.tenant_id,
        mission_id=compiled.mission_id,
        execution_id=EXECUTION_ID,
        plan_id=compiled.plan_id,
        plan_version=compiled.plan_version,
        # A fixed contract id keeps the fixture deterministic: two calls give equal contexts.
        task_genome=make_task_genome(contract=contract),
        reliability_contract=contract,
    )
    fields.update(overrides)
    return ExecutionContext(**fields)


def artifact_of(step_id: str) -> str:
    return f"artifact:{step_id}"


# --- scripted ports -----------------------------------------------------------------------


class ScriptedWork:
    """A ``WorkExecutor`` that returns a scripted result per step id.

    An entry may be a ``WorkResult``, an exception (raised), or a callable
    ``(context, node) -> anything`` (returned as is — so a test can return a bad value).
    Unscripted steps produce ``artifact:<step_id>``.
    """

    def __init__(self, script: dict | None = None):
        self.script = dict(script or {})
        self.calls: list[str] = []
        self.contexts: list[ExecutionContext] = []
        self.nodes: list = []

    def execute(self, context, node):
        self.calls.append(node.step_id)
        self.contexts.append(context)
        self.nodes.append(node)
        entry = self.script.get(node.step_id)
        if entry is None:
            return WorkResult.produced(artifact_of(node.step_id))
        if isinstance(entry, BaseException):
            raise entry
        if callable(entry):
            return entry(context, node)
        return entry


class ScriptedVerifier:
    """A ``Verifier`` that returns a scripted verdict per step id (default: PASS)."""

    def __init__(self, script: dict | None = None):
        self.script = dict(script or {})
        self.calls: list[str] = []
        self.received: list[tuple] = []
        self.contexts: list[ExecutionContext] = []

    def verify(self, context, node, predecessors):
        self.calls.append(node.step_id)
        self.received.append(predecessors)
        self.contexts.append(context)
        entry = self.script.get(node.step_id)
        if entry is None:
            return VerificationResult.passed("verified")
        if isinstance(entry, BaseException):
            raise entry
        if callable(entry):
            return entry(context, node, predecessors)
        return entry


class RecordingGuard:
    """An ``AdmissionGuard`` defined by a pure function of the request; records every request."""

    def __init__(self, decide=None):
        self.decide = decide or (lambda request: AdmissionDecision.admit())
        self.requests: list[AdmissionRequest] = []

    def admit(self, request):
        self.requests.append(request)
        return self.decide(request)

    def asked(self) -> list[tuple]:
        return [(r.step_id, r.level, r.rank_in_level, r.dispatched_before_level) for r in self.requests]


def admit_all() -> RecordingGuard:
    return RecordingGuard()


def halt_when(predicate, reason: str = "budget exhausted") -> RecordingGuard:
    return RecordingGuard(
        lambda request: AdmissionDecision.halt(reason) if predicate(request) else AdmissionDecision.admit()
    )


class RaisingGuard:
    def admit(self, request):
        raise RuntimeError("guard is broken")


class JunkGuard:
    def __init__(self, value=None):
        self.value = value

    def admit(self, request):
        return self.value


def make_executor(work=None, verifier=None, guard=None) -> SequentialExecutor:
    return SequentialExecutor(
        work_executor=work or ScriptedWork(),
        verifier=verifier or ScriptedVerifier(),
        admission_guard=guard or admit_all(),
    )


def statuses(result) -> dict:
    """``step_id -> status value`` in plan order."""
    return {r.step_id: r.status.value for r in result.results}


def succeeded_result(step_id: str, *, verify: bool = False) -> NodeResult:
    if verify:
        return NodeResult(
            step_id=StepId(step_id), kind=PlanStepKind.VERIFY, status=NodeStatus.SUCCEEDED, reason="verified"
        )
    return NodeResult(
        step_id=StepId(step_id),
        kind=PlanStepKind.AGENT,
        status=NodeStatus.SUCCEEDED,
        artifact=artifact_of(step_id),
    )
