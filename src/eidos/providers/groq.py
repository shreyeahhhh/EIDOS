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
from typing import Callable

from eidos.agents import MeasuredFacts, ModelFailure, ModelFailureKind, ModelRequest, ModelResponse, ModelResult

from ._http_error import http_failure_message

_PATH = "/chat/completions"
# Groq's front door (Cloudflare) refuses Python's default "Python-urllib/3.x" identity with a 403 "Error 1010: Access denied" before the request reaches Groq at all, whatever the key. An adapter
# that names itself is let through (and a wrong key then gets the normal 401). Found on the first real use; no scripted test could have shown it.
USER_AGENT = "EIDOS-model-adapter/1"
# A rate limit (HTTP 429) is a request to wait. A free account's per-minute token allowance is small enough that one mission's own calls can use it up (D-244): the adapter waits as long as the provider
# asks, up to this many times and this long each, always inside the call's own timeout, and only then reports the refusal.
MAX_RATE_LIMIT_RETRIES = 3
MAX_RATE_LIMIT_WAIT_SECONDS = 30.0


@dataclass(frozen=True, slots=True, kw_only=True)
class GroqModel:
    base_url: str  # required, no default: e.g. https://api.groq.com/openai/v1
    api_key: str  # required, no default: the caller's own GROQ_API_KEY, read once at the composition root
    sleep: Callable[[float], None] = time.sleep  # how a rate-limit wait is made; a test hands in one that does not really wait

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
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}", "User-Agent": USER_AGENT},
            method="POST",
        )
        started = time.monotonic()
        deadline = started + request.settings.timeout_seconds  # one bound over every attempt and every wait
        retries = 0
        while True:
            try:
                with urllib.request.urlopen(http_request, timeout=max(deadline - time.monotonic(), 0.001)) as response:
                    raw = response.read()
                break
            except urllib.error.HTTPError as error:
                if error.code == 429:
                    # D-244: a rate limit is the provider saying "not yet", and it says how long. Wait that long (bounded) and ask again, rather than failing the whole mission step at once.
                    wait = _rate_limit_wait(error, retries)
                    if wait is not None and retries < MAX_RATE_LIMIT_RETRIES and time.monotonic() + wait < deadline:
                        self.sleep(wait)
                        retries += 1
                        continue
                # Covers a bad/expired key (401), a model the account cannot use (404), and a rate limit that outlasted the retries (429)
                # alike: all are "the provider answered with an error", which is exactly what UNAVAILABLE means.
                detail = http_failure_message("the provider answered", error, secrets=(self.api_key,))  # with Groq's own explanation (D-242)
                return _failure(ModelFailureKind.UNAVAILABLE, detail + (f" (after waiting and retrying {retries} time{'s' if retries != 1 else ''})" if retries else ""))
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
        elapsed = time.monotonic() - started  # the whole call, waits included: what the caller actually waited
        return _interpret(raw, elapsed)


def _rate_limit_wait(error: urllib.error.HTTPError, retries_so_far: int) -> float | None:
    """How long to wait before asking again after a 429, or ``None`` if it is not worth waiting.

    Groq sends ``Retry-After`` (seconds). A value above ``MAX_RATE_LIMIT_WAIT_SECONDS`` means "not soon": the failure is returned at once rather than holding a mission step for minutes. With no
    usable header the wait doubles from two seconds (2, 4, 8), capped the same way.
    """
    header = error.headers.get("retry-after") if error.headers is not None else None
    try:
        seconds = float(header) if header is not None else None
    except ValueError:
        seconds = None
    if seconds is not None and seconds == seconds and seconds >= 0:  # (a NaN is not a wait)
        return seconds if seconds <= MAX_RATE_LIMIT_WAIT_SECONDS else None
    return min(2.0 * (2**retries_so_far), MAX_RATE_LIMIT_WAIT_SECONDS)


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
