"""The model seam: what an agent may ask of a model, and everything a model may answer (D-135).

decisions.md: D-135 (``eidos.agents`` owns a synchronous ``ModelPort`` and its typed request, response and
failure types; only agents call it and only a provider adapter implements it; model, generation parameters
and timeout are explicit and never defaulted; provider outages, timeouts and malformed responses are typed
failures, never raised out of a run and never read as success; what a provider measures is returned as
measured fact), D-103 (no silent defaults, in spirit), D-136 (the default suite runs against a scripted fake),
invariants 9 (models sit behind a capability interface) and 17 (facts are labelled as facts).

Text in, text out. Nothing here names a model, a vendor or an SDK: a model is an opaque identifier string,
and which implementation answers is not this module's business.

**Every setting is required.** ``ModelSettings`` has no default for the model, the generation parameters or
the timeout, so a caller cannot get a hidden temperature or an unbounded wait by omission. ``MeasuredFacts``
are what the *provider* measured; they are never asserted by a model, and any field the provider did not
report is ``None`` rather than a guess.

Implementations must be thread-safe: an execution backend may run a level's nodes on worker threads.
"""

from enum import StrEnum
from typing import Protocol

from pydantic import Field, model_validator

from eidos.contracts import EidosModel


class GenerationParameters(EidosModel):
    """How a model is asked to generate. All three are required (D-135)."""

    temperature: float = Field(ge=0)
    seed: int
    max_output_tokens: int = Field(gt=0)


class ModelSettings(EidosModel):
    """A model and the way it is called. No field has a default (D-135)."""

    model: str = Field(min_length=1)  # an opaque identifier; the seam names no model
    parameters: GenerationParameters
    timeout_seconds: float = Field(gt=0)  # the only bound on a hung call: ports carry no runtime time budget


class ModelRequest(EidosModel):
    settings: ModelSettings
    prompt: str = Field(min_length=1)
    system: str | None = Field(default=None, min_length=1)


class MeasuredFacts(EidosModel):
    """What the provider measured about one call. ``None`` means the provider did not report it."""

    prompt_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    elapsed_seconds: float | None = Field(default=None, ge=0)


class ModelResponse(EidosModel):
    """A usable answer: non-empty text and what was measured about producing it."""

    text: str
    measured: MeasuredFacts = MeasuredFacts()

    @model_validator(mode="after")
    def _check_text_is_not_blank(self) -> "ModelResponse":
        if not self.text.strip():
            raise ValueError("a response with no text is an EMPTY_RESPONSE failure, not a response")
        return self


class ModelFailureKind(StrEnum):
    TIMEOUT = "timeout"  # the call did not finish inside ``timeout_seconds``
    UNAVAILABLE = "unavailable"  # the provider could not be reached, or answered with an error
    MALFORMED_RESPONSE = "malformed_response"  # the provider answered, but not in the shape it promised
    EMPTY_RESPONSE = "empty_response"  # the provider answered with no text


class ModelFailure(EidosModel):
    """A call that did not produce a usable answer. Returned, never raised; never read as success."""

    kind: ModelFailureKind
    message: str = Field(min_length=1)


ModelResult = ModelResponse | ModelFailure


class ModelPort(Protocol):
    """Asks a model to complete a prompt. Synchronous, thread-safe, and total: it returns a failure rather than raising."""

    def complete(self, request: ModelRequest) -> ModelResult: ...
