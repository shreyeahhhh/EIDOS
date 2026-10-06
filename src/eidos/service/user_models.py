"""A user's own model for one run: bring-your-own-key (decisions.md D-246).

A user may name a hosted provider, a model and **their own API key** when they start a mission. The service holds that key **in memory only, for that one run**: it is never written to the database, never put
in an event, never in the stored specification, never in a log, and it is dropped when the run ends (``RunManager`` owns that). This module has the three small types that make that safe:

- ``ModelChoice`` is the request. The key is a ``SecretStr`` (its ``repr`` and ``str`` are masked) and is validated to be the shape of a credential, so nothing that is not one - and nothing with a line break
  - can reach an HTTP header. A validation error never contains the value.
- ``UserModels`` is the deployer's policy: which providers a user may bring a key for, and the function that builds a ``ModelPort`` from a provider name and a key. **This package names no vendor**; the
  composition root supplies the function, and with it each provider's *fixed* address. A user never supplies an address, so a user cannot point the server at a host of their choosing.
- ``RunModel`` is what one run is given in place of the service's own model: a port, and the settings (the user's model name over the deployer's parameters and timeout).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from eidos.agents import ModelPort, ModelSettings

MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}")
API_KEY_SHAPE = re.compile(r"[\x21-\x7e]{8,512}")  # printable ASCII, no space, no control character: every key a provider issues, and nothing that could split a header


class ModelChoice(BaseModel):
    """The model a user asks a run to use, with their own key."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)  # a ValidationError printed anywhere must not carry the key it rejected

    provider: str = Field(min_length=1, max_length=32)
    model: str = Field(min_length=1, max_length=100)
    api_key: SecretStr

    @field_validator("model")
    @classmethod
    def _model_name(cls, value: str) -> str:
        if not MODEL_NAME.fullmatch(value):
            raise ValueError("the model name may hold letters, digits and . _ : / - only (1 to 100 characters)")
        return value

    @field_validator("api_key")
    @classmethod
    def _key_shape(cls, value: SecretStr) -> SecretStr:
        if not API_KEY_SHAPE.fullmatch(value.get_secret_value()):
            raise ValueError("the API key must be 8 to 512 printable characters with no spaces")  # never the value
        return value


class StartRequest(BaseModel):
    """The optional body of a start request. An empty body starts the run on the service's own model, as before."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)  # a ValidationError printed anywhere must not carry the key it rejected

    model: ModelChoice | None = None


ModelFactory = Callable[[str, str], ModelPort]  # (provider, api key) -> a port; raises ValueError for a provider it does not know


@dataclass(frozen=True, slots=True)
class UserModels:
    """The deployer's policy for a user's own model: the providers allowed, and how to build a port for one."""

    providers: frozenset[str]
    factory: ModelFactory


@dataclass(frozen=True, slots=True, repr=False)
class RunModel:
    """The model one run uses instead of the service's own."""

    port: ModelPort
    settings: ModelSettings

    def __repr__(self) -> str:
        return f"RunModel(model={self.settings.model!r})"
