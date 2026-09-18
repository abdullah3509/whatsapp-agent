"""Builds the MCP server exposing WhatsApp as tools.

Uses the high-level ``MCPServer`` API from the official ``mcp`` Python SDK
(v2; ``MCPServer`` is the v2 name for what shipped as ``FastMCP`` in v1 --
see the SDK's migration guide if you're used to the old name). Each tool's
docstring is sent to the model as its description, so they are written for
an LLM audience, not a human reading the source -- see each one for what a
caller (an agent, or an n8n MCP Client Tool node) is expected to know.
"""
from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from ..client import WhatsAppAgentClient
from ..errors import WhatsAppAPIError
from . import tools as _tools


def build_server(client: WhatsAppAgentClient | None = None) -> MCPServer:
    """Build an :class:`MCPServer` wired to ``client`` (constructed from
    ``WHATSAPP_API_KEY`` if not given).

    Returned unstarted -- call ``.run()`` (stdio by default; pass
    ``transport="streamable-http", host=..., port=...`` for HTTP), per the
    ``mcp`` package's own server-running API. See ``docs/mcp.md`` for the
    CLI wrapper (``whatsapp-agent mcp``) most users should reach for instead
    of calling this directly.
    """
    wa = client or WhatsAppAgentClient()
    mcp = MCPServer(
        "whatsapp-agent",
        instructions=(
            "Tools for sending and receiving WhatsApp messages through the WhatsApp Agent "
            "Platform. This agent can only message the WhatsApp account that created it -- "
            "there is no way to message an arbitrary phone number. Always run wa_format_text "
            "on any body written as Markdown before sending it: WhatsApp uses its own "
            "formatting syntax (single '*' for bold, not '**'), and unconverted Markdown "
            "renders as literal punctuation in the chat."
        ),
    )

    @mcp.tool()
    def wa_send_text(
        to: str,
        body: str,
        reply_to: str | None = None,
        preview_url: bool = False,
        from_markdown_source: bool = False,
    ) -> dict[str, Any]:
        """Send a WhatsApp text message.

        Args:
            to: recipient, as `user:<id>` or a bare phone number/id -- use
                the `from` field of an inbound message exactly as received.
            body: message text, max 4096 characters. Must already be in
                WhatsApp formatting (single `*bold*`, `_italic_`, `~strike~`),
                not Markdown -- set from_markdown_source=True if it isn't.
            reply_to: message id to quote, from an inbound message's `id`.
            preview_url: show a link preview for the first http(s) URL in body.
            from_markdown_source: convert body from Markdown to WhatsApp
                formatting before sending. Turn this on whenever body was
                produced by an LLM, which writes Markdown by default.
        """
        return _run(lambda: _tools.send_text(
            wa, to, body, reply_to=reply_to, preview_url=preview_url,
            from_markdown_source=from_markdown_source,
        ))

    @mcp.tool()
    def wa_send_media(
        to: str,
        media_type: str,
        media_id: str,
        caption: str | None = None,
        filename: str | None = None,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Send previously uploaded media. Call wa_upload_media first to get
        a media_id.

        Args:
            to: recipient, as `user:<id>` or a bare phone number/id.
            media_type: one of image, audio, video, document, sticker.
            media_id: id returned by wa_upload_media.
            caption: optional, max 1024 characters. Not supported for audio
                or sticker.
            filename: optional, document only.
            reply_to: message id to quote.
        """
        return _run(lambda: _tools.send_media(
            wa, to, media_type, media_id, caption=caption, filename=filename, reply_to=reply_to,
        ))

    @mcp.tool()
    def wa_upload_media(
        file_path: str | None = None,
        base64_data: str | None = None,
        filename: str | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        """Upload a file for use in a later wa_send_media call. Pass exactly
        one of file_path (a path on the machine running this server) or
        base64_data (with filename set). Size and MIME type are validated
        against WhatsApp's per-type limits before uploading.

        Args:
            file_path: local path to the file to upload.
            base64_data: base64-encoded file contents, if not using file_path.
            filename: required with base64_data, for MIME/extension sniffing.
            mime_type: override the auto-detected MIME type.
        """
        return _run(lambda: _tools.upload_media(
            wa, file_path=file_path, base64_data=base64_data, filename=filename,
            mime_type=mime_type,
        ))

    @mcp.tool()
    def wa_download_media(media_id: str, dest_path: str | None = None) -> dict[str, Any]:
        """Download a media object's bytes to a local file.

        Args:
            media_id: the id from an inbound message's media payload.
            dest_path: where to save it; a temp file is created if omitted.
        """
        return _run(lambda: _tools.download_media(wa, media_id, dest_path=dest_path))

    @mcp.tool()
    def wa_get_updates(
        offset: int | None = None, limit: int = 50, timeout: int = 15
    ) -> dict[str, Any]:
        """Poll once for inbound messages and delivery/read statuses. This is
        the way to receive messages through this server -- there is no push
        notification, so call this on a schedule (e.g. an n8n polling
        trigger). Persist the returned next_offset and pass it back as
        offset on the next call; omitting offset each time only returns
        what arrived since that particular call started and can miss
        messages sent between runs.

        Args:
            offset: resume point from a previous call's next_offset. Omit
                only for the very first call.
            limit: max entries to return, up to 100.
            timeout: seconds to hold the connection open waiting for a
                message to arrive, up to 25. Keep this well under your
                workflow's own execution timeout.
        """
        return _run(lambda: _tools.get_updates(wa, offset=offset, limit=limit, timeout=timeout))

    @mcp.tool()
    def wa_mark_read(message_id: str, show_typing: bool = False) -> dict[str, Any]:
        """Mark an inbound message as read, optionally showing a typing
        indicator that lasts up to 25 seconds.

        Args:
            message_id: the id of an inbound message (not one you sent).
            show_typing: show a typing indicator alongside the read receipt.
        """
        return _run(lambda: _tools.mark_read(wa, message_id, show_typing=show_typing))

    @mcp.tool()
    def wa_format_text(
        text: str, source: str = "markdown", bold_words: list[str] | None = None
    ) -> dict[str, Any]:
        """Convert text to WhatsApp's formatting syntax before sending it.
        Run this on any text written as Markdown (the default for most LLM
        output) -- WhatsApp uses single markers ('*bold*', '_italic_',
        '~strike~'), not Markdown's '**bold**', and unconverted Markdown
        renders as literal asterisks in the chat.

        Args:
            text: the text to convert.
            source: "markdown" (default) to convert from Markdown, or
                "plain" to leave text as-is except for bold_words.
            bold_words: optional list of substrings to wrap in WhatsApp bold
                markers, applied after the source conversion.
        """
        return _tools.format_text(text, source=source, bold_words=bold_words)

    return mcp


def _run(fn: Any) -> dict[str, Any]:
    """Call ``fn`` and turn a :class:`WhatsAppAPIError` into a structured
    error payload instead of letting it propagate as a bare traceback, so a
    workflow calling this tool gets ``error.code`` and the trace id to act
    on (see the manual's per-endpoint "what to do" tables) rather than an
    opaque failure.
    """
    try:
        result: dict[str, Any] = fn()
        return result
    except WhatsAppAPIError as exc:
        return _tools.tool_error_payload(exc)
