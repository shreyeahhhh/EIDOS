"""The tool seam: ``ToolRequest`` / ``ToolResult`` / ``ToolFailure`` / ``ToolPort`` / ``bound_result`` (decisions.md D-203, D-135; V1.2 Step 2)."""

import pytest
from pydantic import ValidationError

from eidos.agents import (
    ToolArgument,
    ToolDocument,
    ToolFailure,
    ToolFailureKind,
    ToolOutcome,
    ToolPort,
    ToolRequest,
    ToolResult,
    bound_result,
)


def request(**overrides) -> ToolRequest:
    fields = dict(
        tool_id="docs/search_documents", arguments=(ToolArgument(name="limit", value=3), ToolArgument(name="query", value="evidence")),
        timeout_seconds=5.0, max_result_bytes=4096,
    ) | overrides
    return ToolRequest(**fields)


def doc(document_id="d1", content="text") -> ToolDocument:
    return ToolDocument(document_id=document_id, content=content)


# --- ToolArgument / ToolRequest --------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["text", "", 0, -3, 12])
def test_an_argument_value_is_a_string_or_an_integer(value):
    assert ToolArgument(name="a", value=value).value == value


@pytest.mark.parametrize("value", [True, False, 1.5, None, ["a"], b"x"])
def test_a_boolean_a_float_or_anything_else_is_not_an_argument_value(value):
    with pytest.raises(ValidationError):
        ToolArgument(name="a", value=value)


def test_a_request_lists_arguments_once_each_in_ascending_name_order():
    assert [argument.name for argument in request().arguments] == ["limit", "query"]
    with pytest.raises(ValidationError):
        request(arguments=(ToolArgument(name="query", value="x"), ToolArgument(name="limit", value=1)))
    with pytest.raises(ValidationError):
        request(arguments=(ToolArgument(name="query", value="x"), ToolArgument(name="query", value="y")))


def test_a_request_with_no_arguments_is_valid():
    assert request(arguments=()).arguments == ()


@pytest.mark.parametrize("field, bad", [("timeout_seconds", 0), ("timeout_seconds", -1), ("max_result_bytes", 0), ("max_result_bytes", -5), ("tool_id", "")])
def test_a_request_needs_a_positive_timeout_and_size_bound_and_a_tool(field, bad):
    with pytest.raises(ValidationError):
        request(**{field: bad})


def test_a_request_has_no_default_bound_a_caller_cannot_get_an_unbounded_call_by_omission():
    fields = {name: getattr(request(), name) for name in ToolRequest.model_fields}
    for omitted in ("timeout_seconds", "max_result_bytes"):
        with pytest.raises(ValidationError):
            ToolRequest(**{key: value for key, value in fields.items() if key != omitted})


def test_two_requests_for_the_same_call_are_equal_and_a_request_is_immutable_and_round_trips():
    assert request() == request()
    with pytest.raises(ValidationError):
        request().tool_id = "x/y"
    assert ToolRequest.model_validate_json(request().model_dump_json()) == request()


# --- ToolResult ------------------------------------------------------------------------------------------------------


def test_an_empty_result_is_a_real_result_not_a_failure():
    result = ToolResult(documents=())
    assert result.size_bytes == 0 and result.documents == ()


def test_a_result_lists_each_document_at_most_once():
    with pytest.raises(ValidationError):
        ToolResult(documents=(doc("a"), doc("a", "other")))


@pytest.mark.parametrize("document_id, content, expected", [
    ("d", "abc", 4),  # ASCII: one byte per character
    ("d", "é", 3),  # a 2-byte character in the content
    ("é", "€", 5),  # 2 bytes in the id, 3 in the content
    ("id", "", 2),
])
def test_the_size_is_the_utf_8_byte_size_of_every_id_and_text(document_id, content, expected):
    assert ToolResult(documents=(doc(document_id, content),)).size_bytes == expected


def test_the_size_adds_up_across_documents():
    assert ToolResult(documents=(doc("a", "xx"), doc("b", "yyy"))).size_bytes == 3 + 4


def test_a_document_needs_an_identifier_and_a_result_round_trips():
    with pytest.raises(ValidationError):
        ToolDocument(document_id="", content="x")
    result = ToolResult(documents=(doc("a"), doc("b", "€")))
    assert ToolResult.model_validate_json(result.model_dump_json()) == result


# --- ToolFailure -----------------------------------------------------------------------------------------------------


def test_the_failure_vocabulary_is_exactly_these_five_kinds():
    assert {kind.value for kind in ToolFailureKind} == {"unavailable", "timeout", "tool_error", "malformed_result", "result_too_large"}


def test_a_failure_states_why():
    with pytest.raises(ValidationError):
        ToolFailure(kind=ToolFailureKind.TIMEOUT, message="")
    assert ToolFailure(kind=ToolFailureKind.TIMEOUT, message="no answer in 5s").kind is ToolFailureKind.TIMEOUT


# --- bound_result ----------------------------------------------------------------------------------------------------


def test_a_result_exactly_at_the_bound_is_returned_itself():
    result = ToolResult(documents=(doc("d", "abc"),))  # 4 bytes
    assert bound_result(result, 4) is result


def test_a_result_one_byte_over_the_bound_is_a_typed_failure_that_says_both_numbers():
    outcome = bound_result(ToolResult(documents=(doc("d", "abc"),)), 3)
    assert isinstance(outcome, ToolFailure) and outcome.kind is ToolFailureKind.RESULT_TOO_LARGE
    assert "4" in outcome.message and "3" in outcome.message


def test_the_bound_counts_bytes_not_characters():
    result = ToolResult(documents=(doc("d", "€€€"),))  # 3 characters, 10 bytes with the id
    assert bound_result(result, 10) is result
    assert isinstance(bound_result(result, 9), ToolFailure)


def test_an_oversized_result_is_refused_whole_never_truncated():
    outcome = bound_result(ToolResult(documents=(doc("a", "x" * 50), doc("b", "y" * 50))), 60)
    assert isinstance(outcome, ToolFailure) and not hasattr(outcome, "documents")


def test_an_empty_result_always_fits():
    empty = ToolResult(documents=())
    assert bound_result(empty, 1) is empty


# --- the port --------------------------------------------------------------------------------------------------------


def test_a_scripted_port_satisfies_the_seam_and_answers_with_a_result_or_a_failure():
    class Scripted:
        def call(self, request: ToolRequest) -> ToolOutcome:
            return ToolResult(documents=(doc(),)) if request.tool_id.endswith("ok") else ToolFailure(kind=ToolFailureKind.UNAVAILABLE, message="down")

    port: ToolPort = Scripted()
    assert isinstance(port.call(request(tool_id="a/ok")), ToolResult)
    assert isinstance(port.call(request(tool_id="a/bad")), ToolFailure)
