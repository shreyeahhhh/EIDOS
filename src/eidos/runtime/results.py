"""Typed, immutable execution results — what a run reports and what a resumed run is given.

decisions.md: D-117 (level-synchronous execution), D-118 (the seven node statuses
and three run outcomes; ``FINISHED`` is not verified success; ``HALTED`` takes
precedence), D-119 (each node is dispatched at most once per run), D-120 (a later
run may receive prior ``SUCCEEDED`` outcomes; invalid prior state is a rejection,
never silently adapted), D-121 (verification is separate from execution
completion), D-123 (nothing here is a ``MissionEvent`` or a MissionState write),
D-165 (V0.6 Step 3: an eighth node status, ``AWAITING``, and a fourth run outcome
of the same name, for a work node whose port reports it has dispatched work to a
remote system and does not yet know the outcome — nothing protocol-specific
reaches this module; see ``AwaitingInfo`` below).

Vocabulary
----------
A **result** is what one node's execution produced. Its ``step_id`` ties it to the
compiled node, and its ``kind`` says which supported kind that was.

A **usable result** is one the executor *reported as produced*: a work node
succeeds only with an ``artifact`` (an opaque ``ArtifactRef``; D-098 defines no
artifact model, and this module invents none). Whether the artifact is *good* is
verification's question, never execution's (invariant 12). A ``VERIFY`` node
produces no artifact; its success is the verifier's ``PASS``, and its ``reason``
carries the verifier's stated reason.

A **failure** always says why, in a non-empty ``reason``.

An **awaiting** result belongs to a dispatched work node whose port has not yet
concluded — dispatched, not skipped and not failed, but not settled either. It
carries no artifact, and a short, generic ``reason`` (D-165 rule 1: never a
protocol-specific one). Unlike a halt, which the executor's own design keeps to
one triggering node per run, more than one node may independently be awaiting at
once (D-165 rule 4), so ``RunResult.awaiting`` is a tuple, not a single value.

Everything is frozen, strict and ``extra=forbid``. There are no timestamps, no
object reprs and no set-iteration order: results are ordered by compiled plan order.
"""

from enum import StrEnum

from pydantic import Field, model_validator

from eidos.compiler import SUPPORTED_STEP_KINDS
from eidos.contracts import (
    ArtifactRef,
    EidosModel,
    ExecutionId,
    MissionId,
    PlanId,
    PlanStepKind,
    StepId,
    TenantId,
)


class NodeStatus(StrEnum):
    """D-118: seven statuses, none collapsed into a generic failure, plus one added by D-165."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"  # the node's execution itself failed (an executor or verifier fault)
    NO_RESULT = "no_result"  # a work node ran and produced no usable result
    VERIFICATION_FAILED = "verification_failed"  # the verifier said FAIL
    VERIFICATION_INCONCLUSIVE = "verification_inconclusive"  # the verifier could not establish success
    SKIPPED = "skipped"  # settled without dispatch: a predecessor did not succeed
    NOT_REACHED = "not_reached"  # never dispatched — because the run halted, or because a predecessor is itself unresolved (D-165)
    AWAITING = "awaiting"  # D-165: dispatched, but the port has not yet concluded — a work node only


# Statuses that can only come from a dispatch: a port was invoked for the node.
_DISPATCH_ONLY_STATUSES: tuple[NodeStatus, ...] = (
    NodeStatus.FAILED,
    NodeStatus.NO_RESULT,
    NodeStatus.VERIFICATION_FAILED,
    NodeStatus.VERIFICATION_INCONCLUSIVE,
    NodeStatus.AWAITING,
)
# Statuses a node can have without having been dispatched in this run.
_UNDISPATCHED_STATUSES: tuple[NodeStatus, ...] = (NodeStatus.SKIPPED, NodeStatus.NOT_REACHED)
# A blocker in this state has not concluded — it may yet succeed — so a node behind only blockers like these is not_reached, not skipped
# (D-165): "did not succeed" (skipped) would claim more than is known. Nothing here weakens the existing halt-caused not_reached case.
_UNRESOLVED_STATUSES: tuple[NodeStatus, ...] = (NodeStatus.AWAITING, NodeStatus.NOT_REACHED)


class NodeResult(EidosModel):
    """The outcome of one node."""

    step_id: StepId
    kind: PlanStepKind
    status: NodeStatus
    artifact: ArtifactRef | None = Field(default=None, min_length=1)
    reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check_shape_matches_status_and_kind(self) -> "NodeResult":
        if self.kind not in SUPPORTED_STEP_KINDS:
            raise ValueError(f"kind {self.kind.value!r} is not a kind V0.3 executes")
        is_work = self.kind is PlanStepKind.AGENT

        if self.status is NodeStatus.SUCCEEDED:
            if is_work:
                if self.artifact is None or self.reason is not None:
                    raise ValueError("a succeeded work node carries its artifact and no reason")
            elif self.artifact is not None or self.reason is None:
                raise ValueError("a succeeded verify node carries the verifier's reason and no artifact")
        else:
            if self.artifact is not None:
                raise ValueError(f"a {self.status.value} node carries no artifact")
            if self.reason is None:
                raise ValueError(f"a {self.status.value} node must state why (reason)")

        if self.status in (NodeStatus.NO_RESULT, NodeStatus.AWAITING) and not is_work:
            raise ValueError(f"{self.status.value} belongs to a work node")
        if self.status in (NodeStatus.VERIFICATION_FAILED, NodeStatus.VERIFICATION_INCONCLUSIVE) and is_work:
            raise ValueError(f"{self.status.value} belongs to a verify node")
        return self


class RunOutcome(StrEnum):
    """D-118. ``FINISHED`` is *not* verified success. D-165 adds a fourth."""

    FINISHED = "finished"  # not halted, not awaiting, and every node SUCCEEDED
    FAILED = "failed"  # not halted, not awaiting, and not every node SUCCEEDED
    HALTED = "halted"  # an admission guard halted the run; takes precedence over everything else
    AWAITING = "awaiting"  # D-165: not halted, but at least one node is; takes precedence over FINISHED/FAILED


class HaltInfo(EidosModel):
    """Why and where a run halted: the first admission HALT, in (level, rank) order."""

    step_id: StepId
    level: int = Field(ge=1)
    reason: str = Field(min_length=1)


class AwaitingInfo(EidosModel):
    """One node whose port reported it has dispatched work and does not yet know the outcome (D-165).

    Mirrors ``HaltInfo``'s shape — ``step_id``, ``level``, ``reason`` — but deliberately carries no field
    naming *what* it is waiting on: that correlation belongs one layer up, in ``eidos.state`` (D-166), which
    already names such things at the contract level. Nothing protocol-specific reaches this module.
    """

    step_id: StepId
    level: int = Field(ge=1)
    reason: str = Field(min_length=1)


class RunResult(EidosModel):
    """The complete, immutable record of one run.

    ``results`` holds exactly one ``NodeResult`` per compiled node, in compiled plan
    order. ``dispatched`` lists, in dispatch order, the nodes a port was invoked for
    *in this run* — so a node carried over from prior outcomes appears in ``results``
    as ``SUCCEEDED`` but not in ``dispatched``. ``awaiting`` lists every node whose
    result is ``AWAITING`` (D-165), in plan order — a plain fact list, exactly like
    ``dispatched``, not gated on the run's own ``outcome`` (unlike ``halt``, below,
    which does correlate 1:1 with an outcome of ``HALTED``: a halt is a single,
    run-level admission decision, not a per-node fact list; ``awaiting`` can be
    non-empty even when a later halt makes ``outcome`` ``HALTED`` rather than
    ``AWAITING`` — nothing about the nodes that were genuinely submitted is hidden
    by that precedence).
    """

    tenant_id: TenantId
    mission_id: MissionId
    execution_id: ExecutionId
    plan_id: PlanId
    plan_version: int = Field(ge=1)

    outcome: RunOutcome
    halt: HaltInfo | None = None
    awaiting: tuple[AwaitingInfo, ...] = ()
    results: tuple[NodeResult, ...]
    dispatched: tuple[StepId, ...] = ()

    @model_validator(mode="after")
    def _check_run_is_internally_consistent(self) -> "RunResult":
        status_of: dict[StepId, NodeStatus] = {}  # lookup only, never iterated
        for result in self.results:
            if result.step_id in status_of:
                raise ValueError(f"duplicate result for step_id {result.step_id!r}")
            status_of[result.step_id] = result.status

        seen: dict[StepId, None] = {}  # membership only
        for step_id in self.dispatched:
            if step_id not in status_of:
                raise ValueError(f"dispatched step_id {step_id!r} has no result")
            if step_id in seen:
                raise ValueError(f"step_id {step_id!r} was dispatched more than once (D-119)")
            if status_of[step_id] in _UNDISPATCHED_STATUSES:
                raise ValueError(f"step_id {step_id!r} was dispatched but is {status_of[step_id].value}")
            seen[step_id] = None
        for result in self.results:
            if result.status in _DISPATCH_ONLY_STATUSES and result.step_id not in seen:
                raise ValueError(f"{result.status.value} node {result.step_id!r} was never dispatched")

        # A not_reached node requires either a halt (D-118's original rule) or at least one awaiting node (D-165):
        # a node can be not_reached because a predecessor of its own is only awaiting, never having failed outright
        # (see the executor's readiness check). This does not verify *which* predecessor — the existing halt check
        # never verified that either, only that a halt exists at all; D-165 extends that same coarse sufficiency test
        # by one more legitimate cause, no more precisely than the rule it extends.
        if self.halt is None and not self.awaiting:
            if any(result.status is NodeStatus.NOT_REACHED for result in self.results):
                raise ValueError("a not_reached node requires the run to have halted or a node to be awaiting")
        if self.halt is not None and status_of.get(self.halt.step_id) is not NodeStatus.NOT_REACHED:
            raise ValueError("the node the run halted at must be not_reached")

        awaiting_step_ids: dict[StepId, None] = {}  # membership only
        for info in self.awaiting:
            if info.step_id in awaiting_step_ids:
                raise ValueError(f"step_id {info.step_id!r} appears more than once in awaiting")
            if status_of.get(info.step_id) is not NodeStatus.AWAITING:
                raise ValueError(f"awaiting names step_id {info.step_id!r}, whose result is not awaiting")
            awaiting_step_ids[info.step_id] = None
        for result in self.results:
            if result.status is NodeStatus.AWAITING and result.step_id not in awaiting_step_ids:
                raise ValueError(f"awaiting node {result.step_id!r} is missing from RunResult.awaiting")

        # Precedence, extending D-118 rule 4: a halt outranks everything, including one or more awaiting nodes
        # (an admission decision to stop is not overridden by work already in flight elsewhere); awaiting, once
        # there is no halt, outranks finished/failed (a run with an unresolved node is neither).
        if self.halt is not None:
            expected = RunOutcome.HALTED
        elif any(result.status is NodeStatus.AWAITING for result in self.results):
            expected = RunOutcome.AWAITING
        elif all(result.status is NodeStatus.SUCCEEDED for result in self.results):
            expected = RunOutcome.FINISHED
        else:
            expected = RunOutcome.FAILED
        if self.outcome is not expected:
            raise ValueError(f"outcome must be {expected.value!r} for these results, not {self.outcome.value!r}")
        return self

    @property
    def verified(self) -> bool:
        """True only for a ``FINISHED`` run in which at least one ``VERIFY`` node succeeded.

        A finished run with no successful ``VERIFY`` node is *unverified* (D-118, D-121).
        This is a fact about the run, never a claim that the mission succeeded: the
        verifier's own procedure is D-015, still Open.
        """
        return self.outcome is RunOutcome.FINISHED and any(
            result.kind is PlanStepKind.VERIFY for result in self.results
        )

    @property
    def settled(self) -> tuple[StepId, ...]:
        """Steps that reached a settled status, in plan order — everything but ``NOT_REACHED`` and ``AWAITING`` (D-165):
        neither has concluded, so neither is settled."""
        return tuple(r.step_id for r in self.results if r.status not in (NodeStatus.NOT_REACHED, NodeStatus.AWAITING))

    def result_for(self, step_id: StepId) -> NodeResult:
        for result in self.results:
            if result.step_id == step_id:
                return result
        raise KeyError(step_id)


class PriorOutcomes(EidosModel):
    """Outcomes from an earlier run of the same plan, offered to a new run (D-120).

    Only ``SUCCEEDED`` outcomes are valid prior state; the executor rejects anything
    else rather than ignoring it. The identity fields say which execution and plan
    version the outcomes belong to, so they cannot be silently applied to another.
    """

    tenant_id: TenantId
    mission_id: MissionId
    execution_id: ExecutionId
    plan_id: PlanId
    plan_version: int = Field(ge=1)
    outcomes: tuple[NodeResult, ...]

    @model_validator(mode="after")
    def _check_each_step_appears_once(self) -> "PriorOutcomes":
        seen: dict[StepId, None] = {}
        for outcome in self.outcomes:
            if outcome.step_id in seen:
                raise ValueError(f"duplicate prior outcome for step_id {outcome.step_id!r}")
            seen[outcome.step_id] = None
        return self

    @classmethod
    def succeeded_from(cls, result: RunResult) -> "PriorOutcomes":
        """The ``SUCCEEDED`` outcomes of an earlier run, as the prior for a resumed one.

        Selecting only the successes is the caller's explicit act (D-120: a later run
        "may receive prior SUCCEEDED outcomes"); the executor never filters.
        """
        return cls(
            tenant_id=result.tenant_id,
            mission_id=result.mission_id,
            execution_id=result.execution_id,
            plan_id=result.plan_id,
            plan_version=result.plan_version,
            outcomes=tuple(r for r in result.results if r.status is NodeStatus.SUCCEEDED),
        )


class RunRejectionCode(StrEnum):
    """Why a run was refused before anything executed (D-120, and context validation)."""

    WRONG_TENANT = "wrong_tenant"
    WRONG_MISSION = "wrong_mission"
    WRONG_PLAN = "wrong_plan"
    WRONG_PLAN_VERSION = "wrong_plan_version"
    INVALID_PRIOR_STATE = "invalid_prior_state"


class RunRejection(EidosModel):
    """A run that was refused. Nothing was dispatched and nothing was adapted."""

    code: RunRejectionCode
    message: str = Field(min_length=1)
    step_ids: tuple[StepId, ...] = ()  # the steps a prior-state rejection concerns

    @model_validator(mode="after")
    def _check_only_prior_state_names_steps(self) -> "RunRejection":
        if self.step_ids and self.code is not RunRejectionCode.INVALID_PRIOR_STATE:
            raise ValueError(f"code {self.code.value!r} is about the context, not steps")
        return self
