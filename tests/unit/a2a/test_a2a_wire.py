"""The A2A v1.0 wire types (decisions.md D-171, D-172): exact JSON-RPC request shape, task-id extraction,
context-id handling, and the TaskState casing ADR-001 fixes (SCREAMING_SNAKE_CASE, never plain lowercase).

Every JSON body here is copied verbatim from the published specification's own worked examples (§6.6, §9.4) — this
file pins EIDOS's parser against the spec's own words, not against what ``client.py`` happens to produce.
"""

import json

import pytest
from pydantic import ValidationError

from eidos.a2a.wire import (
    Artifact,
    AuthenticationInfo,
    GetTaskRequest,
    JsonRpcRequest,
    JsonRpcResponse,
    MessageWire,
    Part,
    RoleWire,
    SendMessageConfiguration,
    SendMessageRequest,
    SendMessageResponse,
    StreamResponse,
    Task,
    TaskPushNotificationConfig,
    TaskStateWire,
    TaskStatusUpdateEvent,
)

# --- TaskState casing (ADR-001, resolving the casing question Step 2 left open) ----------------------------------


def test_every_task_state_wire_value_is_the_full_screaming_snake_case_proto_name():
    for member in TaskStateWire:
        assert member.value.startswith("TASK_STATE_")
        assert member.value == member.value.upper()


def test_task_state_member_names_match_agent_task_status_member_names_exactly():
    from eidos.contracts import AgentTaskStatus

    wire_names = {m.name for m in TaskStateWire}
    concluding_and_not = {m.name for m in AgentTaskStatus} - {"TIMED_OUT"}  # EIDOS's own, never a wire value
    assert wire_names == concluding_and_not


# --- the spec's own worked example (§6.6): SendMessage request/response, and the webhook push -----------------------


def test_the_send_message_request_shape_matches_the_specs_own_example():
    message = MessageWire(
        message_id="6dbc13b5-bd57-4c2b-b503-24e381b6c8d6",
        role=RoleWire.USER,
        parts=(Part(text="Generate the Q1 sales report. This usually takes a while. Notify me when it's ready."),),
    )
    configuration = SendMessageConfiguration(
        return_immediately=True,
        task_push_notification_config=TaskPushNotificationConfig(
            url="https://client.example.com/webhook/a2a-notifications",
            authentication=AuthenticationInfo(scheme="Bearer", credentials="secure-client-token-for-task-aaa"),
        ),
    )
    request = SendMessageRequest(message=message, configuration=configuration)
    document = json.loads(request.model_dump_json(by_alias=True, exclude_none=True))
    assert document["message"]["role"] == "ROLE_USER"
    assert document["message"]["messageId"] == "6dbc13b5-bd57-4c2b-b503-24e381b6c8d6"
    assert document["message"]["parts"][0]["text"].startswith("Generate the Q1 sales report")
    assert document["configuration"]["taskPushNotificationConfig"]["url"] == "https://client.example.com/webhook/a2a-notifications"
    assert document["configuration"]["taskPushNotificationConfig"]["authentication"] == {
        "scheme": "Bearer", "credentials": "secure-client-token-for-task-aaa",
    }


def test_the_send_message_response_parses_the_specs_own_example_task_shape():
    body = """
    {
      "task": {
        "id": "43667960-d455-4453-b0cf-1bae4955270d",
        "contextId": "c295ea44-7543-4f78-b524-7a38915ad6e4",
        "status": {"state": "TASK_STATE_SUBMITTED", "timestamp": "2024-03-15T11:00:00Z"}
      }
    }
    """
    response = SendMessageResponse.model_validate_json(body)
    assert response.task.id == "43667960-d455-4453-b0cf-1bae4955270d"
    assert response.task.context_id == "c295ea44-7543-4f78-b524-7a38915ad6e4"
    assert response.task.status.state is TaskStateWire.SUBMITTED
    assert response.message is None


def test_the_push_notification_body_parses_the_specs_own_example_status_update():
    body = """
    {
      "statusUpdate": {
        "taskId": "43667960-d455-4453-b0cf-1bae4955270d",
        "contextId": "c295ea44-7543-4f78-b524-7a38915ad6e4",
        "status": {"state": "TASK_STATE_COMPLETED", "timestamp": "2024-03-15T18:30:00Z"}
      }
    }
    """
    notification = StreamResponse.model_validate_json(body)
    assert notification.status_update.task_id == "43667960-d455-4453-b0cf-1bae4955270d"
    assert notification.status_update.context_id == "c295ea44-7543-4f78-b524-7a38915ad6e4"
    assert notification.status_update.status.state is TaskStateWire.COMPLETED
    assert notification.task is None and notification.message is None and notification.artifact_update is None


# --- the spec's own JSON-RPC envelope example (§9.4.1, §9.4.3) -------------------------------------------------------


def test_a_json_rpc_request_envelope_matches_the_specs_own_shape_and_method_names():
    envelope = JsonRpcRequest(id="1", method="SendMessage", params={})
    document = json.loads(envelope.model_dump_json(by_alias=True))
    assert document["jsonrpc"] == "2.0"
    assert document["method"] == "SendMessage"  # PascalCase, matching gRPC — not "message/send" (§5.3, verified)


def test_get_task_request_names_the_task_id_and_optional_history_length():
    request = GetTaskRequest(id="task-uuid", history_length=10)
    document = json.loads(request.model_dump_json(by_alias=True, exclude_none=True))
    assert document == {"id": "task-uuid", "historyLength": 10}


def test_a_json_rpc_error_response_parses_the_specs_own_example():
    body = """
    {
      "jsonrpc": "2.0",
      "id": 2,
      "error": {
        "code": -32001,
        "message": "Task not found",
        "data": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo"}]
      }
    }
    """
    response = JsonRpcResponse.model_validate_json(body)
    assert response.error.code == -32001 and response.error.message == "Task not found"
    assert response.result is None


def test_a_json_rpc_response_carries_exactly_one_of_result_or_error():
    with pytest.raises(ValidationError):
        JsonRpcResponse.model_validate({"id": "1", "result": {"a": 1}, "error": {"code": 1, "message": "x"}})
    with pytest.raises(ValidationError):
        JsonRpcResponse.model_validate({"id": "1"})


# --- context-id handling: optional at the Task level, required on TaskStatusUpdateEvent (spec's own field_behavior) --


def test_a_task_may_omit_its_context_id_but_a_status_update_event_always_names_one():
    task = Task.model_validate({"id": "t1", "status": {"state": "TASK_STATE_WORKING"}})
    assert task.context_id is None
    with pytest.raises(ValidationError):
        TaskStatusUpdateEvent.model_validate({"taskId": "t1", "status": {"state": "TASK_STATE_WORKING"}})  # no contextId


# --- Part's oneof and Artifact's part list ----------------------------------------------------------------------------


def test_a_part_carries_at_most_one_of_text_raw_url_data():
    Part(text="hello")  # fine
    Part()  # fine: none set is tolerated (a third party's content choice, parsed leniently)
    with pytest.raises(ValidationError):
        Part.model_validate({"text": "a", "url": "https://example.com"})


def test_an_artifact_carries_its_id_and_a_list_of_parts():
    artifact = Artifact.model_validate({"artifactId": "a1", "parts": [{"text": "hello"}]})
    assert artifact.artifact_id == "a1" and artifact.parts[0].text == "hello"


def test_a_send_message_response_carries_exactly_one_of_task_or_message():
    with pytest.raises(ValidationError):
        SendMessageResponse.model_validate({})  # neither
    with pytest.raises(ValidationError):
        SendMessageResponse.model_validate({
            "task": {"id": "t1", "status": {"state": "TASK_STATE_WORKING"}},
            "message": {"messageId": "m1", "role": "ROLE_AGENT", "parts": []},
        })  # both


def test_a_stream_response_carries_exactly_one_payload():
    with pytest.raises(ValidationError):
        StreamResponse.model_validate({})  # none set
    with pytest.raises(ValidationError):
        StreamResponse.model_validate({
            "task": {"id": "t1", "status": {"state": "TASK_STATE_WORKING"}},
            "message": {"messageId": "m1", "role": "ROLE_AGENT", "parts": []},
        })  # both set
