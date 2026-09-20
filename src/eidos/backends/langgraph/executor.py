"""The LangGraph execution backend — the only module in EIDOS that imports LangGraph.

decisions.md: D-113 (MissionState never enters LangGraph state; LangGraph state contains only
``outcomes``, a mapping from step id to node outcome; a run receives a frozen
``ExecutionContext``), D-115 (this package is the sole importer of LangGraph; the compiler and the
runtime are backend-neutral), D-116 (LangGraph is an optional extra), D-117 (level-synchronous
execution), D-118, D-119, D-120, D-121, D-122, D-123, D-127 (no LangGraph checkpointing, interrupts
or retry), D-128 (the sequential reference executor is the semantic oracle this backend is held to).

``LangGraphExecutor.run(compiled, context, prior)`` has the same signature and the same contract as
``SequentialExecutor.run``: for the same compiled plan, context, prior outcomes and deterministic
ports it returns an equal ``RunResult`` or ``RunRejection``. LangGraph supplies the *mechanics*
(scheduling, parallel branches, the join of a node's predecessors). It supplies no semantics: every
decision about what a node does is EIDOS's, made by the same rules as the reference executor.

How the EIDOS model maps onto LangGraph
---------------------------------------
- One LangGraph node per compiled node, named by plan position (``n0``, ``n1``, ...) so an arbitrary
  step id can never collide with a reserved LangGraph name. Roots hang off ``START``; a node with one
  predecessor has a plain edge; a node with several has one list-form edge, which LangGraph fires only
  once all of them have completed. The compiled plan's edges are the graph's edges; nothing is added.
- LangGraph's super-steps *are* EIDOS's levels. A node runs in the super-step after its last
  predecessor completes, which is exactly ``level = 1 + max(predecessor levels)``. Every node runs its
  wrapper — a skipped or halted node too — so successors always trigger and the level barrier holds.
- The graph state is ``outcomes`` and nothing else (D-113). Nodes of one super-step read the state as
  it stood at the start of the step and never see each other's writes; each node writes only its own
  key, so the merge is order-independent and a key written twice is a fault.
- The frozen context, the compiled plan and the three ports are closed over by the node wrappers. They
  are never in the graph state, so MissionState cannot be there, and there is no checkpointer, no
  ``thread_id``, no interrupt and no LangGraph retry policy (D-127): a port that fails is recorded as
  ``FAILED`` by the wrapper and never reaches LangGraph.
- Tracing is forced off. LangGraph's dependency LangSmith exports run data to a third party when the
  environment says so; an ambient setting must never do that to a mission's data, so every invocation runs
  inside ``tracing_context(enabled=False)``.

Everything a wrapper needs is a pure function of that start-of-step snapshot and the static plan, so the
guard's answers do not depend on scheduling: ``rank_in_level`` is counted from the outcomes of earlier
levels, ``dispatched_before_level`` from the outcomes already recorded, and whether the run has halted
from any ``NOT_REACHED`` outcome already recorded. Dispatch order, the halt and the outcome are derived
from the final outcomes and the plan, never from completion order.

Threading: LangGraph runs the nodes of one level concurrently on worker threads, so the three ports
must be safe to call concurrently. The result does not depend on which finishes first (D-117).

Cost: each wrapper scans the recorded outcomes, so a run is quadratic in the node count in the worst
case. Plans are bounded by ``max_nodes`` (V0.2), so this is a bound, not a scaling target.

A fault in this backend or in LangGraph itself raises ``BackendError``. It is never used for anything a
run can legitimately produce.
"""

from dataclasses import dataclass
from typing import Annotated, TypedDict

try:
    from langgraph.errors import GraphRecursionError  # noqa: F401  (named so a fault is recognisable)
    from langgraph.graph import START, StateGraph
    from langsmith import tracing_context  # a dependency of LangGraph; used only to switch tracing off
except ImportError as error:  # the optional extra is not installed (D-116)
    raise ImportError(
        "eidos.backends.langgraph needs the optional 'langgraph' extra: pip install 'eidos[langgraph]'"
    ) from error

from pydantic import ValidationError

from eidos.compiler import CompiledPlan, VerifyNode, WorkNode
from eidos.contracts import StepId
from eidos.runtime import (
    AdmissionDecision,
    AdmissionGuard,
    AdmissionOutcome,
    AdmissionRequest,
    ExecutionContext,
    HaltInfo,
    NodeResult,
    NodeStatus,
    PriorOutcomes,
    RunOutcome,
    RunRejection,
    RunResult,
    VerificationResult,
    VerificationVerdict,
    Verifier,
    WorkExecutor,
    WorkResult,
    WorkStatus,
    check_run_preconditions,
)

from .errors import BackendError

_Node = WorkNode | VerifyNode

# The reason a node carries when the guard denied it. The halt is derived from the recorded outcomes,
# so this text is the one place the guard's reason survives; conformance tests pin it to the reference.
_DENIED_PREFIX = "admission halted the run at this node: "

# LangGraph counts one step of overhead beyond the plan's depth (measured, not assumed: the minimum
# limit for a chain of n nodes is n + 1). One further step is margin. The plan is a validated acyclic
# DAG, so slack here cannot make anything loop; it only prevents a spurious GraphRecursionError.
_RECURSION_OVERHEAD = 2


def _recursion_limit(compiled: CompiledPlan) -> int:
    """Super-steps the run may take: the plan's depth, computed from the compiled levels."""
    return max(node.level for node in compiled.nodes) + _RECURSION_OVERHEAD


# --- the graph state: outcomes, and nothing else (D-113) ------------------------------------------


def _merge_outcomes(
    current: dict[StepId, NodeResult], update: dict[StepId, NodeResult]
) -> dict[StepId, NodeResult]:
    """Combine writes. Each node writes only its own key, so order cannot matter; a repeat is a fault."""
    for step_id in update:
        if step_id in current:
            raise ValueError(f"an outcome for step {step_id!r} was written twice")
    return {**current, **update}


class _RunState(TypedDict):
    outcomes: Annotated[dict[StepId, NodeResult], _merge_outcomes]


@dataclass(frozen=True, slots=True)
class _Layout:
    """Static facts about one run, closed over by the node wrappers. Read-only lookups."""

    by_level: tuple[tuple[_Node, ...], ...]  # index is level - 1; each level in plan order
    level_of: dict[StepId, int]
    prior_ids: dict[StepId, None]  # steps already settled by prior outcomes; membership only


@dataclass(frozen=True, slots=True, kw_only=True)
class LangGraphExecutor:
    """Runs a compiled plan on LangGraph, under the same semantics as ``SequentialExecutor``.

    Holds only its three ports, all required: there is no default guard and no ambient configuration.
    It keeps no state between runs and builds a fresh graph for every run.
    """

    work_executor: WorkExecutor
    verifier: Verifier
    admission_guard: AdmissionGuard

    def run(
        self,
        compiled: CompiledPlan,
        context: ExecutionContext,
        prior: PriorOutcomes | None = None,
    ) -> RunResult | RunRejection:
        """Execute ``compiled``, or return the typed reason the run may not start.

        Never mutates ``compiled``, ``context`` or ``prior``. Raises ``BackendError`` only for a
        fault in this backend or in LangGraph — never for a port, a plan, a context or a prior.
        """
        rejection = check_run_preconditions(compiled, context, prior)
        if rejection is not None:
            return rejection

        if not compiled.nodes:
            # LangGraph cannot compile a graph with no entry point, and there is nothing to run.
            return _run_result(compiled, context, RunOutcome.FINISHED, None, (), ())

        layout = _layout(compiled, prior)
        graph = self._build_graph(compiled, context, layout)
        initial = {"outcomes": {outcome.step_id: outcome for outcome in prior.outcomes} if prior else {}}
        try:
            # An ambient LANGSMITH_TRACING / LANGCHAIN_TRACING_V2 would otherwise make LangGraph POST every
            # node's inputs and outputs — outcomes, artifacts, reasons — to a third-party service. A run
            # never depends on the environment for that, so tracing is forced off for the whole invocation,
            # worker threads included (verified: tests/integration/langgraph).
            with tracing_context(enabled=False):
                final = graph.invoke(initial, {"recursion_limit": _recursion_limit(compiled)})
        except Exception as error:  # ports never raise into LangGraph, so this is a backend fault
            raise BackendError(f"the LangGraph backend failed: {type(error).__name__}: {error}") from error
        return _assemble(compiled, context, layout, final["outcomes"])

    # --- graph construction -------------------------------------------------------------------------

    def _build_graph(self, compiled: CompiledPlan, context: ExecutionContext, layout: _Layout):
        names = {node.step_id: f"n{node.position}" for node in compiled.nodes}  # lookup only
        builder = StateGraph(_RunState)
        for node in compiled.nodes:
            builder.add_node(names[node.step_id], self._node_function(node, context, layout))
        for node in compiled.nodes:
            if not node.predecessors:
                builder.add_edge(START, names[node.step_id])
            elif len(node.predecessors) == 1:
                builder.add_edge(names[node.predecessors[0]], names[node.step_id])
            else:  # fires once, after every predecessor has completed
                builder.add_edge([names[p] for p in node.predecessors], names[node.step_id])
        return builder.compile()  # no checkpointer: nothing is persisted (D-127)

    def _node_function(self, node: _Node, context: ExecutionContext, layout: _Layout):
        def run_node(state: _RunState) -> dict:
            result = self._settle(node, context, layout, state["outcomes"])
            return {} if result is None else {"outcomes": {node.step_id: result}}

        return run_node

    # --- one node's decision: the reference executor's rules, from a start-of-step snapshot -------------

    def _settle(
        self,
        node: _Node,
        context: ExecutionContext,
        layout: _Layout,
        outcomes: dict[StepId, NodeResult],
    ) -> NodeResult | None:
        """The node's outcome, or ``None`` if prior outcomes already settled it."""
        if node.step_id in layout.prior_ids:
            return None  # carried over untouched; never dispatched (D-120)

        halted_at = _halt_level(outcomes, layout.level_of)
        if halted_at is not None:  # a halt at an earlier level: this node's level is never reached
            return NodeResult(
                step_id=node.step_id,
                kind=node.kind,
                status=NodeStatus.NOT_REACHED,
                reason=f"the run halted after level {halted_at}, before this node's level",
            )

        blockers = [p for p in node.predecessors if outcomes[p].status is not NodeStatus.SUCCEEDED]
        if blockers:
            return _skipped(node, blockers, outcomes)

        decision = self._ask_guard(
            AdmissionRequest(
                step_id=node.step_id,
                level=node.level,
                rank_in_level=_rank_in_level(node, layout, outcomes),
                dispatched_before_level=_dispatched_count(outcomes, layout.prior_ids),
            )
        )
        if decision.outcome is AdmissionOutcome.HALT:
            return NodeResult(
                step_id=node.step_id,
                kind=node.kind,
                status=NodeStatus.NOT_REACHED,
                reason=f"{_DENIED_PREFIX}{decision.reason}",
            )
        if isinstance(node, WorkNode):
            return self._dispatch_work(context, node)
        return self._dispatch_verify(context, node, outcomes)

    # --- ports, with faults contained (the same rules as the reference executor) ------------------------

    def _ask_guard(self, request: AdmissionRequest) -> AdmissionDecision:
        """Fails closed: a guard that raises or answers with anything else halts the run."""
        try:
            decision = self.admission_guard.admit(request)
        except Exception as error:
            return AdmissionDecision.halt(f"the admission guard raised {_describe(error)}")
        if not isinstance(decision, AdmissionDecision):
            return AdmissionDecision.halt(
                f"the admission guard returned {type(decision).__name__}, not an AdmissionDecision"
            )
        return decision

    def _dispatch_work(self, context: ExecutionContext, node: WorkNode) -> NodeResult:
        try:
            result = self.work_executor.execute(context, node)
        except Exception as error:
            return _failed(node, f"the work executor raised {_describe(error)}")
        if not isinstance(result, WorkResult):
            return _failed(
                node, f"the work executor returned {type(result).__name__}, not a WorkResult"
            )
        if result.status is WorkStatus.PRODUCED:
            return NodeResult(
                step_id=node.step_id, kind=node.kind, status=NodeStatus.SUCCEEDED, artifact=result.artifact
            )
        status = NodeStatus.FAILED if result.status is WorkStatus.FAILED else NodeStatus.NO_RESULT
        return NodeResult(step_id=node.step_id, kind=node.kind, status=status, reason=result.reason)

    def _dispatch_verify(
        self, context: ExecutionContext, node: VerifyNode, outcomes: dict[StepId, NodeResult]
    ) -> NodeResult:
        predecessors = tuple(outcomes[p] for p in node.predecessors)
        try:
            result = self.verifier.verify(context, node, predecessors)
        except Exception as error:
            return _failed(node, f"the verifier raised {_describe(error)}")
        if not isinstance(result, VerificationResult):
            return _failed(
                node, f"the verifier returned {type(result).__name__}, not a VerificationResult"
            )
        status = {
            VerificationVerdict.PASS: NodeStatus.SUCCEEDED,
            VerificationVerdict.FAIL: NodeStatus.VERIFICATION_FAILED,
            VerificationVerdict.INCONCLUSIVE: NodeStatus.VERIFICATION_INCONCLUSIVE,
        }[result.verdict]
        return NodeResult(step_id=node.step_id, kind=node.kind, status=status, reason=result.reason)


# --- facts derived from the start-of-step snapshot ---------------------------------------------------------


def _layout(compiled: CompiledPlan, prior: PriorOutcomes | None) -> _Layout:
    depth = max(node.level for node in compiled.nodes)
    levels: list[list[_Node]] = [[] for _ in range(depth)]
    for node in compiled.nodes:
        levels[node.level - 1].append(node)  # plan order within each level
    return _Layout(
        by_level=tuple(tuple(level) for level in levels),
        level_of={node.step_id: node.level for node in compiled.nodes},
        prior_ids={outcome.step_id: None for outcome in prior.outcomes} if prior else {},
    )


def _halt_level(outcomes: dict[StepId, NodeResult], level_of: dict[StepId, int]) -> int | None:
    """The level at which the run halted, if any node already recorded is ``NOT_REACHED``."""
    levels = [level_of[step_id] for step_id, result in outcomes.items() if result.status is NodeStatus.NOT_REACHED]
    return min(levels) if levels else None


def _rank_in_level(node: _Node, layout: _Layout, outcomes: dict[StepId, NodeResult]) -> int:
    """Nodes of this level, earlier in plan order, that will be put to the guard: not settled by
    prior outcomes, and with every predecessor succeeded."""
    return sum(
        1
        for other in layout.by_level[node.level - 1]
        if other.position < node.position
        and other.step_id not in layout.prior_ids
        and all(outcomes[p].status is NodeStatus.SUCCEEDED for p in other.predecessors)
    )


def _dispatched_count(outcomes: dict[StepId, NodeResult], prior_ids: dict[StepId, None]) -> int:
    """Nodes dispatched so far in this run: recorded, not carried over from prior, and actually run."""
    return sum(
        1
        for step_id, result in outcomes.items()
        if step_id not in prior_ids
        and result.status not in (NodeStatus.SKIPPED, NodeStatus.NOT_REACHED)
    )


def _skipped(node: _Node, blockers: list[StepId], outcomes: dict[StepId, NodeResult]) -> NodeResult:
    listed = ", ".join(f"{blocker!r} ({outcomes[blocker].status.value})" for blocker in blockers)
    return NodeResult(
        step_id=node.step_id,
        kind=node.kind,
        status=NodeStatus.SKIPPED,
        reason=f"not dispatched: predecessor(s) did not succeed: {listed}",
    )


def _failed(node: _Node, reason: str) -> NodeResult:
    return NodeResult(step_id=node.step_id, kind=node.kind, status=NodeStatus.FAILED, reason=reason)


def _describe(error: Exception) -> str:
    text = str(error)
    return f"{type(error).__name__}: {text}" if text else type(error).__name__


# --- the RunResult, derived from the final outcomes and the plan — never from completion order ---------------


def _assemble(
    compiled: CompiledPlan,
    context: ExecutionContext,
    layout: _Layout,
    outcomes: dict[StepId, NodeResult],
) -> RunResult:
    try:
        results = tuple(outcomes[node.step_id] for node in compiled.nodes)
    except KeyError as error:
        raise BackendError(f"the graph finished without an outcome for step {error.args[0]!r}") from error

    ordered = sorted(compiled.nodes, key=lambda node: (node.level, node.position))  # dispatch order
    dispatched = tuple(
        node.step_id
        for node in ordered
        if node.step_id not in layout.prior_ids
        and outcomes[node.step_id].status not in (NodeStatus.SKIPPED, NodeStatus.NOT_REACHED)
    )
    halt = _halt_info(ordered, outcomes)
    if halt is not None:
        outcome = RunOutcome.HALTED
    elif all(result.status is NodeStatus.SUCCEEDED for result in results):
        outcome = RunOutcome.FINISHED
    else:
        outcome = RunOutcome.FAILED
    return _run_result(compiled, context, outcome, halt, results, dispatched)


def _halt_info(ordered: list[_Node], outcomes: dict[StepId, NodeResult]) -> HaltInfo | None:
    """The first denied node: the lowest level's, then the earliest in plan order.

    Nodes of a later level that are ``NOT_REACHED`` only because the run had halted have a higher level,
    so the first ``NOT_REACHED`` node in (level, position) order is always a node the guard denied.
    """
    for node in ordered:
        result = outcomes[node.step_id]
        if result.status is NodeStatus.NOT_REACHED:
            if result.reason is None or not result.reason.startswith(_DENIED_PREFIX):
                raise BackendError(f"the first not-reached node {node.step_id!r} was not a guard denial")
            return HaltInfo(step_id=node.step_id, level=node.level, reason=result.reason[len(_DENIED_PREFIX):])
    return None


def _run_result(compiled, context, outcome, halt, results, dispatched) -> RunResult:
    try:
        return RunResult(
            tenant_id=compiled.tenant_id,
            mission_id=compiled.mission_id,
            execution_id=context.execution_id,
            plan_id=compiled.plan_id,
            plan_version=compiled.plan_version,
            outcome=outcome,
            halt=halt,
            results=results,
            dispatched=dispatched,
        )
    except ValidationError as error:
        raise BackendError(f"the backend assembled an inconsistent run: {error}") from error
