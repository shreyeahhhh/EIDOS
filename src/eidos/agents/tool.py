"""The tool seam: what an agent may ask of a tool provider, and everything a provider may answer (decisions.md D-203, D-135; V1.2 Step 2).

The same shape as the model seam (D-135), one boundary over: this package owns a synchronous ``ToolPort`` and its typed
request, result and failure; only an agent calls it, and only a provider adapter implements it. Nothing here names a
provider, a protocol or an SDK: a tool is an opaque identifier string, and which implementation answers is not this
module's business.

**A request is only ever built for a call that has already been admitted** (``eidos.policy``), so its arguments are
already validated and its bounds already come from the allowlist entry. It carries its own timeout and result-size bound:
neither has a default, so a caller cannot get an unbounded wait or an unbounded result by omission (D-135's rule for
models, applied here). Arguments are held in a canonical order so that two requests for the same call are equal.

**A result is the normalised one**: a tuple of documents, each with the provider's own identifier for it and its text.
An empty tuple is a real result ("nothing matched"), not a failure. A tool that fails, or answers in a shape it did not
promise, or answers with more than the bound allows, is a typed ``ToolFailure`` — returned, never raised, never read as
success (invariant 12: a tool answering is not evidence sufficiency, and evidence sufficiency is not mission success).

No result text is ever parsed into anything executable or interpreted as an instruction (invariant 3): it is text.
Implementations must be thread-safe: an execution backend may run a level's nodes on worker threads.
"""

from enum import StrEnum
from typing import Protocol

from pydantic import Field, model_validator

from eidos.contracts import EidosModel


class ToolArgument(EidosModel):
    name: str = Field(min_length=1)
    value: str | int


class ToolRequest(EidosModel):
    """One admitted call. Every field is required: the bounds come from the allowlist entry, never from a default."""

    tool_id: str = Field(min_length=1)
    arguments: tuple[ToolArgument, ...]
    timeout_seconds: float = Field(gt=0)
    max_result_bytes: int = Field(gt=0)

    @model_validator(mode="after")
    def _check_arguments_are_canonical(self) -> "ToolRequest":
        names = [argument.name for argument in self.arguments]
        if names != sorted(names) or len(set(names)) != len(names):
            raise ValueError("a request lists its arguments once each, in ascending name order")
        return self


class ToolDocument(EidosModel):
    """One retrieved document: the provider's own identifier for it, and its text."""

    document_id: str = Field(min_length=1)
    content: str


class ToolResult(EidosModel):
    """A usable answer. An empty ``documents`` means the tool ran and found nothing."""

    documents: tuple[ToolDocument, ...]

    @model_validator(mode="after")
    def _check_document_ids_are_distinct(self) -> "ToolResult":
        ids = [document.document_id for document in self.documents]
        if len(set(ids)) != len(ids):
            raise ValueError("a result lists each document at most once")
        return self

    @property
    def size_bytes(self) -> int:
        """The UTF-8 size of every document's identifier and text: the quantity a result-size bound limits."""
        return sum(len(document.document_id.encode("utf-8")) + len(document.content.encode("utf-8")) for document in self.documents)


class ToolFailureKind(StrEnum):
    UNAVAILABLE = "unavailable"  # the provider could not be reached, or refused to serve
    TIMEOUT = "timeout"  # the call did not finish inside ``timeout_seconds``
    TOOL_ERROR = "tool_error"  # the provider ran the tool and reported that it failed
    MALFORMED_RESULT = "malformed_result"  # the provider answered, but not in the shape it promised
    RESULT_TOO_LARGE = "result_too_large"  # the answer exceeded ``max_result_bytes``


class ToolFailure(EidosModel):
    """A call that did not produce a usable answer. Returned, never raised; never read as success."""

    kind: ToolFailureKind
    message: str = Field(min_length=1)


ToolOutcome = ToolResult | ToolFailure


class ToolPort(Protocol):
    """Runs one admitted call. Synchronous, thread-safe, and total: it returns a failure rather than raising."""

    def call(self, request: ToolRequest) -> ToolOutcome: ...


def bound_result(result: ToolResult, max_result_bytes: int) -> ToolOutcome:
    """The result itself if it fits ``max_result_bytes``, otherwise the ``RESULT_TOO_LARGE`` failure. Nothing is truncated:
    a partial result would be a different, unverifiable one."""
    if result.size_bytes > max_result_bytes:
        return ToolFailure(
            kind=ToolFailureKind.RESULT_TOO_LARGE,
            message=f"the result is {result.size_bytes} bytes, more than the bound of {max_result_bytes}",
        )
    return result
