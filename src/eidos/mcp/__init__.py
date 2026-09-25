"""eidos.mcp — the one transport that speaks to a tool provider (decisions.md D-203, D-207; V1.2 Step 5).

    port = StdioMcpToolPort(launch=McpServerLaunch(argv=(...), env=(...)), registry=allowlist, provider_id="docs", max_message_bytes=65536)

A minimal, hand-rolled, standard-library client for **one** revision of the Model Context Protocol, ``2026-07-28``, over **stdio** to a **local, trusted**
server. It implements ``eidos.agents.ToolPort`` and nothing else: agents reach it only through the tool gate, which has already admitted the call, so
this package holds no policy. It has no SDK dependency, no HTTP or SSE transport, no OAuth, no resources, prompts, sampling or elicitation, no server of
its own and no support for earlier, handshake-based revisions. It is imported by no other package (a guard enforces that), and it is the only package that
starts a process.
"""

from .protocol import PROTOCOL_VERSION, normalise_call_result, schema_digest
from .stdio import McpServerLaunch, StdioMcpToolPort

__all__ = ["PROTOCOL_VERSION", "McpServerLaunch", "StdioMcpToolPort", "normalise_call_result", "schema_digest"]
