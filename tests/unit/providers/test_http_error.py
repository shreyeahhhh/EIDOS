"""What a provider said when it refused a call (decisions.md D-242): the status is always there, the provider's own explanation is added when it gave one, and nothing here can fail or leak a key."""

import io
import json
import urllib.error

import pytest

from eidos.providers._http_error import MAX_DETAIL_CHARS, http_failure_message


def error(status: int, body: bytes | str | dict | list | None) -> urllib.error.HTTPError:
    if isinstance(body, (dict, list)):
        body = json.dumps(body)
    if isinstance(body, str):
        body = body.encode("utf-8")
    return urllib.error.HTTPError("http://example.invalid/x", status, "reason", {}, io.BytesIO(body) if body is not None else None)  # type: ignore[arg-type]


def test_a_groq_style_explanation_is_added_to_the_status():
    message = http_failure_message("the provider answered", error(404, {"error": {"message": "The model `qwen3:4b` does not exist or you do not have access to it.", "type": "invalid_request_error"}}))
    assert message == "the provider answered HTTP status 404: The model `qwen3:4b` does not exist or you do not have access to it."


def test_an_ollama_style_explanation_is_added_to_the_status():
    assert http_failure_message("the runtime answered", error(404, {"error": "model 'llama3' not found"})) == "the runtime answered HTTP status 404: model 'llama3' not found"


@pytest.mark.parametrize(
    "body",
    [None, b"", b"   ", "not json at all", b"\xff\xfe\x00 binary", {}, {"error": None}, {"error": {}}, {"error": {"message": ""}}, {"error": {"message": "   "}}, {"error": {"message": 7}}, {"error": 7}, {"detail": "x"}, ["error"], "null", "42"],
)
def test_without_a_usable_explanation_the_message_is_the_plain_status_line_exactly_as_before(body):
    assert http_failure_message("the provider answered", error(503, body)) == "the provider answered HTTP status 503"


def test_whitespace_in_the_explanation_is_collapsed_to_one_line():
    assert http_failure_message("p", error(400, {"error": {"message": "line one\n\n  line   two\ttab"}})).endswith(": line one line two tab")


def test_a_long_explanation_is_cut_to_a_fixed_length():
    message = http_failure_message("p", error(400, {"error": {"message": "x" * 5000}}))
    detail = message.split(": ", 1)[1]
    assert len(detail) == MAX_DETAIL_CHARS and detail.endswith("…")


def test_a_secret_that_appears_in_the_explanation_is_removed():
    key = "gsk_abcdefghijklmnop"
    message = http_failure_message("the provider answered", error(401, {"error": {"message": f"Invalid API Key provided: {key}. Check {key}."}}), secrets=(key,))
    assert key not in message and message.count("[redacted]") == 2 and "HTTP status 401" in message


def test_a_secret_cut_by_the_length_limit_cannot_survive_as_a_prefix():
    # The secret is replaced before the message is shortened, so a cut can never leave half of one behind.
    key = "S" * 40
    message = http_failure_message("p", error(401, {"error": {"message": "a" * (MAX_DETAIL_CHARS - 10) + key}}), secrets=(key,))
    assert "SSSS" not in message


def test_an_empty_secret_is_ignored():
    assert http_failure_message("p", error(400, {"error": {"message": "plain"}}), secrets=("",)) == "p HTTP status 400: plain"


def test_an_error_body_that_cannot_be_read_still_gives_the_status():
    class Unreadable(urllib.error.HTTPError):
        def read(self, *args, **kwargs):
            raise OSError("connection reset")

    assert http_failure_message("p", Unreadable("http://example.invalid/x", 502, "r", {}, None)) == "p HTTP status 502"  # type: ignore[arg-type]


def test_only_a_bounded_amount_of_the_body_is_read():
    seen = []

    class Recording(urllib.error.HTTPError):
        def read(self, amount=None):
            seen.append(amount)
            return b"{}"

    http_failure_message("p", Recording("http://example.invalid/x", 500, "r", {}, None))  # type: ignore[arg-type]
    assert seen and seen[0] is not None and seen[0] <= 16_384


def test_a_body_larger_than_the_read_bound_gives_the_plain_status_line_not_a_crash():
    huge = '{"error": {"message": "' + "x" * 40_000 + '"}}'
    assert http_failure_message("p", error(500, huge)) == "p HTTP status 500"  # cut mid-document, so not JSON: the status alone
