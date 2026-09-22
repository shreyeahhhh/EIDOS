"""The sequential reference executor — EIDOS's backend-neutral execution semantics.

decisions.md: D-117 (level-synchronous execution), D-118 (statuses and outcomes), D-119
(no automatic retry, no in-run replan; each node is dispatched at most once), D-120
(prior ``SUCCEEDED`` outcomes seed a new run and are never redispatched), D-121 (the
verifier's verdict maps to a node status; no scalar), D-122 (synchronous ports; a
required ``AdmissionGuard``), D-123 (no event, no MissionState write), D-128 (this
executor is part of V0.3), D-165 (V0.6 Step 3: a work port may report ``SUBMITTED``
instead of concluding; see points 3, 5 and 7 below — nothing protocol-specific is added
here, and no port shipped today ever returns it).

It is the reference and the oracle, not the production concurrency backend. It defines
what a run *means*; an execution backend (D-115) is later held to produce the same
``RunResult`` for the same compiled plan, context, prior and ports. It imports no
backend and knows nothing about one.

The semantics, exactly
----------------------
The compiled plan's ``level`` for each node is used as given; no other scheduling model
is computed. For each level, in order, and for each node of the level in ascending plan
position:

1. A node already settled by prior outcomes is carried over untouched and is not
   dispatched.
2. A node is *ready* when all its predecessors are settled, whatever their status. Every
   predecessor is in a lower level, so it is always settled by now.
3. If any predecessor is not ``SUCCEEDED``, the node is not dispatched, and consults no
   guard. It is settled ``SKIPPED`` if at least one predecessor has *concluded* without
   succeeding (failed, produced nothing, was itself skipped, or was never reached); it is
   settled ``NOT_REACHED`` instead if every one of them is only ``AWAITING`` or
   ``NOT_REACHED`` — genuinely unresolved rather than failed (D-165): ``SKIPPED`` would
   claim more than is known about a node whose predecessor may yet succeed.
4. Otherwise the ``AdmissionGuard`` is asked about it (rank counted among the nodes of
   this level that will be dispatched). ``ADMIT`` dispatches it; ``HALT`` leaves it
   ``NOT_REACHED``.
5. A dispatched node is invoked exactly once. A work node's result maps to ``SUCCEEDED``,
   ``FAILED``, ``NO_RESULT`` or ``AWAITING`` (D-165: the port dispatched the work and does
   not yet know the outcome); a ``VERIFY`` node's verdict maps ``PASS`` to ``SUCCEEDED``,
   ``FAIL`` to ``VERIFICATION_FAILED`` and ``INCONCLUSIVE`` to
   ``VERIFICATION_INCONCLUSIVE``.
6. Every node of the level is resolved before the next level begins. A failure never
   stops independent branches, and nothing is retried. Neither does an awaiting node
   (D-165): only the nodes that actually depend on it, directly or transitively, become
   ``NOT_REACHED``, through the ordinary readiness check in point 3 — there is no bulk
   cascade for it, unlike a halt.
7. A ``HALT`` takes effect after the current level: the other nodes of the level are still
   resolved, then every node of every later level that is not already settled by prior
   outcomes becomes ``NOT_REACHED``, and the run ends ``HALTED`` — this outranks
   everything, including one or more nodes that are independently ``AWAITING`` elsewhere
   in the same run (D-165). A run that never halts but has at least one ``AWAITING`` node
   ends ``AWAITING`` instead of ``FINISHED`` or ``FAILED``.

Faults in a port never leak: an exception from a ``WorkExecutor`` or a ``Verifier``, or a
return value that is not the port's typed result, becomes ``FAILED`` with the reason
recorded — never a pass, never an inconclusive verdict. An ``AdmissionGuard`` that raises
or returns something else **fails closed**: the node is not dispatched and the run halts.

Determinism: results are ordered by compiled plan order; dispatch order is (level, plan
position); dicts are used for lookup only and never iterated.
"""

from dataclasses import dataclass

from eidos.compiler import CompiledPlan, VerifyNode, WorkNode
from eidos.contracts import PlanStepKind, StepId

from .context import ExecutionContext
from .ports import (
    AdmissionDecision,
    AdmissionGuard,
    AdmissionOutcome,
    AdmissionRequest,
    Verifier,
    VerificationResult,
    VerificationVerdict,
    WorkExecutor,
    WorkResult,
    WorkStatus,
)
from .preconditions import check_run_preconditions
from .results import (
    AwaitingInfo,
    HaltInfo,
    NodeResult,
    NodeStatus,
    PriorOutcomes,
    RunOutcome,
    RunRejection,
    RunResult,
)

# A blocker in one of these states has not concluded — it may yet succeed — so a node behind only blockers like these is not_reached, not
# skipped (D-165, mirrored from results.py's own _UNRESOLVED_STATUSES so the executor's readiness check and RunResult's own validator agree).
_UNRESOLVED_STATUSES = (NodeStatus.AWAITING, NodeStatus.NOT_REACHED)


@dataclass(frozen=True, slots=True, kw_only=True)
class SequentialExecutor:
    """Runs a compiled plan level by level, one node at a time.

    Holds only its three ports, all required: there is no default guard and no ambient
    configuration. It keeps no state between runs.
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

        Never mutates ``compiled``, ``context`` or ``prior``, and never raises for a fault
        in a port or an invalid combination of inputs.
        """
        rejection = check_run_preconditions(compiled, context, prior)
        if rejection is not None:
            return rejection

        settled: dict[StepId, NodeResult] = {}  # lookup only; never iterated
        if prior is not None:
            for outcome in prior.outcomes:
                settled[outcome.step_id] = outcome

        levels = _nodes_by_level(compiled)
        dispatched: list[StepId] = []
        awaiting: list[AwaitingInfo] = []
        halt: HaltInfo | None = None

        for level, level_nodes in enumerate(levels, start=1):
            dispatched_before_level = len(dispatched)
            rank = 0
            for node in level_nodes:
                if node.step_id in settled:
                    continue  # carried over from prior outcomes
                blockers = [p for p in node.predecessors if settled[p].status is not NodeStatus.SUCCEEDED]
                if blockers:
                    if all(settled[p].status in _UNRESOLVED_STATUSES for p in blockers):
                        settled[node.step_id] = _not_reached_pending(node, blockers, settled)
                    else:
                        settled[node.step_id] = _skipped(node, blockers, settled)
                    continue

                decision = self._ask_guard(
                    AdmissionRequest(
                        step_id=node.step_id,
                        level=level,
                        rank_in_level=rank,
                        dispatched_before_level=dispatched_before_level,
                    )
                )
                rank += 1
                if decision.outcome is AdmissionOutcome.HALT:
                    settled[node.step_id] = NodeResult(
                        step_id=node.step_id,
                        kind=node.kind,
                        status=NodeStatus.NOT_REACHED,
                        reason=f"admission halted the run at this node: {decision.reason}",
                    )
                    if halt is None:
                        halt = HaltInfo(step_id=node.step_id, level=level, reason=decision.reason)
                    continue

                settled[node.step_id] = self._dispatch(context, node, settled)
                dispatched.append(node.step_id)
                if settled[node.step_id].status is NodeStatus.AWAITING:
                    awaiting.append(AwaitingInfo(step_id=node.step_id, level=level, reason=settled[node.step_id].reason))

            if halt is not None:
                for later_nodes in levels[level:]:  # the levels after this one (level is 1-based)
                    for node in later_nodes:
                        if node.step_id not in settled:
                            settled[node.step_id] = NodeResult(
                                step_id=node.step_id,
                                kind=node.kind,
                                status=NodeStatus.NOT_REACHED,
                                reason=f"the run halted after level {level}, before this node's level",
                            )
                break

        results = tuple(settled[node.step_id] for node in compiled.nodes)
        if halt is not None:
            outcome = RunOutcome.HALTED
        elif awaiting:
            outcome = RunOutcome.AWAITING
        elif all(result.status is NodeStatus.SUCCEEDED for result in results):
            outcome = RunOutcome.FINISHED
        else:
            outcome = RunOutcome.FAILED
        return RunResult(
            tenant_id=compiled.tenant_id,
            mission_id=compiled.mission_id,
            execution_id=context.execution_id,
            plan_id=compiled.plan_id,
            plan_version=compiled.plan_version,
            outcome=outcome,
            halt=halt,
            awaiting=tuple(awaiting),
            results=results,
            dispatched=tuple(dispatched),
        )

    # --- ports, with faults contained ---------------------------------------------------

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

    def _dispatch(
        self, context: ExecutionContext, node: WorkNode | VerifyNode, settled: dict[StepId, NodeResult]
    ) -> NodeResult:
        if isinstance(node, WorkNode):
            return self._dispatch_work(context, node)
        return self._dispatch_verify(context, node, settled)

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
        status = {
            WorkStatus.FAILED: NodeStatus.FAILED,
            WorkStatus.NO_RESULT: NodeStatus.NO_RESULT,
            WorkStatus.SUBMITTED: NodeStatus.AWAITING,  # D-165
        }[result.status]
        return NodeResult(step_id=node.step_id, kind=node.kind, status=status, reason=result.reason)

    def _dispatch_verify(
        self, context: ExecutionContext, node: VerifyNode, settled: dict[StepId, NodeResult]
    ) -> NodeResult:
        predecessors = tuple(settled[p] for p in node.predecessors)
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


# --- helpers ---------------------------------------------------------------------------


def _nodes_by_level(compiled: CompiledPlan) -> list[list[WorkNode | VerifyNode]]:
    """Nodes grouped by the level the compiled plan gave them, each group in plan order.

    Levels are contiguous from 1 (the compiled form guarantees it), so the list index is
    ``level - 1``. Nothing here recomputes a level.
    """
    depth = max((node.level for node in compiled.nodes), default=0)
    levels: list[list[WorkNode | VerifyNode]] = [[] for _ in range(depth)]
    for node in compiled.nodes:
        levels[node.level - 1].append(node)
    return levels


def _skipped(node: WorkNode | VerifyNode, blockers: list[StepId], settled: dict[StepId, NodeResult]) -> NodeResult:
    listed = ", ".join(f"{blocker!r} ({settled[blocker].status.value})" for blocker in blockers)
    return NodeResult(
        step_id=node.step_id,
        kind=node.kind,
        status=NodeStatus.SKIPPED,
        reason=f"not dispatched: predecessor(s) did not succeed: {listed}",
    )


def _not_reached_pending(node: WorkNode | VerifyNode, blockers: list[StepId], settled: dict[StepId, NodeResult]) -> NodeResult:
    """D-165: every blocker is only awaiting or itself not_reached — none has concluded, so this is not a skip."""
    listed = ", ".join(f"{blocker!r} ({settled[blocker].status.value})" for blocker in blockers)
    return NodeResult(
        step_id=node.step_id,
        kind=node.kind,
        status=NodeStatus.NOT_REACHED,
        reason=f"not dispatched: predecessor(s) have not concluded yet: {listed}",
    )


def _failed(node: WorkNode | VerifyNode, reason: str) -> NodeResult:
    return NodeResult(step_id=node.step_id, kind=node.kind, status=NodeStatus.FAILED, reason=reason)


def _describe(error: Exception) -> str:
    text = str(error)
    return f"{type(error).__name__}: {text}" if text else type(error).__name__
