"""Asking several models the same question directly, with the user's own keys (decisions.md D-248).

**This is not a mission.** A mission only completes if its answer cites sources that exist, and an answer from a model's own knowledge has none, so it can never pass EIDOS's checks; nothing here pretends
otherwise (no question is dressed up as a "source", and no verification is claimed). The question goes to each chosen model once, concurrently, and what each one says comes back **as it said it**, with how
long it took, the tokens the provider reported, or the provider's own refusal in its own words. Every answer is marked ``verified: false`` and the response says plainly that nothing was checked and nothing was
cited. **Nothing is stored and no event is recorded**: it is not a run of the runtime, so nothing in the runtime's guarantees is claimed for it.

The user's key is handled exactly as for a mission (D-246): a ``SecretStr``, held in memory for the length of this call, never stored, logged or echoed.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .user_models import ModelChoice

ASK_MAX_MODELS = 3
ASK_MAX_IN_FLIGHT = 6  # PROVISIONAL: model calls in flight across every request of this process, so one person cannot occupy the service

ASK_NOTE = (
    "These answers are each model's own words, from its own knowledge. EIDOS found no sources, cited none and checked none of it. Treat them as unverified, and for anything that matters "
    "(money, health, law) check a reliable source."
)

ASK_SYSTEM_PROMPT = (
    "Answer the user's question as helpfully and accurately as you can. If you are not sure, say so plainly. You have no documents and no web access here, so you cannot cite sources: "
    "do not invent citations, links or quotations."
)


class AskRequest(BaseModel):
    """One question and the models to put it to."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    question: str = Field(min_length=1)
    models: list[ModelChoice] = Field(min_length=1, max_length=ASK_MAX_MODELS)

    @field_validator("question")
    @classmethod
    def _question(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("write a question")
        if "\x00" in text:
            raise ValueError("the question has a character that cannot be sent")
        return text


class AskedAnswer(BaseModel):
    """What one model said (or why it could not), in its own words. Never a score."""

    provider: str
    model: str
    ok: bool
    text: str | None = None
    failure: str | None = None
    elapsed_seconds: float | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None


class AskResult(BaseModel):
    """The answers, in the order the models were named, and the plain statement that none of it is verified."""

    answers: list[AskedAnswer]
    verified: Literal[False] = False
    note: str = ASK_NOTE
