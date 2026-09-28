"""A hosted-model adapter — Groq's OpenAI-compatible chat-completions API (decisions.md D-135, D-136).

``GroqModel`` implements ``eidos.agents.ModelPort`` exactly as ``OllamaModel`` does: standard library
only, no vendor SDK, nothing about the endpoint or credential assumed. The base URL, the API key, the
model, the generation parameters and the timeout are all **explicit, required** inputs — there is no
default endpoint and nothing ambient is read here (D-135); ``eidos.api.main``, the composition root, is
the one caller that reads ``GROQ_API_KEY`` from outside configuration, and hands it to this adapter as a
plain constructor argument like every other setting.

The port is *total*: outages, timeouts, rate limits and malformed answers come back as typed
``ModelFailure`` values, never raised and never read as success — the same four-kind vocabulary
``OllamaModel`` uses, because a rate limit or a provider-side error is exactly what ``UNAVAILABLE``
already means ("the provider could not be reached, or answered with an error"). No new failure kind
was added for this provider.

Only ``http`` and ``https`` URLs are accepted, matching ``OllamaModel``.
"""

import http.client
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from eidos.agents import MeasuredFacts, ModelFailure, ModelFailureKind, ModelRequest, ModelResponse, ModelResult

_PATH = "/chat/completions"


@dataclass(frozen=True, slots=True, kw_only=True)
class GroqModel:
    base_url: str  # required, no default: e.g. https://api.groq.com/openai/v1
    api_key: str  # required, no default: the caller's own GROQ_API_KEY, read once at the composition root

    def __post_init__(self) -> None:
        parsed = urllib.parse.urlsplit(self.base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(f"base_url must be an http or https URL with a host, not {self.base_url!r}")
        if not self.api_key.strip():
            raise ValueError("api_key must not be blank")

    def complete(self, request: ModelRequest) -> ModelResult:
        messages: list[dict[str, str]] = []
        if request.system is not None:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        body: dict[str, object] = {
            "model": request.settings.model,
            "messages": messages,
            "temperature": request.settings.parameters.temperature,
            "seed": request.settings.parameters.seed,
            "max_tokens": request.settings.parameters.max_output_tokens,
        }
        http_request = urllib.request.Request(
            self.base_url.rstrip("/") + _PATH,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(http_request, timeout=request.settings.timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            # Covers a bad/expired key (401), a model the account cannot use (404), and rate limiting (429)
            # alike: all are "the provider answered with an error", which is exactly what UNAVAILABLE means.
            return _failure(ModelFailureKind.UNAVAILABLE, f"the provider answered HTTP status {error.code}")
        except urllib.error.URLError as error:
            if isinstance(error.reason, (socket.timeout, TimeoutError)):
                return _failure(ModelFailureKind.TIMEOUT, f"no answer within {request.settings.timeout_seconds} seconds")
            return _failure(ModelFailureKind.UNAVAILABLE, f"the provider could not be reached: {error.reason}")
        except (socket.timeout, TimeoutError):
            return _failure(ModelFailureKind.TIMEOUT, f"no answer within {request.settings.timeout_seconds} seconds")
        except http.client.RemoteDisconnected:
            return _failure(ModelFailureKind.UNAVAILABLE, "the provider closed the connection without answering")
        except http.client.HTTPException as error:
            return _failure(ModelFailureKind.MALFORMED_RESPONSE, f"the answer was not well-formed HTTP: {type(error).__name__}")
        except OSError as error:
            return _failure(ModelFailureKind.UNAVAILABLE, f"the connection failed: {error}")
        elapsed = time.monotonic() - started
        return _interpret(raw, elapsed)


def _interpret(raw: bytes, elapsed_seconds: float) -> ModelResult:
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _failure(ModelFailureKind.MALFORMED_RESPONSE, "the answer was not valid JSON")
    if not isinstance(document, dict):
        return _failure(ModelFailureKind.MALFORMED_RESPONSE, "the answer was not a JSON object")
    choices = document.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return _failure(ModelFailureKind.MALFORMED_RESPONSE, "the answer had no usable 'choices' entry")
    message = choices[0].get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        return _failure(ModelFailureKind.MALFORMED_RESPONSE, "the answer had no text field named 'choices[0].message.content'")
    text = message["content"]
    if not text.strip():
        if choices[0].get("finish_reason") == "length":  # the same D-150(c) treatment OllamaModel gives a cutoff
            return _failure(
                ModelFailureKind.EMPTY_RESPONSE,
                "the model returned no text: generation stopped at the output limit (finish_reason 'length') before any answer text",
            )
        return _failure(ModelFailureKind.EMPTY_RESPONSE, "the model returned no text")
    usage = document.get("usage") if isinstance(document.get("usage"), dict) else {}
    return ModelResponse(
        text=text,
        measured=MeasuredFacts(
            prompt_tokens=_count(usage.get("prompt_tokens")),
            output_tokens=_count(usage.get("completion_tokens")),
            elapsed_seconds=elapsed_seconds,
        ),
    )


def _count(value: object) -> int | None:
    """A token count the provider reported, or ``None`` — a bool, a negative or anything else is not a count."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _failure(kind: ModelFailureKind, message: str) -> ModelFailure:
    return ModelFailure(kind=kind, message=message)
