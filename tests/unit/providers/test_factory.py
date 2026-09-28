"""``model_port``: choosing an adapter by name (decisions.md D-135, D-234; V1.6 adds ``groq``)."""

import pytest

from eidos.providers import GroqModel, KNOWN_PROVIDERS, OllamaModel, model_port


def test_known_providers_are_exactly_ollama_and_groq():
    assert KNOWN_PROVIDERS == ("ollama", "groq")


def test_ollama_never_needed_an_api_key_and_still_does_not():
    port = model_port("ollama", base_url="http://model.example.test:1234")
    assert isinstance(port, OllamaModel) and port.base_url == "http://model.example.test:1234"
    # Passing one anyway (a caller that always forwards GROQ_API_KEY, say) is harmless: Ollama ignores it.
    same = model_port("ollama", base_url="http://model.example.test:1234", api_key="unused")
    assert isinstance(same, OllamaModel)


def test_groq_is_built_with_the_given_base_url_and_key():
    port = model_port("groq", base_url="https://api.groq.com/openai/v1", api_key="a-real-key")
    assert isinstance(port, GroqModel)
    assert (port.base_url, port.api_key) == ("https://api.groq.com/openai/v1", "a-real-key")


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_groq_without_a_usable_api_key_is_refused(bad):
    with pytest.raises(ValueError, match="api_key"):
        model_port("groq", base_url="https://api.groq.com/openai/v1", api_key=bad)


def test_an_unknown_provider_is_refused_and_names_the_known_ones():
    with pytest.raises(ValueError, match="unknown model provider"):
        model_port("bedrock", base_url="https://example.test")
