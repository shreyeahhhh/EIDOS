"""Choosing a model adapter by name (decisions.md D-135, D-234, D-246).

This package is the only place a vendor name may appear, so the service and the API name a provider only by the configuration string they are handed and get a ``ModelPort`` back. The endpoint is
the caller's explicit choice for the operator's own model: there is no default host or port.

Two operator providers (V1.6): ``ollama`` (the local development runtime) and ``groq`` (a hosted, OpenAI-compatible
provider, added for production execution where a local runtime has nothing to run on — decisions.md,
V1.6). ``api_key`` is required for and used only by ``groq``; ``ollama`` ignores it, unchanged from before.

Bring-your-own-key (D-246): ``hosted_model_port`` builds the same adapter for ``openai``, ``gemini`` or ``groq`` from a **fixed profile**. **The address is never the caller's**: a user supplies only a key
and a model name, so a user cannot make the server call a host of their choosing (no server-side request forgery through this door), and every address below is ``https``.
"""

from dataclasses import dataclass

from eidos.agents import ModelPort

from .groq import GroqModel
from .ollama import OllamaModel

KNOWN_PROVIDERS = ("ollama", "groq")


@dataclass(frozen=True, slots=True)
class HostedProfile:
    """What differs between the hosted providers that speak the OpenAI chat-completions protocol."""

    base_url: str
    token_parameter: str
    send_seed: bool


# Not verified against a live key in this repository (D-246): the addresses are the providers' published OpenAI-compatible ones, and the two differing parameters are set to what their documentation
# describes. If a provider refuses a request, its own explanation is what the user sees (D-242), so a wrong guess here is visible rather than silent.
HOSTED_PROFILES: dict[str, HostedProfile] = {
    "openai": HostedProfile(base_url="https://api.openai.com/v1", token_parameter="max_completion_tokens", send_seed=True),
    "gemini": HostedProfile(base_url="https://generativelanguage.googleapis.com/v1beta/openai", token_parameter="max_tokens", send_seed=False),
    "groq": HostedProfile(base_url="https://api.groq.com/openai/v1", token_parameter="max_tokens", send_seed=True),
}
USER_KEY_PROVIDERS = tuple(HOSTED_PROFILES)


def model_port(provider: str, *, base_url: str, api_key: str | None = None) -> ModelPort:
    """The ``ModelPort`` for ``provider`` at ``base_url``. Raises ``ValueError`` for a provider this package does not know, or for ``groq`` with no ``api_key``."""
    if provider == "ollama":
        return OllamaModel(base_url=base_url)
    if provider == "groq":
        if not api_key or not api_key.strip():
            raise ValueError("api_key (GROQ_API_KEY) is required for the 'groq' provider")
        return GroqModel(base_url=base_url, api_key=api_key)
    raise ValueError(f"unknown model provider {provider!r}; known: {', '.join(KNOWN_PROVIDERS)}")


def hosted_model_port(provider: str, api_key: str) -> ModelPort:
    """The ``ModelPort`` for a user's own key at a hosted provider's fixed address. Raises ``ValueError`` for a provider without a profile or a blank key; the message never contains the key."""
    profile = HOSTED_PROFILES.get(provider)
    if profile is None:
        raise ValueError(f"unknown provider {provider!r}; known: {', '.join(USER_KEY_PROVIDERS)}")
    return GroqModel(base_url=profile.base_url, api_key=api_key, token_parameter=profile.token_parameter, send_seed=profile.send_seed)
