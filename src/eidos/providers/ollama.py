"""The local model runtime adapter — the only place a vendor name appears (decisions.md D-135, D-136).

``OllamaModel`` implements ``eidos.agents.ModelPort`` over the runtime's HTTP API using the **standard library only**: no vendor SDK
and no new dependency (D-136). Nothing about the machine is assumed: the base URL is an **explicit, required** input (there is no
default host or port), and so are the model, the generation parameters and the timeout, which arrive in each ``ModelRequest`` (D-135).

The port is *total*: outages, timeouts and malformed answers come back as typed ``ModelFailure`` values, never raised and never read as
success. What the provider reports about a call (token counts) and what this adapter times are returned as ``MeasuredFacts``; a value the
provider did not report is ``None``, never a guess.

The timeout is passed to every socket operation of the call (connecting and each read). With streaming off, the runtime sends its answer
in one piece when generation ends, so the read wait is the generation wait; a peer that trickled bytes could in principle wait longer than
the timeout, which is why the timeout is the *only* bound on a call and not a guarantee of total elapsed time.

Only ``http`` and ``https`` URLs are accepted: the standard library would otherwise open ``file:`` and other schemes.
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

_PATH = "/api/generate"


@dataclass(frozen=True, slots=True, kw_only=True)
class OllamaModel:
    base_url: str  # required, no default: e.g. the scheme, host and port the owner's runtime listens on

    def __post_init__(self) -> None:
        parsed = urllib.parse.urlsplit(self.base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(f"base_url must be an http or https URL with a host, not {self.base_url!r}")

    def complete(self, request: ModelRequest) -> ModelResult:
        options = {
            "temperature": request.settings.parameters.temperature,
            "seed": request.settings.parameters.seed,
            "num_predict": request.settings.parameters.max_output_tokens,
        }
        body: dict[str, object] = {"model": request.settings.model, "prompt": request.prompt, "stream": False, "options": options}
        if request.system is not None:
            body["system"] = request.system
        http_request = urllib.request.Request(
            self.base_url.rstrip("/") + _PATH,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(http_request, timeout=request.settings.timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            return _failure(ModelFailureKind.UNAVAILABLE, f"the runtime answered HTTP status {error.code}")
        except urllib.error.URLError as error:
            if isinstance(error.reason, (socket.timeout, TimeoutError)):
                return _failure(ModelFailureKind.TIMEOUT, f"no answer within {request.settings.timeout_seconds} seconds")
            return _failure(ModelFailureKind.UNAVAILABLE, f"the runtime could not be reached: {error.reason}")
        except (socket.timeout, TimeoutError):
            return _failure(ModelFailureKind.TIMEOUT, f"no answer within {request.settings.timeout_seconds} seconds")
        except http.client.RemoteDisconnected:
            return _failure(ModelFailureKind.UNAVAILABLE, "the runtime closed the connection without answering")
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
    if not isinstance(document, dict) or not isinstance(document.get("response"), str):
        return _failure(ModelFailureKind.MALFORMED_RESPONSE, "the answer had no text field named 'response'")
    text = document["response"]
    if not text.strip():
        return _failure(ModelFailureKind.EMPTY_RESPONSE, "the model returned no text")
    return ModelResponse(
        text=text,
        measured=MeasuredFacts(
            prompt_tokens=_count(document.get("prompt_eval_count")),
            output_tokens=_count(document.get("eval_count")),
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
