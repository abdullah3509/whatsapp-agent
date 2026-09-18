"""Tool implementations behind the MCP server, kept separate from the MCP
wiring in ``server.py`` so they can be unit-tested (or reused from a
different tool-calling framework) without spinning up a protocol server.

Every function takes a :class:`~whatsapp_agent.client.WhatsAppAgentClient`
explicitly rather than reading a module-global, so tests can pass a client
pointed at a mock transport.
"""
from __future__ import annotations

import base64
import mimetypes
import os
import tempfile
from typing import Any

from ..client import WhatsAppAgentClient
from ..errors import WhatsAppAPIError
from ..markdown import from_markdown


def send_text(
    client: WhatsAppAgentClient,
    to: str,
    body: str,
    *,
    reply_to: str | None = None,
    preview_url: bool = False,
    from_markdown_source: bool = False,
) -> dict[str, Any]:
    """Send a text message. Set ``from_markdown_source=True`` if ``body`` was
    written as Markdown (the default for most LLMs) and needs converting to
    WhatsApp's formatting syntax first -- see
    :func:`whatsapp_agent.markdown.from_markdown`.
    """
    if from_markdown_source:
        body = from_markdown(body)
    result = client.send_text(to, body, preview_url=preview_url, context_message_id=reply_to)
    return result


def send_media(
    client: WhatsAppAgentClient,
    to: str,
    media_type: str,
    media_id: str,
    *,
    caption: str | None = None,
    filename: str | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    """Send a previously uploaded media object. ``media_type`` is one of
    image/audio/video/document/sticker; use :func:`upload_media` first to
    get a ``media_id``.
    """
    senders = {
        "image": lambda: client.send_image(
            to, media_id, caption=caption, context_message_id=reply_to
        ),
        "audio": lambda: client.send_audio(to, media_id, context_message_id=reply_to),
        "video": lambda: client.send_video(
            to, media_id, caption=caption, context_message_id=reply_to
        ),
        "document": lambda: client.send_document(
            to, media_id, filename=filename, caption=caption, context_message_id=reply_to
        ),
        "sticker": lambda: client.send_sticker(to, media_id, context_message_id=reply_to),
    }
    sender = senders.get(media_type)
    if sender is None:
        raise ValueError(f"media_type must be one of {sorted(senders)}, got {media_type!r}")
    return sender()


def upload_media(
    client: WhatsAppAgentClient,
    *,
    file_path: str | None = None,
    base64_data: str | None = None,
    filename: str | None = None,
    mime_type: str | None = None,
) -> dict[str, Any]:
    """Upload media from a local ``file_path`` or from ``base64_data`` (with
    ``filename`` for its extension/MIME sniffing), returning its media id.
    Exactly one of ``file_path``/``base64_data`` must be given.
    """
    if bool(file_path) == bool(base64_data):
        raise ValueError("pass exactly one of file_path or base64_data")
    if file_path:
        media_id = client.upload_media(file_path, mime_type=mime_type)
    else:
        assert base64_data is not None
        if not filename:
            raise ValueError("filename is required when uploading base64_data")
        raw = base64.b64decode(base64_data)
        media_id = client.upload_media_bytes(raw, filename, mime_type=mime_type)
    return {"id": media_id}


def download_media(
    client: WhatsAppAgentClient, media_id: str, *, dest_path: str | None = None
) -> dict[str, Any]:
    """Download a media object's bytes to ``dest_path`` (a temp file if not
    given), returning the local path and metadata.
    """
    info = client.get_media_info(media_id)
    if dest_path is None:
        suffix = mimetypes.guess_extension(info.mime_type) or ""
        fd, dest_path = tempfile.mkstemp(suffix=suffix, prefix="whatsapp-media-")
        os.close(fd)
    path = client.download_media(media_id, dest_path)
    return {
        "path": str(path),
        "mime_type": info.mime_type,
        "file_size": info.file_size,
        "sha256_hex": info.sha256,
    }


def get_updates(
    client: WhatsAppAgentClient,
    *,
    offset: int | None = None,
    limit: int = 50,
    timeout: int = 15,
) -> dict[str, Any]:
    """One poll of inbound messages and statuses. Callers driving this tool
    on a schedule (an n8n polling trigger, for example) should persist
    ``next_offset`` and pass it back as ``offset`` on the next call --
    passing none each time only ever returns what arrived since *that* call
    started, which can miss messages between runs.
    """
    update = client.get_updates(offset=offset, limit=limit, timeout=timeout)
    if update is None:
        return {"messages": [], "statuses": [], "contacts": [], "next_offset": offset}
    return {
        "messages": [m.raw for m in update.messages],
        "statuses": [s.raw for s in update.statuses],
        "contacts": [c.raw for c in update.contacts],
        "next_offset": update.next_offset,
    }


def mark_read(
    client: WhatsAppAgentClient, message_id: str, *, show_typing: bool = False
) -> dict[str, Any]:
    """Mark an inbound message as read, optionally showing a typing
    indicator.
    """
    success = client.mark_read(message_id, show_typing=show_typing)
    return {"success": success}


def format_text(
    text: str,
    *,
    source: str = "markdown",
    bold_words: list[str] | None = None,
) -> dict[str, Any]:
    """Convert ``text`` to WhatsApp's formatting syntax. ``source="markdown"``
    (default) runs :func:`whatsapp_agent.markdown.from_markdown`;
    ``source="plain"`` returns ``text`` unchanged except for wrapping any
    ``bold_words`` given. Use this before calling ``send_text`` whenever the
    text was generated by an LLM, which almost always writes Markdown by
    default.
    """
    if source == "markdown":
        result = from_markdown(text)
    elif source == "plain":
        result = text
    else:
        raise ValueError(f"source must be 'markdown' or 'plain', got {source!r}")
    if bold_words:
        from ..formatting import bold

        for word in bold_words:
            result = result.replace(word, bold(word))
    return {"formatted": result}


def tool_error_payload(exc: WhatsAppAPIError) -> dict[str, Any]:
    """Shape a :class:`WhatsAppAPIError` into the structured payload MCP
    tool errors should carry, instead of a bare stack trace -- includes the
    manual's numeric code and trace id so a human debugging an n8n run has
    enough to act on.
    """
    return {
        "error": True,
        "http_status": exc.http_status,
        "code": exc.code,
        "message": exc.message,
        "details": exc.details,
        "fbtrace_id": exc.fbtrace_id,
        "type": type(exc).__name__,
    }
