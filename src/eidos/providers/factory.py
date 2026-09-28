"""Choosing a model adapter by name (decisions.md D-135, D-234).

This package is the only place a vendor name may appear, so the service and the API name a provider only by the configuration string they are handed and get a ``ModelPort`` back. The endpoint is
the caller's explicit choice: there is no default host or port.

Two adapters (V1.6): ``ollama`` (the local development runtime) and ``groq`` (a hosted, OpenAI-compatible
provider, added for production execution where a local runtime has nothing to run on — decisions.md,
V1.6). ``api_key`` is required for and used only by ``groq``; ``ollama`` ignores it, unchanged from before.
"""

from eidos.agents import ModelPort

from .groq import GroqModel
from .ollama import OllamaModel

KNOWN_PROVIDERS = ("ollama", "groq")


def model_port(provider: str, *, base_url: str, api_key: str | None = None) -> ModelPort:
    """The ``ModelPort`` for ``provider`` at ``base_url``. Raises ``ValueError`` for a provider this package does not know, or for ``groq`` with no ``api_key``."""
    if provider == "ollama":
        return OllamaModel(base_url=base_url)
    if provider == "groq":
        if not api_key or not api_key.strip():
            raise ValueError("api_key (GROQ_API_KEY) is required for the 'groq' provider")
        return GroqModel(base_url=base_url, api_key=api_key)
    raise ValueError(f"unknown model provider {provider!r}; known: {', '.join(KNOWN_PROVIDERS)}")
