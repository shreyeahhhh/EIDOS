"""Model-provider adapters — milestone V0.4, Step 8 (decisions.md D-135, D-136).

This package is the **only** place a vendor, model or SDK name may appear. Every adapter implements ``eidos.agents.ModelPort`` and nothing
else; agents never import this package, and no core layer does.

    from eidos.providers import OllamaModel
    model = OllamaModel(base_url="http://<host>:<port>")   # explicit: there is no default

Standard library only (D-136). Installing the runtime and choosing a model are the owner's actions, never Claude Code's.
"""

from .ollama import OllamaModel

__all__ = ["OllamaModel"]
