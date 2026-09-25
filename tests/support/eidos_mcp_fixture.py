"""Test-support for the real MCP path: how to launch the local reference server and build the real stdio port for it (decisions.md D-203, D-207; V1.2 Step 5).

The server is ``mcp_search_documents_server.py`` in this directory, started with the current interpreter, no shell and an environment of exactly what
Windows needs to start Python at all (and nothing else, so nothing about the developer's machine reaches it). ``MAX_MESSAGE_BYTES`` is the fixture's cap
on one protocol line, chosen well above the allowlist's own 4096-byte result bound and well below the ``giant_line`` fault.
"""

import os
import sys
from pathlib import Path

from eidos.mcp import McpServerLaunch, StdioMcpToolPort

from eidos_search_fixture import PROVIDER_ID, search_registry

SERVER = Path(__file__).resolve().parent / "mcp_search_documents_server.py"
MAX_MESSAGE_BYTES = 65536


def server_launch(fault: str = "", argument: str = "") -> McpServerLaunch:
    env = tuple((name, os.environ[name]) for name in ("SYSTEMROOT",) if name in os.environ)
    extra = tuple(part for part in (fault, argument) if part)
    return McpServerLaunch(argv=(sys.executable, "-B", str(SERVER), *extra), env=env)


def make_mcp_port(*, fault: str = "", argument: str = "", registry=None, max_message_bytes: int = MAX_MESSAGE_BYTES) -> StdioMcpToolPort:
    return StdioMcpToolPort(
        launch=server_launch(fault, argument), registry=registry or search_registry(), provider_id=PROVIDER_ID, max_message_bytes=max_message_bytes,
    )
