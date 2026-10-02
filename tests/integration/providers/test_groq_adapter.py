"""``GroqModel`` against a local *fake* Groq-shaped server over real sockets (decisions.md D-135, D-136, V1.6).

Mirrors ``test_ollama_adapter.py``'s coverage and style over the same ``FakeRuntime`` harness — the two
adapters share every contract (``ModelPort``, the four ``ModelFailureKind`` values, ``MeasuredFacts``);
only the wire shape (OpenAI-style chat completions) differs. No real Groq API is involved, so nothing
here says anything about a model's speed or quality.
"""

import socket
import threading
import time
import urllib.error

import pytest

from eidos.agents import (
    GenerationParameters,
    ModelFailure,
    ModelFailureKind,
    ModelRequest,
    ModelResponse,
    ModelSettings,
)
from eidos.providers import GroqModel

from eidos_fake_runtime import (
    FakeRuntime,
    closes_without_answering,
    free_port_with_nothing_listening,
    send_bytes,
    send_json,
    sends_a_truncated_body,
    sends_garbage,
    sleeps_then,
)

API_KEY = "test-key-not-a-real-secret"


def request(**overrides) -> ModelRequest:
    settings = ModelSettings(
        model="a-test-model",
        parameters=GenerationParameters(temperature=0.25, seed=42, max_output_tokens=128),
        timeout_seconds=overrides.pop("timeout_seconds", 5.0),
    )
    fields = dict(settings=settings, prompt="Say hello.", system="Be brief.")
    fields.update(overrides)
    return ModelRequest(**fields)


def replies(text, **extra_choice):
    """A Groq-shaped chat-completions answer, optionally reporting usage."""

    def behavior(handler, body):
        usage = {"prompt_tokens": extra_choice.pop("prompt_tokens")} if "prompt_tokens" in extra_choice else {}
        if "completion_tokens" in extra_choice:
            usage["completion_tokens"] = extra_choice.pop("completion_tokens")
        document = {"choices": [{"message": {"role": "assistant", "content": text}, **extra_choice}]}
        if usage:
            document["usage"] = usage
        send_json(handler, document)

    return behavior


# --- what is sent -------------------------------------------------------------------------------------------------------


def test_the_request_carries_exactly_the_explicit_settings_as_openai_shaped_messages():
    with FakeRuntime(replies("hello")) as runtime:
        GroqModel(base_url=runtime.url, api_key=API_KEY).complete(request())

    (path, headers, body), = runtime.requests
    assert path == "/chat/completions"
    assert headers["content-type"] == "application/json"
    assert headers["authorization"] == f"Bearer {API_KEY}"
    # Groq's Cloudflare answers Python's default identity with 403 "Error 1010" before the request reaches Groq: the adapter must name itself.
    assert headers["user-agent"].startswith("EIDOS-") and "python-urllib" not in headers["user-agent"].lower()
    assert body == {
        "model": "a-test-model",
        "messages": [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Say hello."}],
        "temperature": 0.25,
        "seed": 42,
        "max_tokens": 128,
    }


def test_no_system_message_is_sent_when_none_was_given():
    with FakeRuntime(replies("hello")) as runtime:
        GroqModel(base_url=runtime.url, api_key=API_KEY).complete(request(system=None))
    assert runtime.requests[0][2]["messages"] == [{"role": "user", "content": "Say hello."}]


def test_a_trailing_slash_on_the_base_url_is_harmless():
    with FakeRuntime(replies("hello")) as runtime:
        assert isinstance(GroqModel(base_url=runtime.url + "/", api_key=API_KEY).complete(request()), ModelResponse)
    assert runtime.requests[0][0] == "/chat/completions"


# --- what comes back ----------------------------------------------------------------------------------------------------


def test_a_good_answer_is_a_response_with_the_facts_the_provider_reported_and_a_measured_elapsed_time():
    with FakeRuntime(replies("Hello there.", prompt_tokens=11, completion_tokens=4)) as runtime:
        result = GroqModel(base_url=runtime.url, api_key=API_KEY).complete(request())

    assert isinstance(result, ModelResponse) and result.text == "Hello there."
    assert (result.measured.prompt_tokens, result.measured.output_tokens) == (11, 4)
    assert result.measured.elapsed_seconds is not None and result.measured.elapsed_seconds >= 0


def test_facts_the_provider_did_not_report_are_unknown_never_guessed():
    with FakeRuntime(replies("Hello.")) as runtime:
        result = GroqModel(base_url=runtime.url, api_key=API_KEY).complete(request())
    assert (result.measured.prompt_tokens, result.measured.output_tokens) == (None, None)


@pytest.mark.parametrize("junk", [-1, True, "12", 1.5, None, [3]])
def test_a_token_count_that_is_not_a_count_is_treated_as_unreported(junk):
    with FakeRuntime(replies("Hello.", prompt_tokens=junk, completion_tokens=junk)) as runtime:
        result = GroqModel(base_url=runtime.url, api_key=API_KEY).complete(request())
    assert isinstance(result, ModelResponse)
    assert (result.measured.prompt_tokens, result.measured.output_tokens) == (None, None)


# --- every failure is a typed value, never raised ---------------------------------------------------------------------------


def failure_of(behavior, **kwargs) -> ModelFailure:
    with FakeRuntime(behavior) as runtime:
        result = GroqModel(base_url=runtime.url, api_key=API_KEY).complete(request(**kwargs))
    assert isinstance(result, ModelFailure), result
    return result


def test_a_provider_that_is_not_listening_is_unavailable():
    port = free_port_with_nothing_listening()
    result = GroqModel(base_url=f"http://127.0.0.1:{port}", api_key=API_KEY).complete(request())
    assert isinstance(result, ModelFailure) and result.kind is ModelFailureKind.UNAVAILABLE
    assert "could not be reached" in result.message


@pytest.mark.parametrize("status", [400, 401, 404, 429, 500, 503], ids=["bad-request", "bad-key", "not-found", "rate-limited", "server-error", "unavailable"])
def test_an_error_status_is_unavailable_and_names_the_status_whatever_it_means(status):
    failure = failure_of(lambda handler, body: send_json(handler, {"error": {"message": "no"}}, status=status))
    assert failure.kind is ModelFailureKind.UNAVAILABLE and str(status) in failure.message


def test_the_providers_own_explanation_of_a_refusal_is_in_the_message_and_the_key_never_is():
    explanation = "The model `qwen3:4b` does not exist or you do not have access to it."
    failure = failure_of(lambda handler, body: send_json(handler, {"error": {"message": explanation, "type": "invalid_request_error", "code": "model_not_found"}}, status=404))
    assert failure.message == f"the provider answered HTTP status 404: {explanation}"  # a wrong model name is now told apart from a wrong URL or a bad key

    echoing = failure_of(lambda handler, body: send_json(handler, {"error": {"message": f"Invalid API Key: {API_KEY}"}}, status=401))
    assert API_KEY not in echoing.message and "[redacted]" in echoing.message


def test_a_call_that_outlasts_its_timeout_is_a_timeout_and_returns_promptly():
    started = time.monotonic()
    failure = failure_of(sleeps_then(3.0, replies("too late")), timeout_seconds=0.3)
    assert failure.kind is ModelFailureKind.TIMEOUT and "0.3" in failure.message
    assert time.monotonic() - started < 2.5  # it gave up at the timeout, it did not wait for the answer


def test_a_connection_dropped_without_an_answer_is_unavailable():
    failure = failure_of(closes_without_answering)
    assert failure.kind is ModelFailureKind.UNAVAILABLE


@pytest.mark.parametrize(
    "behavior",
    [
        lambda handler, body: send_bytes(handler, b"this is not json"),
        lambda handler, body: send_bytes(handler, b"\xff\xfe\x00"),
        lambda handler, body: send_json(handler, ["a", "list"]),
        lambda handler, body: send_json(handler, {"done": True}),
        lambda handler, body: send_json(handler, {"choices": []}),
        lambda handler, body: send_json(handler, {"choices": [{"message": {"content": 42}}]}),
        lambda handler, body: send_json(handler, {"choices": [{"message": {"content": None}}]}),
        lambda handler, body: send_json(handler, {"choices": [{"no_message_here": True}]}),
        sends_garbage,
        sends_a_truncated_body,
    ],
    ids=["not json", "not utf-8", "a list", "no choices field", "empty choices", "a numeric content", "a null content", "no message field", "not http", "truncated"],
)
def test_an_answer_that_is_not_in_the_promised_shape_is_malformed(behavior):
    assert failure_of(behavior).kind is ModelFailureKind.MALFORMED_RESPONSE


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_an_answer_with_no_text_is_empty_never_a_response(text):
    assert failure_of(replies(text)).kind is ModelFailureKind.EMPTY_RESPONSE


# --- an empty answer that stopped at the output limit says so (the D-150(c) treatment, mirrored from Ollama) -----------------


PLAIN = "the model returned no text"


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_an_empty_answer_that_stopped_at_the_output_limit_says_so_and_stays_an_empty_response(text):
    failure = failure_of(replies(text, finish_reason="length"))

    assert failure.kind is ModelFailureKind.EMPTY_RESPONSE
    assert failure.message.startswith(PLAIN)
    assert "stopped at the output limit" in failure.message and "'length'" in failure.message


def test_an_empty_answer_that_stopped_normally_keeps_the_plain_message():
    failure = failure_of(replies("", finish_reason="stop"))
    assert failure.kind is ModelFailureKind.EMPTY_RESPONSE and failure.message == PLAIN


def test_a_non_empty_answer_is_still_a_response_when_it_stopped_at_the_output_limit():
    with FakeRuntime(replies("The application runs as a single", finish_reason="length")) as runtime:
        result = GroqModel(base_url=runtime.url, api_key=API_KEY).complete(request())
    assert isinstance(result, ModelResponse) and result.text == "The application runs as a single"


def test_the_port_never_raises_whatever_the_provider_does():
    behaviors = [closes_without_answering, sends_garbage, sends_a_truncated_body, replies(""),
                 lambda handler, body: send_bytes(handler, b"{", status=200)]
    for behavior in behaviors:
        with FakeRuntime(behavior) as runtime:
            result = GroqModel(base_url=runtime.url, api_key=API_KEY).complete(request(timeout_seconds=1.0))
        assert isinstance(result, (ModelResponse, ModelFailure))


# --- configuration is explicit and cannot reach a file or another protocol ----------------------------------------------------


def test_the_base_url_and_the_api_key_are_required_there_is_no_default():
    with pytest.raises(TypeError):
        GroqModel()
    with pytest.raises(TypeError):
        GroqModel(base_url="https://api.groq.com/openai/v1")
    with pytest.raises(TypeError):
        GroqModel(api_key=API_KEY)


@pytest.mark.parametrize("bad", ["", "localhost:1234", "ftp://host/", "file:///etc/passwd", "http://", "//host", "host"])
def test_only_an_http_or_https_url_with_a_host_is_accepted(bad):
    with pytest.raises(ValueError, match="base_url"):
        GroqModel(base_url=bad, api_key=API_KEY)


@pytest.mark.parametrize("bad", ["", "   "])
def test_a_blank_api_key_is_refused(bad):
    with pytest.raises(ValueError, match="api_key"):
        GroqModel(base_url="https://api.groq.com/openai/v1", api_key=bad)


def test_the_adapter_is_immutable():
    model = GroqModel(base_url="https://api.groq.com/openai/v1", api_key=API_KEY)
    with pytest.raises(AttributeError):
        model.api_key = "something-else"


# --- thread safety ------------------------------------------------------------------------------------------------------------


def test_concurrent_calls_all_get_their_own_answer():
    results = []
    lock = threading.Lock()
    with FakeRuntime(lambda handler, body: send_json(handler, {"choices": [{"message": {"content": f"echo {body['messages'][-1]['content']}"}}]})) as runtime:
        model = GroqModel(base_url=runtime.url, api_key=API_KEY)

        def call(n):
            found = model.complete(request(prompt=f"p{n}"))
            with lock:
                results.append(found)

        threads = [threading.Thread(target=call, args=(n,)) for n in range(16)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert sorted(r.text for r in results) == sorted(f"echo p{n}" for n in range(16))
    assert len(runtime.requests) == 16


# --- failures the fake runtime cannot produce portably (a connect that times out): the transport is faked instead ---------------------


@pytest.mark.parametrize(
    "raised, kind",
    [
        (lambda: urllib.error.URLError(TimeoutError("timed out")), ModelFailureKind.TIMEOUT),
        (lambda: urllib.error.URLError(socket.timeout("timed out")), ModelFailureKind.TIMEOUT),
        (lambda: urllib.error.URLError(ConnectionRefusedError("refused")), ModelFailureKind.UNAVAILABLE),
        (lambda: TimeoutError("read timed out"), ModelFailureKind.TIMEOUT),
        (lambda: ConnectionResetError("reset"), ModelFailureKind.UNAVAILABLE),
        (lambda: OSError("network is unreachable"), ModelFailureKind.UNAVAILABLE),
    ],
    ids=["connect timeout", "connect socket timeout", "connect refused", "read timeout", "reset", "unreachable"],
)
def test_transport_errors_map_to_the_failure_they_mean(monkeypatch, raised, kind):
    def urlopen(*args, **kwargs):
        raise raised()

    monkeypatch.setattr("eidos.providers.groq.urllib.request.urlopen", urlopen)

    result = GroqModel(base_url="http://127.0.0.1:9", api_key=API_KEY).complete(request())

    assert isinstance(result, ModelFailure) and result.kind is kind
