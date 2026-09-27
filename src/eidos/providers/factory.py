"""Choosing a model adapter by name (decisions.md D-135, D-234).

This package is the only place a vendor name may appear, so the service and the API name a provider only by the configuration string they are handed and get a ``ModelPort`` back. The endpoint is
the caller's explicit choice: there is no default host or port.
"""

from eidos.agents import ModelPort

from .ollama import OllamaModel

KNOWN_PROVIDERS = ("ollama",)


def model_port(provider: str, *, base_url: str) -> ModelPort:
    """The ``ModelPort`` for ``provider`` at ``base_url``. Raises ``ValueError`` for a provider this package does not know."""
    if provider == "ollama":
        return OllamaModel(base_url=base_url)
    raise ValueError(f"unknown model provider {provider!r}; known: {', '.join(KNOWN_PROVIDERS)}")
