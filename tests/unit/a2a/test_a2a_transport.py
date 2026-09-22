"""``HttpxTransport`` (decisions.md D-171, D-173 item 1) — the one module that ever touches ``httpx``, exercised here
against ``httpx.MockTransport`` (no real socket, the default suite never reaches a real network)."""

import httpx
import pytest

from eidos.a2a.transport import HttpxTransport, TransportFailure, TransportFailureKind, TransportResponse


def transport_with(handler) -> HttpxTransport:
    return HttpxTransport(timeout_seconds=5.0, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_a_successful_response_is_returned_with_its_status_and_body():
    def handler(request):
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": "1", "result": {}})

    result = transport_with(handler).post_json("https://peer.example/rpc", "{}", headers={})
    assert isinstance(result, TransportResponse)
    assert result.status_code == 200 and '"jsonrpc"' in result.text


def test_a_non_2xx_status_is_still_a_transport_response_not_a_failure():
    """JSON-RPC reports its own errors inside a 200 body; client.py, not this module, decides what a status means."""

    def handler(request):
        return httpx.Response(500, text="internal error")

    result = transport_with(handler).post_json("https://peer.example/rpc", "{}", headers={})
    assert isinstance(result, TransportResponse) and result.status_code == 500


def test_a_connect_timeout_is_a_typed_timeout_failure():
    def handler(request):
        raise httpx.ConnectTimeout("timed out")

    result = transport_with(handler).post_json("https://peer.example/rpc", "{}", headers={})
    assert isinstance(result, TransportFailure) and result.kind is TransportFailureKind.TIMEOUT


def test_a_connection_error_is_a_typed_network_failure():
    def handler(request):
        raise httpx.ConnectError("refused")

    result = transport_with(handler).post_json("https://peer.example/rpc", "{}", headers={})
    assert isinstance(result, TransportFailure) and result.kind is TransportFailureKind.NETWORK


def test_the_body_and_headers_are_sent_exactly_as_given():
    seen = {}

    def handler(request):
        seen["body"] = request.content.decode("utf-8")
        seen["header"] = request.headers.get("x-test")
        return httpx.Response(200, json={"ok": True})

    transport_with(handler).post_json("https://peer.example/rpc", '{"a": 1}', headers={"x-test": "yes"})
    assert seen["body"] == '{"a": 1}' and seen["header"] == "yes"


def test_timeout_seconds_has_no_default_and_rejects_a_non_positive_value():
    with pytest.raises(TypeError):
        HttpxTransport()  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        HttpxTransport(timeout_seconds=0)
    with pytest.raises(ValueError):
        HttpxTransport(timeout_seconds=-1)
