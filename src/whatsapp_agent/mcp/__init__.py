"""MCP (Model Context Protocol) server exposing the WhatsApp Agent Platform
as a set of tools -- for n8n's MCP Client Tool node, Claude Desktop, Cursor,
or any other MCP host. See ``docs/mcp.md`` and ``docs/n8n.md`` for setup.

Requires the ``mcp`` extra: ``pip install "whatsapp-agent[mcp]"``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only for static analysis -- gives `whatsapp_agent.mcp.build_server` its
    # real type without eagerly importing the `mcp` package at runtime for
    # users who only want the plain SDK client (see __getattr__ below).
    from .server import build_server as build_server

__all__ = ["build_server"]


def __getattr__(name: str) -> object:
    # Deferred import so `import whatsapp_agent` doesn't require the `mcp`
    # package for users who only want the plain SDK client.
    if name == "build_server":
        from .server import build_server

        return build_server
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
