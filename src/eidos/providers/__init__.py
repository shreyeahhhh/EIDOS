"""Model-provider adapters — milestone V0.4, Step 8; ``GroqModel`` added V1.6 (decisions.md D-135, D-136).

This package is the **only** place a vendor, model or SDK name may appear. Every adapter implements ``eidos.agents.ModelPort`` and nothing
else; agents never import this package, and no core layer does.

    from eidos.providers import OllamaModel, GroqModel
    model = OllamaModel(base_url="http://<host>:<port>")                          # local development
    model = GroqModel(base_url="https://api.groq.com/openai/v1", api_key="...")   # hosted production

Standard library only (D-136) — for both adapters. Installing the runtime, choosing a model and holding
the Groq API key are the owner's actions, never Claude Code's.
"""

from .factory import HOSTED_PROFILES, KNOWN_PROVIDERS, USER_KEY_PROVIDERS, HostedProfile, hosted_model_port, model_port
from .groq import GroqModel
from .ollama import OllamaModel

__all__ = ["HOSTED_PROFILES", "KNOWN_PROVIDERS", "USER_KEY_PROVIDERS", "GroqModel", "HostedProfile", "OllamaModel", "hosted_model_port", "model_port"]
