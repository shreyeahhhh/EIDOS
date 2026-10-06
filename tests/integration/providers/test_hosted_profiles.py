"""The hosted-provider profiles behind bring-your-own-key (decisions.md D-246).

One adapter speaks to Groq, OpenAI and Gemini's OpenAI-compatible endpoint from a **fixed profile** each. What is held here, over a local fake server (no real provider is contacted, so nothing here says
that any of them accepts the request: that is recorded as unverified in D-246): each profile sends the output-limit parameter and the seed it is configured to; every address is ``https`` and fixed, so
a user supplies a key and a model name and never an address; and a key is never shown by ``repr`` or by an error message.
"""

import json
import urllib.parse

import pytest

from eidos.agents import GenerationParameters, ModelFailure, ModelRequest, ModelResponse, ModelSettings
from eidos.providers import HOSTED_PROFILES, USER_KEY_PROVIDERS, GroqModel, hosted_model_port

from eidos_fake_runtime import FakeRuntime, send_json

KEY = "sk-test-not-a-real-key-0123456789"


def request() -> ModelRequest:
    settings = ModelSettings(model="a-model", parameters=GenerationParameters(temperature=0.5, seed=9, max_output_tokens=64), timeout_seconds=5.0)
    return ModelRequest(settings=settings, prompt="Say hello.", system="Be brief.")


def answers(handler, body):
    send_json(handler, {"choices": [{"message": {"role": "assistant", "content": "hello"}}]})


def sent_to_a_fake(provider: str) -> dict:
    """What the adapter built for ``provider`` sends, with only its address pointed at a local fake (the profile's own parameters are used as they are)."""
    profile = HOSTED_PROFILES[provider]
    with FakeRuntime(answers) as runtime:
        result = GroqModel(base_url=runtime.url, api_key=KEY, token_parameter=profile.token_parameter, send_seed=profile.send_seed).complete(request())
    assert isinstance(result, ModelResponse)
    (path, headers, body), = runtime.requests
    assert headers["authorization"] == f"Bearer {KEY}"  # in the header, never in the URL or the body
    assert KEY not in path and KEY not in json.dumps(body)
    return body


def test_there_are_exactly_three_providers_a_user_may_bring_a_key_for():
    assert USER_KEY_PROVIDERS == ("openai", "gemini", "groq")


def test_openai_names_the_output_limit_max_completion_tokens_and_sends_the_seed():
    body = sent_to_a_fake("openai")
    assert body["max_completion_tokens"] == 64 and "max_tokens" not in body and body["seed"] == 9


def test_gemini_takes_max_tokens_and_is_sent_no_seed():
    body = sent_to_a_fake("gemini")
    assert body["max_tokens"] == 64 and "max_completion_tokens" not in body and "seed" not in body


def test_groq_is_unchanged_max_tokens_and_the_seed():
    body = sent_to_a_fake("groq")
    assert body["max_tokens"] == 64 and body["seed"] == 9 and "max_completion_tokens" not in body


@pytest.mark.parametrize("provider", USER_KEY_PROVIDERS)
def test_every_profile_address_is_a_fixed_https_url_with_a_host(provider):
    parsed = urllib.parse.urlsplit(HOSTED_PROFILES[provider].base_url)
    assert parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.query


@pytest.mark.parametrize("provider", USER_KEY_PROVIDERS)
def test_the_port_for_a_provider_uses_that_providers_own_address_and_settings(provider):
    port = hosted_model_port(provider, KEY)
    profile = HOSTED_PROFILES[provider]
    assert (port.base_url, port.token_parameter, port.send_seed) == (profile.base_url, profile.token_parameter, profile.send_seed)


def test_a_provider_without_a_profile_is_refused_and_ollama_is_not_one_a_user_can_bring():
    for provider in ("ollama", "anthropic", "", "OPENAI", "https://evil.example"):
        with pytest.raises(ValueError) as raised:
            hosted_model_port(provider, KEY)
        assert KEY not in str(raised.value)  # a user-chosen host or a local runtime is never reachable this way: the address cannot be supplied


def test_a_blank_key_is_refused_without_echoing_anything():
    with pytest.raises(ValueError) as raised:
        hosted_model_port("openai", "   ")
    assert "blank" in str(raised.value)


@pytest.mark.parametrize("provider", USER_KEY_PROVIDERS)
def test_a_key_never_appears_in_repr_or_str_of_the_adapter(provider):
    port = hosted_model_port(provider, KEY)
    assert KEY not in repr(port) and KEY not in str(port)


def test_a_failure_message_never_contains_the_key_even_when_the_provider_echoes_it():
    def echoes_the_key(handler, body):
        send_json(handler, {"error": {"message": f"Incorrect API key provided: {KEY}"}}, status=401)

    with FakeRuntime(echoes_the_key) as runtime:
        result = GroqModel(base_url=runtime.url, api_key=KEY, token_parameter="max_completion_tokens", send_seed=True).complete(request())
    assert isinstance(result, ModelFailure) and KEY not in result.message


def test_the_adapter_rejects_an_output_limit_parameter_it_does_not_know():
    with pytest.raises(ValueError):
        GroqModel(base_url="https://example.com/v1", api_key=KEY, token_parameter="max_new_tokens")
