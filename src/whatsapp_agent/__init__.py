"""whatsapp-agent -- Python SDK and MCP server for the WhatsApp Agent Platform.

    from whatsapp_agent import WhatsAppAgentClient

    client = WhatsAppAgentClient()  # reads WHATSAPP_API_KEY from the environment
    for message in client.listen(auto_mark_read=True):
        client.reply_text(message, "Got it!")

See the package README and ``docs/`` for the full guide, including
``whatsapp_agent.formatting`` for WhatsApp's own text-formatting syntax and
``whatsapp_agent.mcp`` for the bundled MCP server.
"""
from __future__ import annotations

from . import formatting, markdown
from .client import WhatsAppAgentClient, hash_media_bytes, verify_media_sha256
from .errors import (
    AuthenticationError,
    InvalidRequestError,
    MediaError,
    NotAcceptedError,
    PollConflictError,
    RateLimitError,
    RecipientNotAllowedError,
    ServerError,
    WhatsAppAPIError,
)
from .models import Contact, MediaInfo, MediaRef, Message, MessageContext, Reaction, Status, Updates

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "WhatsAppAgentClient",
    "verify_media_sha256",
    "hash_media_bytes",
    # errors
    "WhatsAppAPIError",
    "AuthenticationError",
    "RateLimitError",
    "NotAcceptedError",
    "InvalidRequestError",
    "RecipientNotAllowedError",
    "MediaError",
    "PollConflictError",
    "ServerError",
    # models
    "Contact",
    "MediaRef",
    "MessageContext",
    "Reaction",
    "Message",
    "Status",
    "Updates",
    "MediaInfo",
    # submodules
    "formatting",
    "markdown",
]
