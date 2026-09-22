"""The one narrow seam to the network: ``Transport.post_json`` (decisions.md D-171, D-173 item 1).

A JSON-RPC 2.0 binding always POSTs a JSON envelope to one configured URL, whatever the method (spec §9) — so the
whole transport surface EIDOS needs is one operation, mirroring ``eidos.agents.ModelPort``'s own shape: synchronous,
total (a failure comes back typed, never raised), and thread-safe.

``Transport`` is a ``Protocol`` — the seam a fake, network-free implementation substitutes for tests (D-136's own
precedent, applied here: the default suite never reaches a real network), exactly as ``ScriptedModel`` substitutes
for ``ModelPort``. ``HttpxTransport`` is the one real implementation, and the only module in ``eidos.a2a`` that
imports ``httpx`` (D-171: one new, narrow dependency, an optional extra — ``pip install 'eidos[a2a]'``).

The transport/network timeout (D-173 item 1) lives here, on ``HttpxTransport``, and nowhere else: never a domain
contract field, exactly as ``OllamaModel``'s HTTP timeout isn't one. It has no default (D-135's discipline, applied
here too): a caller states it, or construction fails loudly.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Protocol

try:
    import httpx
except ImportError as error:  # the optional extra is not installed (D-171)
    raise ImportError("eidos.a2a needs the optional 'a2a' extra: pip install 'eidos[a2a]'") from error


class TransportFailureKind(StrEnum):
    NETWORK = "network"  # could not connect, or the peer answered with a transport-level fault
    TIMEOUT = "timeout"  # exceeded this transport's own configured deadline


@dataclass(frozen=True, slots=True)
class TransportFailure:
    kind: TransportFailureKind
    message: str


@dataclass(frozen=True, slots=True)
class TransportResponse:
    """A response the peer sent, whatever its HTTP status — JSON-RPC reports its own errors inside a 200 body, so a
    non-2xx status is not itself a ``TransportFailure``; ``client.py`` decides what a given status and body mean."""

    status_code: int
    text: str


TransportResult = TransportResponse | TransportFailure


class Transport(Protocol):
    def post_json(self, url: str, body: str, *, headers: Mapping[str, str]) -> TransportResult: ...


class HttpxTransport:
    """``timeout_seconds`` is required, no default (D-135's discipline, D-173 item 1).

    ``client``, if given, is used exactly as constructed — the seam a test uses to inject
    ``httpx.Client(transport=httpx.MockTransport(handler))`` without a real socket, the same spirit as ``Transport``
    itself but one layer down, at ``httpx``'s own boundary rather than EIDOS's. Left unset, a real ``httpx.Client``
    bound to ``timeout_seconds`` is built once, at construction, and reused across calls.
    """

    def __init__(self, *, timeout_seconds: float, client: "httpx.Client | None" = None) -> None:
        if timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be positive, not {timeout_seconds!r}")
        self.timeout_seconds = timeout_seconds
        self.client = client if client is not None else httpx.Client(timeout=timeout_seconds)

    def post_json(self, url: str, body: str, *, headers: Mapping[str, str]) -> TransportResult:
        try:
            response = self.client.post(url, content=body.encode("utf-8"), headers=dict(headers))
        except httpx.TimeoutException:
            return TransportFailure(kind=TransportFailureKind.TIMEOUT, message=f"no answer within {self.timeout_seconds} seconds")
        except httpx.HTTPError as error:
            return TransportFailure(kind=TransportFailureKind.NETWORK, message=f"the request failed: {type(error).__name__}: {error}")
        return TransportResponse(status_code=response.status_code, text=response.text)
