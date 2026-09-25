"""The tool gate: an agent's one way to a tool (decisions.md D-203, D-205, D-206, D-207; V1.2 Step 4).

An agent that wants a tool calls ``ToolAccess.call(context, tool_id, arguments)`` and gets back one typed ``ToolGateOutcome``. ``ToolGate`` is the
implementation that composes the pieces the earlier steps built, in a fixed order, and it is the only thing that ever reaches a ``ToolPort``:

1. **Admission first.** ``eidos.policy.admit_tool_call`` decides from the pinned allowlist, the mission's own ``allowed_actions`` and autonomy level,
   and the contract's ``max_tool_calls``, against this execution's history of invocations. A denial is returned; the port is never called.
2. **A duplicate is served, not invoked.** An exact repeat of a call in this execution, whichever plan attempt made it, whose result was stored is
   answered from the artifacts it became. No tool is invoked and no invocation budget is consumed.
3. **Only then a request is built and the port is called**, with the timeout and result-size bound of the allowlist entry and nothing else.
4. **A result is normalised and stored.** Each document becomes its own artifact in the store, with a reference that names the tool, the request
   digest and the document (``tool:<tool_id>:<args_digest>:<document_id>``), so distinct documents are distinct sources and a reference alone says
   where a piece of evidence came from. Text a tool returns is data: it is stored as text and never read as an instruction (invariant 3).

The gate never raises for a tool outcome. A port that raises, answers in a shape it did not promise, exceeds the size bound or names a document with
an id that could not be cited is turned into a typed ``ToolFailure`` and still counts as an invocation, because a tool was reached.

The ledger of invocations lives here, in memory, behind one lock, so two nodes on worker threads cannot both spend the last unit of a budget: the
budget is reserved under the lock before the port is called. It is scoped, by ``eidos.policy``, to ``(execution_id, plan_id)``; nothing here
adds a cumulative mission-wide limit (deferred, D-043). This module knows nothing about how a port reaches its tool: it names no protocol, no
transport and no provider.
"""

import re
import threading
from collections.abc import Mapping
from enum import StrEnum
from typing import Protocol

from pydantic import model_validator

from eidos.capabilities import ToolRegistry
from eidos.contracts import ArtifactRef, EidosModel, ExecutionId
from eidos.policy import ToolAdmission, ToolDecision, ToolInvocationRecord, admit_tool_call
from eidos.runtime import ExecutionContext

from .artifacts import Artifact, ArtifactConflict, ArtifactStore
from .tool import ToolArgument, ToolDocument, ToolFailure, ToolFailureKind, ToolOutcome, ToolPort, ToolRequest, ToolResult, bound_result

TOOL_DOCUMENT_CONTENT_TYPE = "text/plain"

# A provider's own id for a document must be citable as ``[[reference]]`` and safe to put in a reference: the same plain identifier the allowlist
# uses for provider and tool names.
_DOCUMENT_ID = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def tool_document_ref(tool_id: str, args_digest: str, document_id: str) -> ArtifactRef:
    """The reference a retrieved document is stored under: it names the tool, the request digest and the document."""
    return ArtifactRef(f"tool:{tool_id}:{args_digest}:{document_id}")


def parse_tool_document_ref(ref: str) -> tuple[str, str, str] | None:
    """``(tool_id, args_digest, document_id)`` for a reference ``tool_document_ref`` made, else ``None``."""
    parts = str(ref).split(":", 3)
    if len(parts) != 4 or parts[0] != "tool" or not parts[1] or not parts[2] or not _DOCUMENT_ID.fullmatch(parts[3]):
        return None
    return parts[1], parts[2], parts[3]


class ToolGateKind(StrEnum):
    DENIED = "denied"  # admission refused the call: no tool was reached
    SERVED = "served"  # a duplicate, answered from the stored result: no tool was reached
    INVOKED = "invoked"  # a tool was reached, whatever it came to


class ToolGateOutcome(EidosModel):
    """Everything one call to the gate came to. ``admission`` is the decision; ``result`` is what was answered (a result, or a failure for an
    invocation that failed; ``None`` for a denial); ``refs`` are the artifacts the answer became, one per document and in the answer's order."""

    tool_id: str
    admission: ToolAdmission
    result: ToolOutcome | None = None
    refs: tuple[ArtifactRef, ...] = ()

    @model_validator(mode="after")
    def _check_the_outcome_matches_the_decision(self) -> "ToolGateOutcome":
        decision = self.admission.decision
        if decision is ToolDecision.DENY:
            if self.result is not None or self.refs:
                raise ValueError("a denied call reached no tool and has no result")
            return self
        if self.result is None:
            raise ValueError("a call that was not denied has a result or a failure")
        if decision is ToolDecision.SERVE_STORED and not isinstance(self.result, ToolResult):
            raise ValueError("a served duplicate is answered with the stored result")
        if self.refs and not (isinstance(self.result, ToolResult) and len(self.refs) == len(self.result.documents)):
            raise ValueError("references name the documents of a result, one each")
        return self

    @property
    def kind(self) -> ToolGateKind:
        if self.admission.decision is ToolDecision.DENY:
            return ToolGateKind.DENIED
        if self.admission.decision is ToolDecision.SERVE_STORED:
            return ToolGateKind.SERVED
        return ToolGateKind.INVOKED

    @property
    def documents(self) -> tuple[ToolDocument, ...]:
        return self.result.documents if isinstance(self.result, ToolResult) else ()


class ToolAccess(Protocol):
    """What an agent calls. Synchronous, thread-safe and total: every outcome, a refusal included, is a returned ``ToolGateOutcome``."""

    def call(self, context: ExecutionContext, tool_id: str, arguments: Mapping[str, object]) -> ToolGateOutcome: ...


class ToolGate:
    def __init__(self, *, registry: ToolRegistry, port: ToolPort, store: ArtifactStore):
        self._registry, self._port, self._store = registry, port, store
        self._lock = threading.Lock()
        self._records: list[ToolInvocationRecord] = []
        self._stored: dict[tuple[ExecutionId, str, str], tuple[ArtifactRef, ...]] = {}

    @property
    def invocations(self) -> tuple[ToolInvocationRecord, ...]:
        """Every call that reached a tool, in the order it was reserved: the ledger admission reads and the budget it enforces."""
        with self._lock:
            return tuple(self._records)

    def call(self, context: ExecutionContext, tool_id: str, arguments: Mapping[str, object]) -> ToolGateOutcome:
        with self._lock:
            admission = admit_tool_call(
                registry=self._registry,
                tool_id=tool_id,
                arguments=arguments,
                execution_id=context.execution_id,
                plan_id=context.plan_id,
                allowed_actions=context.task_genome.allowed_actions,
                autonomy_level=context.task_genome.autonomy_level,
                max_tool_calls=context.reliability_contract.max_tool_calls,
                prior_invocations=tuple(self._records),
            )
            if admission.decision is ToolDecision.DENY:
                return ToolGateOutcome(tool_id=tool_id, admission=admission)
            digest = admission.args_digest
            if admission.decision is ToolDecision.SERVE_STORED:
                return self._served(context, tool_id, admission, digest)
            index = len(self._records)  # the budget is spent here, before the port is called
            self._records.append(
                ToolInvocationRecord(execution_id=context.execution_id, plan_id=context.plan_id, tool_id=tool_id, args_digest=digest, result_stored=False)
            )

        request = ToolRequest(
            tool_id=tool_id,
            arguments=tuple(ToolArgument(name=name, value=arguments[name]) for name in sorted(arguments)),  # type: ignore[arg-type]  # validated by admission
            timeout_seconds=admission.timeout_seconds,
            max_result_bytes=admission.max_result_bytes,
        )
        answer = self._invoke(request)
        refs: tuple[ArtifactRef, ...] = ()
        if isinstance(answer, ToolResult):
            answer, refs = self._store_documents(context, tool_id, digest, answer)
        if isinstance(answer, ToolResult):
            with self._lock:  # a stored result is what lets a later duplicate be served
                self._records[index] = ToolInvocationRecord(
                    execution_id=context.execution_id, plan_id=context.plan_id, tool_id=tool_id, args_digest=digest, result_stored=True
                )
                self._stored[(context.execution_id, tool_id, digest)] = refs
        return ToolGateOutcome(tool_id=tool_id, admission=admission, result=answer, refs=refs)

    # --- a duplicate ---------------------------------------------------------------------------------------------------------

    def _served(self, context: ExecutionContext, tool_id: str, admission: ToolAdmission, digest: str) -> ToolGateOutcome:
        refs = self._stored[(context.execution_id, tool_id, digest)]
        documents = []
        for ref in refs:
            artifact = self._store.get(context.execution_id, ref)
            if artifact is None:
                raise LookupError(f"the stored result {str(ref)!r} is missing from the artifact store")
            documents.append(ToolDocument(document_id=parse_tool_document_ref(ref)[2], content=artifact.content))  # type: ignore[index]
        return ToolGateOutcome(tool_id=tool_id, admission=admission, result=ToolResult(documents=tuple(documents)), refs=refs)

    # --- an invocation --------------------------------------------------------------------------------------------------------

    def _invoke(self, request: ToolRequest) -> ToolOutcome:
        try:
            answer = self._port.call(request)
        except Exception as error:  # noqa: BLE001 — a port is total; one that raises is a fault, recorded as a typed failure
            return ToolFailure(kind=ToolFailureKind.TOOL_ERROR, message=f"the tool port raised {type(error).__name__}")
        if isinstance(answer, ToolFailure):
            return answer
        if not isinstance(answer, ToolResult):
            return ToolFailure(kind=ToolFailureKind.MALFORMED_RESULT, message="the tool port returned neither a result nor a failure")
        return bound_result(answer, request.max_result_bytes)

    def _store_documents(
        self, context: ExecutionContext, tool_id: str, digest: str, result: ToolResult
    ) -> tuple[ToolOutcome, tuple[ArtifactRef, ...]]:
        """Each document becomes its own artifact. A result whose documents could not all be stored under citable references is a failure and
        stores nothing."""
        if any(not _DOCUMENT_ID.fullmatch(document.document_id) for document in result.documents):
            return ToolFailure(kind=ToolFailureKind.MALFORMED_RESULT, message="a document id is not a plain identifier that can be cited"), ()
        refs = tuple(tool_document_ref(tool_id, digest, document.document_id) for document in result.documents)
        if any(self._store.get(context.execution_id, ref) is not None for ref in refs):
            return ToolFailure(kind=ToolFailureKind.MALFORMED_RESULT, message="a document reference is already taken in this execution"), ()
        try:
            for ref, document in zip(refs, result.documents):
                self._store.put_supplied(
                    context.execution_id, Artifact(ref=ref, content_type=TOOL_DOCUMENT_CONTENT_TYPE, content=document.content)
                )
        except ArtifactConflict:
            return ToolFailure(kind=ToolFailureKind.MALFORMED_RESULT, message="a document reference is already taken in this execution"), ()
        return result, refs
