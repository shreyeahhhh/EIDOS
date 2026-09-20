"""Factories and doubles for V0.4 agent tests.

``ScriptedModel`` is the fake at the model seam (D-136): the default suite never reaches a real model. It answers
as a test scripted, records every request atomically, and is thread-safe, because the LangGraph backend runs a
level's nodes on worker threads. Nothing here names a real model or provider.
"""

import threading

from eidos.agents import GenerationParameters, ModelRequest, ModelResponse, ModelSettings


def make_settings(**overrides) -> ModelSettings:
    fields = dict(
        model="test-model",
        parameters=GenerationParameters(temperature=0.0, seed=7, max_output_tokens=256),
        timeout_seconds=5.0,
    )
    fields.update(overrides)
    return ModelSettings(**fields)


class ScriptedModel:
    """A ``ModelPort`` that answers with ``respond(request)``.

    ``respond`` may return a ``ModelResponse`` or ``ModelFailure``, or raise (to test containment). By default it
    answers ``"scripted answer"``. Every request is recorded, under a lock.
    """

    def __init__(self, respond=None):
        self._respond = respond or (lambda request: ModelResponse(text="scripted answer"))
        self._lock = threading.Lock()
        self.requests: list[ModelRequest] = []

    def complete(self, request):
        with self._lock:
            self.requests.append(request)
        return self._respond(request)

    @property
    def calls(self) -> int:
        with self._lock:
            return len(self.requests)
