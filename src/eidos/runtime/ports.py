"""Synchronous, backend-neutral execution ports and their typed results.

decisions.md: D-118 (node statuses), D-119 (a node is dispatched at most once),
D-121 (the verifier returns ``PASS | FAIL | INCONCLUSIVE`` plus a reason — no scalar),
D-122 (ports are synchronous; the ``AdmissionGuard`` is explicit and required, with
no default; D-018 stays scoped to this execution-side interface only), D-117 (a halt
takes effect after the current level).

Three narrow ports, owned here so implementations depend on the runtime and never the
reverse (D-115):

- ``WorkExecutor.execute(context, node)`` — perform a work node's requested capability.
- ``Verifier.verify(context, node, predecessors)`` — judge a ``VERIFY`` node.
- ``AdmissionGuard.admit(request)`` — decide whether one node may be dispatched.

Nothing here names a model, a provider or an agent. A work node carries only a
requested *capability* (invariant 11); which implementation serves it is not the
runtime's business.

Results are typed and immutable. A port never returns a bare ``dict`` or ``None``.
"""

from enum import StrEnum
from typing import Protocol

from pydantic import Field, model_validator

from eidos.compiler import VerifyNode, WorkNode
from eidos.contracts import ArtifactRef, EidosModel, StepId

from .context import ExecutionContext
from .results import NodeResult

# --- work -------------------------------------------------------------------------


class WorkStatus(StrEnum):
    PRODUCED = "produced"  # the executor produced a usable result
    FAILED = "failed"  # the executor's own work failed
    NO_RESULT = "no_result"  # the executor completed but produced nothing usable
    SUBMITTED = "submitted"  # D-165: dispatched to a remote system; the outcome is not yet known


class WorkResult(EidosModel):
    """What a ``WorkExecutor`` reports for one work node.

    ``PRODUCED`` means a usable result: it names an ``artifact`` (an opaque reference;
    no artifact model exists, D-098). ``FAILED``, ``NO_RESULT`` and ``SUBMITTED`` carry
    no artifact and must say why. ``SUBMITTED`` (D-165) is the one non-blocking case: the
    port genuinely dispatched the work — it does not raise, and it does not wait — and
    reports plainly that it does not yet know the outcome. Its ``reason`` is a short,
    generic description; nothing protocol-specific belongs here (D-165 rule 1), since
    ``eidos.runtime`` names no vendor, model or protocol.
    """

    status: WorkStatus
    artifact: ArtifactRef | None = Field(default=None, min_length=1)
    reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check_fields_match_status(self) -> "WorkResult":
        if self.status is WorkStatus.PRODUCED:
            if self.artifact is None or self.reason is not None:
                raise ValueError("a produced result names its artifact and carries no reason")
        elif self.artifact is not None or self.reason is None:
            raise ValueError(f"a {self.status.value} result carries no artifact and must state why")
        return self

    @classmethod
    def produced(cls, artifact: ArtifactRef) -> "WorkResult":
        return cls(status=WorkStatus.PRODUCED, artifact=artifact)

    @classmethod
    def failed(cls, reason: str) -> "WorkResult":
        return cls(status=WorkStatus.FAILED, reason=reason)

    @classmethod
    def no_result(cls, reason: str) -> "WorkResult":
        return cls(status=WorkStatus.NO_RESULT, reason=reason)

    @classmethod
    def submitted(cls, reason: str) -> "WorkResult":
        return cls(status=WorkStatus.SUBMITTED, reason=reason)


class WorkExecutor(Protocol):
    """Performs one work node's requested capability. Synchronous.

    An exception raised here is caught by the executor and recorded as ``FAILED``; it
    never propagates. The *call* is always synchronous and returns exactly once — but the
    *work* need not be finished when it does: a port may report ``SUBMITTED`` (D-165) to
    say it has dispatched the work elsewhere and does not yet know the outcome, without
    blocking this call to find out.
    """

    def execute(self, context: ExecutionContext, node: WorkNode) -> WorkResult: ...


# --- verification --------------------------------------------------------------------


class VerificationVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"  # success could not be established; never a pass


class VerificationResult(EidosModel):
    """A verdict and the verifier's reason. No score of any kind (D-121)."""

    verdict: VerificationVerdict
    reason: str = Field(min_length=1)

    @classmethod
    def passed(cls, reason: str) -> "VerificationResult":
        return cls(verdict=VerificationVerdict.PASS, reason=reason)

    @classmethod
    def failed(cls, reason: str) -> "VerificationResult":
        return cls(verdict=VerificationVerdict.FAIL, reason=reason)

    @classmethod
    def inconclusive(cls, reason: str) -> "VerificationResult":
        return cls(verdict=VerificationVerdict.INCONCLUSIVE, reason=reason)


class Verifier(Protocol):
    """Judges one ``VERIFY`` node. Synchronous; called exactly once per dispatched node.

    ``predecessors`` are the node's predecessors' results, in the node's predecessor
    order. Every one of them ``SUCCEEDED`` — a node with a predecessor that did not
    succeed is skipped, never verified — so a work predecessor's ``artifact`` is what
    is available to verify. An exception raised here is caught by the executor and
    recorded as ``FAILED``; it is never read as a verdict.
    """

    def verify(
        self,
        context: ExecutionContext,
        node: VerifyNode,
        predecessors: tuple[NodeResult, ...],
    ) -> VerificationResult: ...


# --- admission ------------------------------------------------------------------------


class AdmissionRequest(EidosModel):
    """Everything an ``AdmissionGuard`` is told: deterministic execution facts only.

    - ``level``: the node's level in the compiled plan (D-117).
    - ``rank_in_level``: the node's zero-based rank among the nodes of its level that
      will actually be dispatched in this run, in ascending plan position. Nodes that
      are skipped, or already settled by prior outcomes, are not counted.
    - ``dispatched_before_level``: how many nodes this run dispatched in earlier levels.

    These depend on the compiled plan and node results alone, never on timing, so a
    guard that is a pure function of them gives the same answer under any scheduling.
    """

    step_id: StepId
    level: int = Field(ge=1)
    rank_in_level: int = Field(ge=0)
    dispatched_before_level: int = Field(ge=0)


class AdmissionOutcome(StrEnum):
    ADMIT = "admit"
    HALT = "halt"


class AdmissionDecision(EidosModel):
    """``ADMIT``, or ``HALT`` with the reason the run is halting."""

    outcome: AdmissionOutcome
    reason: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _check_halt_states_why(self) -> "AdmissionDecision":
        if self.outcome is AdmissionOutcome.HALT:
            if self.reason is None:
                raise ValueError("a halt must state why (reason)")
        elif self.reason is not None:
            raise ValueError("an admit carries no reason")
        return self

    @classmethod
    def admit(cls) -> "AdmissionDecision":
        return cls(outcome=AdmissionOutcome.ADMIT)

    @classmethod
    def halt(cls, reason: str) -> "AdmissionDecision":
        return cls(outcome=AdmissionOutcome.HALT, reason=reason)


class AdmissionGuard(Protocol):
    """The bounded-execution hook: may this node be dispatched? Synchronous.

    **Must be a pure function of the request** — no clock, no counters of its own, no
    memory of earlier calls — so that its answer does not depend on scheduling order.
    It is asked once for every node that would be dispatched. A ``HALT`` leaves that node
    ``NOT_REACHED`` and stops the run after the current level; it does not stop the other
    nodes of the level from being asked.

    There is no default guard and no ambient configuration (D-122); no production guard
    ships in V0.3, because runtime budget accounting is deferred (D-127).
    """

    def admit(self, request: AdmissionRequest) -> AdmissionDecision: ...
