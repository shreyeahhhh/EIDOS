"""Tools EIDOS can use (decisions.md D-238): adapters for the ``ToolPort`` the agents define.

Exactly one exists, ``web/fetch``, which reads the public web pages a mission's goal names. It is configured, not built in: the service wires it only when the deployer lists the ``web_fetch`` action in
``EIDOS_ALLOWED_ACTIONS``, and a mission can use it only if it lists the action too. Nothing here is imported by the core layers, the agents or the runtime.
"""

from .web_fetch import (
    MAX_ADDRESSES_PER_CALL,
    WEB_FETCH_ACTION,
    WEB_FETCH_TOOL_ID,
    WebFetchTool,
    addresses_in,
    web_fetch_descriptor,
    web_fetch_registry,
)

__all__ = [
    "MAX_ADDRESSES_PER_CALL", "WEB_FETCH_ACTION", "WEB_FETCH_TOOL_ID", "WebFetchTool", "addresses_in", "web_fetch_descriptor", "web_fetch_registry",
]
