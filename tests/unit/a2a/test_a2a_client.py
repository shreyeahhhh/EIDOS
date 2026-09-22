"""``A2AClient`` (decisions.md D-171): submission and an optional reconciliation read, over a fake ``Transport``
(D-136's own precedent). Every scenario proves one of item 7's four boundaries, or a success path."""

import json

from eidos.a2a.client import A2AClient, A2AFailure, A2AFailureKind, Submitted, TaskSnapshot
from eidos.a2a.transport import TransportFailure, TransportFailureKind, TransportResponse
from eidos.a2a.wire import MessageWire, Part, RoleWire

from eidos_a2a_factories import FakeTransport, json_rpc_error, json_rpc_result, wire_task


def a_message() -> MessageWire:
    return MessageWire(message_id="m1", role=RoleWire.USER, parts=(Part(text="hello"),))


def test_send_message_always_sets_return_immediately_true():
    transport = FakeTransport(lambda url, body, headers: json_rpc_result(body, {"task": wire_task("t1")}))
    client = A2AClient(endpoint_url="https://peer.example/rpc", transport=transport)
    client.send_message(a_message())
    sent = json.loads(transport.calls[0][1])
    assert sent["method"] == "SendMessage"
    assert sent["params"]["configuration"]["returnImmediately"] is True


def test_send_message_success_returns_the_task_id_and_context_id():
    transport = FakeTransport(lambda url, body, headers: json_rpc_result(body, {"task": wire_task("t1", context_id="c1", state="TASK_STATE_SUBMITTED")}))
    client = A2AClient(endpoint_url="https://peer.example/rpc", transport=transport)
    result = client.send_message(a_message())
    assert isinstance(result, Submitted)
    assert result.task_id == "t1" and result.context_id == "c1"


def test_send_message_treats_any_immediate_state_as_submitted_never_branching_on_it():
    """D-165 rule 5: the caller never blocks on or branches over the immediate state — WORKING is just as much a
    successful submission as SUBMITTED itself."""
    transport = FakeTransport(lambda url, body, headers: json_rpc_result(body, {"task": wire_task("t1", state="TASK_STATE_WORKING")}))
    client = A2AClient(endpoint_url="https://peer.example/rpc", transport=transport)
    result = client.send_message(a_message())
    assert isinstance(result, Submitted)  # still a Submitted, not treated specially


# --- item 7's four boundaries -------------------------------------------------------------------------------------


def test_boundary_one_a_transport_network_failure():
    transport = FakeTransport(lambda url, body, headers: TransportFailure(kind=TransportFailureKind.NETWORK, message="connection refused"))
    client = A2AClient(endpoint_url="https://peer.example/rpc", transport=transport)
    result = client.send_message(a_message())
    assert isinstance(result, A2AFailure) and result.kind is A2AFailureKind.NETWORK


def test_boundary_two_a_transport_level_timeout():
    transport = FakeTransport(lambda url, body, headers: TransportFailure(kind=TransportFailureKind.TIMEOUT, message="no answer within 5.0 seconds"))
    client = A2AClient(endpoint_url="https://peer.example/rpc", transport=transport)
    result = client.send_message(a_message())
    assert isinstance(result, A2AFailure) and result.kind is A2AFailureKind.TRANSPORT_TIMEOUT


def test_boundary_three_a_malformed_response_not_valid_json():
    transport = FakeTransport(lambda url, body, headers: TransportResponse(status_code=200, text="not json at all {"))
    client = A2AClient(endpoint_url="https://peer.example/rpc", transport=transport)
    result = client.send_message(a_message())
    assert isinstance(result, A2AFailure) and result.kind is A2AFailureKind.MALFORMED_RESPONSE


def test_boundary_three_a_malformed_response_does_not_match_the_expected_shape():
    transport = FakeTransport(lambda url, body, headers: json_rpc_result(body, {"nonsense": True}))
    client = A2AClient(endpoint_url="https://peer.example/rpc", transport=transport)
    result = client.send_message(a_message())
    assert isinstance(result, A2AFailure) and result.kind is A2AFailureKind.MALFORMED_RESPONSE


def test_boundary_three_a_send_message_response_with_only_a_message_has_nothing_to_correlate():
    transport = FakeTransport(lambda url, body, headers: json_rpc_result(body, {"message": {"messageId": "m9", "role": "ROLE_AGENT", "parts": []}}))
    client = A2AClient(endpoint_url="https://peer.example/rpc", transport=transport)
    result = client.send_message(a_message())
    assert isinstance(result, A2AFailure) and result.kind is A2AFailureKind.MALFORMED_RESPONSE


def test_boundary_four_a_well_formed_protocol_error():
    transport = FakeTransport(lambda url, body, headers: json_rpc_error(body, -32001, "Task not found"))
    client = A2AClient(endpoint_url="https://peer.example/rpc", transport=transport)
    result = client.send_message(a_message())
    assert isinstance(result, A2AFailure) and result.kind is A2AFailureKind.PROTOCOL_ERROR
    assert result.code == -32001 and result.message == "Task not found"


# --- get_task ------------------------------------------------------------------------------------------------------


def test_get_task_success_returns_a_snapshot():
    transport = FakeTransport(lambda url, body, headers: json_rpc_result(body, wire_task("t1", context_id="c1", state="TASK_STATE_COMPLETED")))
    client = A2AClient(endpoint_url="https://peer.example/rpc", transport=transport)
    result = client.get_task("t1")
    assert isinstance(result, TaskSnapshot)
    assert result.task_id == "t1" and result.context_id == "c1"

    sent = json.loads(transport.calls[0][1])
    assert sent["method"] == "GetTask" and sent["params"]["id"] == "t1"


def test_get_task_never_called_by_send_message_itself():
    """D-170: nothing here decides when to poll — a single send_message call makes exactly one request."""
    transport = FakeTransport(lambda url, body, headers: json_rpc_result(body, {"task": wire_task("t1")}))
    client = A2AClient(endpoint_url="https://peer.example/rpc", transport=transport)
    client.send_message(a_message())
    assert transport.call_count == 1
