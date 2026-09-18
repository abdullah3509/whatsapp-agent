"""The main SDK client: :class:`WhatsAppAgentClient`.

Covers every endpoint in the WhatsApp Agent Platform developer manual (v1,
August 25, 2026): sending messages, long-polling for updates, read
receipts/typing, and media upload/fetch/download/delete.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import mimetypes
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from . import constants as const
from .errors import InvalidRequestError, PollConflictError, WhatsAppAPIError
from .models import MediaInfo, Message, Status, Updates
from .ratelimit import RateLimiter
from .transport import Transport

load_dotenv()


class WhatsAppAgentClient:
    """Client for the WhatsApp Agent Platform (``/agent/v1``).

    Reads the agent's API token from ``WHATSAPP_API_KEY`` (``.env`` or the
    environment) unless ``api_key`` is passed explicitly. Reads a default
    recipient from ``WHATSAPP_USER_ID`` for any ``send_*`` call (or
    :meth:`notify`) that omits ``to`` -- handy for a single-recipient
    notification sender.

    :param api_key: the agent's API token. Falls back to the
        ``WHATSAPP_API_KEY`` environment variable.
    :param base_url: override for testing against a different host.
    :param http_timeout: default per-request socket timeout, in seconds.
        The manual recommends configuring this well above the standard send
        duration so an ordinary delay doesn't get treated as a lost request
        (p.9) -- see :meth:`send_message`.
    :param client_side_rate_limiting: when True (default), calls block to
        stay within the manual's documented per-endpoint budgets (p.28)
        instead of firing a request that the server will reject with 429.
        Disable if you are running your own external rate limiting (e.g.
        sharing one token's budget across multiple processes).
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = const.BASE_URL,
        http_timeout: float = 30.0,
        *,
        client_side_rate_limiting: bool = True,
    ):
        self.api_key = api_key or os.getenv("WHATSAPP_API_KEY")
        if not self.api_key:
            raise ValueError("WHATSAPP_API_KEY is not set (pass api_key=, or set it in .env)")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.api_key}"
        rate_limiter = (
            RateLimiter(
                {
                    "messages": const.RATE_LIMITS["messages"],
                    "statuses": const.RATE_LIMITS["statuses"],
                    "updates": const.RATE_LIMITS["updates"],
                    "media_post": const.RATE_LIMITS["media_post"],
                    "media_get": const.RATE_LIMITS["media_get"],
                    "media_delete": const.RATE_LIMITS["media_delete"],
                }
            )
            if client_side_rate_limiting
            else None
        )
        self._transport = Transport(
            self.session, base_url, http_timeout=http_timeout, rate_limiter=rate_limiter
        )

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._transport.close()

    def __enter__(self) -> WhatsAppAgentClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # ---- participant identifiers ---------------------------------------

    @staticmethod
    def _normalize_recipient(to: str) -> str:
        """Coerce a bare phone number/id into ``user:<id>``.

        ``to`` on ``POST /messages`` accepts only ``user:<id>`` -- an
        ``agent:<id>`` there is rejected with HTTP 400 / code 131009 (manual
        p.5), so unlike a general "normalize either prefix" helper, this
        specifically refuses to pass an ``agent:`` prefix through, since
        doing so would just forward a request that is guaranteed to fail.
        """
        if ":" not in to:
            return f"user:{to}"
        prefix, _, _ = to.partition(":")
        if prefix != "user":
            raise ValueError(
                f"'to' must be a user:<id> (or a bare id), got {to!r}. "
                "An agent:<id> cannot be a message recipient (manual p.5)."
            )
        return to

    # ---- 1. send a message ----------------------------------------------

    def send_message(
        self,
        to: str | None,
        type: str,
        payload: dict[str, Any],
        *,
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Send an outbound message of any ``type`` (manual p.5).

        Prefer the ``send_text``/``send_image``/etc. helpers below, which
        validate their payload locally before the request. Call this
        directly only for a message type or payload shape those don't cover.

        :param to: recipient. Pass ``None`` to send to ``WHATSAPP_USER_ID``
            (from ``.env``/the environment) -- handy for a fixed-recipient
            notification sender that doesn't want to repeat the id on every
            call. Raises ``ValueError`` if ``None`` and that variable isn't set.

        .. note::
           The manual recommends configuring the client read timeout well
           above the ordinary send duration (p.9): a ``500``, a connection
           reset, or your own read timeout all leave it *unknown* whether the
           message was actually sent, and blindly retrying then risks a
           duplicate. A ``503`` (not accepted for delivery) is the one
           outcome the manual guarantees means it was never sent, so it -- and
           ``429`` -- are retried automatically here; everything else is left
           to the caller. See :class:`whatsapp_agent.transport.Transport`.

           Concurrent sends to the *same* recipient are not ordered by the
           server (manual p.9) -- don't issue two ``send_*`` calls to one
           recipient without waiting for the first to return.
        """
        if type not in const.MESSAGE_TYPES:
            raise ValueError(f"type must be one of {sorted(const.MESSAGE_TYPES)}, got {type!r}")
        to = to or os.getenv("WHATSAPP_USER_ID")
        if not to:
            raise ValueError(
                "'to' was not given and WHATSAPP_USER_ID is not set "
                "(pass to=, or set WHATSAPP_USER_ID in .env)"
            )
        body: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": self._normalize_recipient(to),
            "type": type,
            type: payload,
        }
        if context_message_id:
            body["context"] = {"message_id": context_message_id}
        resp = self._transport.request(
            "POST",
            "/messages",
            json=body,
            bucket="messages",
            auto_retry_not_accepted=True,
        )
        return dict(resp.json())

    def send_text(
        self,
        to: str | None,
        body: str,
        *,
        preview_url: bool = False,
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a text message (manual p.6-7). ``body`` must be 1-4096
        characters; validated locally before the request.

        :param preview_url: render a link preview for the *first* URL in
            ``body``. That URL must start with ``http://`` or ``https://``
            (manual p.7) -- checked locally when this is True.
        """
        _validate_text_body(body)
        if preview_url and not _contains_previewable_url(body):
            raise ValueError(
                "preview_url=True but body contains no http:// or https:// URL to preview"
            )
        payload: dict[str, Any] = {"body": body}
        if preview_url:
            payload["preview_url"] = True
        return self.send_message(to, "text", payload, context_message_id=context_message_id)

    def send_image(
        self,
        to: str | None,
        media_id: str,
        *,
        caption: str | None = None,
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a previously uploaded image by ``media_id`` (manual p.6-7)."""
        payload = _media_payload(media_id, caption=caption)
        return self.send_message(to, "image", payload, context_message_id=context_message_id)

    def send_audio(
        self, to: str | None, media_id: str, *, context_message_id: str | None = None
    ) -> dict[str, Any]:
        """Send a previously uploaded audio clip by ``media_id``. Audio has
        no caption field (manual p.21).
        """
        return self.send_message(
            to, "audio", {"id": media_id}, context_message_id=context_message_id
        )

    def send_video(
        self,
        to: str | None,
        media_id: str,
        *,
        caption: str | None = None,
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a previously uploaded video by ``media_id``."""
        payload = _media_payload(media_id, caption=caption)
        return self.send_message(to, "video", payload, context_message_id=context_message_id)

    def send_document(
        self,
        to: str | None,
        media_id: str,
        *,
        filename: str | None = None,
        caption: str | None = None,
        context_message_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a previously uploaded document by ``media_id``."""
        payload = _media_payload(media_id, caption=caption, filename=filename)
        return self.send_message(to, "document", payload, context_message_id=context_message_id)

    def send_sticker(
        self, to: str | None, media_id: str, *, context_message_id: str | None = None
    ) -> dict[str, Any]:
        """Send a previously uploaded sticker by ``media_id``. Stickers have
        no caption field (manual p.21).
        """
        return self.send_message(
            to, "sticker", {"id": media_id}, context_message_id=context_message_id
        )

    def reply_text(
        self, message: Message | dict[str, Any], body: str, **kwargs: Any
    ) -> dict[str, Any]:
        """Convenience: reply to an inbound ``message`` with a text message
        quoting it, threading ``context_message_id`` from ``message.id``.
        Accepts either a :class:`~whatsapp_agent.models.Message` or the raw
        inbound dict.
        """
        sender = message.from_ if isinstance(message, Message) else message["from"]
        msg_id = message.id if isinstance(message, Message) else message["id"]
        return self.send_text(sender, body, context_message_id=msg_id, **kwargs)

    def notify(self, body: str, **kwargs: Any) -> dict[str, Any]:
        """Convenience: send a text message to ``WHATSAPP_USER_ID`` (from
        ``.env``/the environment). For a script that always messages the
        same person -- a monitoring alert, a cron job -- so you don't have
        to pass ``to`` on every call. Equivalent to
        ``send_text(None, body, **kwargs)``; raises ``ValueError`` if
        ``WHATSAPP_USER_ID`` isn't set.
        """
        return self.send_text(None, body, **kwargs)

    # ---- 2. receive messages ----------------------------------------------

    def get_updates(
        self,
        *,
        offset: int | None = None,
        limit: int = const.DEFAULT_POLL_LIMIT,
        timeout: int = const.DEFAULT_POLL_TIMEOUT,
    ) -> Updates | None:
        """One long-poll call to ``GET /updates`` (manual pp.9-15).

        Returns ``None`` on a 204 (timeout elapsed, nothing to deliver) --
        re-poll with the *same* ``offset`` in that case; there is no
        ``next_offset`` to advance to (manual p.15).

        Prefer :meth:`listen` for a continuous loop -- it gets the
        offset-carrying right automatically. Call this directly only if you
        need to control the poll cadence yourself (e.g. one poll per
        scheduler tick, as in the MCP tool ``wa_get_updates``).
        """
        params: dict[str, Any] = {"limit": limit, "timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        resp = self._transport.request(
            "GET",
            "/updates",
            params=params,
            bucket="updates",
            # long-poll: give the server room to hold the connection open
            http_timeout=timeout + 10,
        )
        if resp.status_code == 204:
            return None
        return Updates.from_dict(resp.json())

    def listen(
        self,
        *,
        start: str = "new",
        offset: int | None = None,
        limit: int = const.DEFAULT_POLL_LIMIT,
        timeout: int = 25,
        on_message: Callable[[Message], None] | None = None,
        on_status: Callable[[Status], None] | None = None,
        auto_mark_read: bool = False,
        error_backoff: float = 2.0,
    ) -> Iterator[Message]:
        """Long-poll forever, yielding each inbound :class:`Message` and
        advancing the offset automatically.

        :param start: how to choose the very first poll's starting point
            (manual p.15, "Starting a new agent") -- ignored if ``offset`` is
            given explicitly.

            - ``"new"`` (default): only messages that arrive *after* this
              call starts. The manual documents this as omitting ``offset``
              on the first request, but is explicit that doing so
              *re-resolves the head at the moment each such request
              arrives* -- so unlike a naive implementation that keeps
              omitting ``offset`` across retries/204s, this resolves the
              head **exactly once**, on the very first successful poll, and
              carries ``next_offset`` from then on. Re-omitting ``offset()``
              on every empty poll (the bug in earlier drafts of this client)
              can silently skip a message that arrived between two polls.
            - ``"all"``: replay up to 30 days of backlog by starting at
              ``offset=0`` (manual p.15). Deduplicate on ``message.id`` or
              filter on ``message.timestamp`` before acting on replayed
              messages if your handler isn't naturally idempotent.
        :param offset: resume from a specific offset you saved earlier
            (e.g. persisted ``next_offset`` from a previous run). Overrides
            ``start``.
        """
        if offset is not None:
            current_offset: int | None = offset
        elif start == "all":
            current_offset = 0
        elif start == "new":
            current_offset = None
        else:
            raise ValueError(f"start must be 'new' or 'all', got {start!r}")

        resolved_head = current_offset is not None
        while True:
            try:
                update = self.get_updates(offset=current_offset, limit=limit, timeout=timeout)
            except PollConflictError:
                # A second poller is running for this agent -- that's a
                # caller bug (the manual says to run exactly one poll loop
                # per agent), not a transient condition. Don't retry it.
                raise
            except WhatsAppAPIError:
                time.sleep(error_backoff)
                continue

            if update is None:
                # 204: timeout elapsed, nothing delivered. There is no
                # next_offset on a 204 (manual p.15) -- re-poll with the
                # same offset, which for the very first "new" poll means
                # deliberately staying offset-less so the head keeps
                # resolving to "now" until something actually arrives.
                continue

            if not resolved_head:
                # First successful response after an offset-less "new"
                # start: from here on we always carry next_offset, so the
                # head is never re-resolved again and nothing written
                # between two polls can be missed.
                resolved_head = True
            current_offset = update.next_offset

            for status in update.statuses:
                if on_status:
                    on_status(status)
            for message in update.messages:
                if auto_mark_read:
                    self.mark_read(message.id)
                if on_message:
                    on_message(message)
                yield message

    # ---- 3. read receipts & typing indicator -------------------------------

    def mark_read(self, message_id: str, *, show_typing: bool = False) -> bool:
        """Mark an inbound message as read, optionally showing a typing
        indicator in the same call (manual p.16-17).
        """
        body: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        if show_typing:
            body["typing_indicator"] = {"type": "text"}
        resp = self._transport.request("POST", "/statuses", json=body, bucket="statuses")
        return bool(resp.json().get("success", False))

    @contextmanager
    def typing(self, message_id: str) -> Iterator[None]:
        """Context manager that shows a typing indicator for ``message_id``
        and refreshes it periodically so it survives longer than the
        platform's 25-second TTL (manual p.17: "The indicator disappears
        once you reply, or after 25 seconds, whichever comes first. For a
        reply that takes longer than that, repeat the call to refresh the
        indicator.").

        Runs the refresh on a background thread; stops automatically when
        the ``with`` block exits (typically because you're about to send the
        reply, which clears the indicator anyway).

        Example::

            with client.typing(message.id):
                reply = call_slow_llm(message.text)
            client.reply_text(message, reply)
        """
        stop = threading.Event()

        def _refresh() -> None:
            self.mark_read(message_id, show_typing=True)
            while not stop.wait(const.TYPING_INDICATOR_REFRESH_INTERVAL):
                self.mark_read(message_id, show_typing=True)

        thread = threading.Thread(target=_refresh, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=5)

    # ---- 4. media -----------------------------------------------------------

    def upload_media(
        self, file_path: str | Path, *, mime_type: str | None = None
    ) -> str:
        """Upload a local file for use in an outbound message, returning its
        media id (manual p.18-21). Validates the file's size and MIME type
        locally, against the accepted-type tables, before uploading.
        """
        file_path = Path(file_path)
        mime_type = mime_type or mimetypes.guess_type(file_path.name)[0] or const.GENERIC_MIME_TYPE
        size = file_path.stat().st_size
        _validate_media(mime_type, size)
        with open(file_path, "rb") as fh:
            files = {"file": (file_path.name, fh, mime_type)}
            data = {"messaging_product": "whatsapp", "type": mime_type}
            resp = self._transport.request(
                "POST", "/media", data=data, files=files, bucket="media_post"
            )
        return str(resp.json()["id"])

    def upload_media_bytes(
        self, data: bytes, filename: str, *, mime_type: str | None = None
    ) -> str:
        """Like :meth:`upload_media`, for in-memory bytes rather than a file
        on disk (e.g. media generated on the fly, or received from another
        API).
        """
        mime_type = mime_type or mimetypes.guess_type(filename)[0] or const.GENERIC_MIME_TYPE
        _validate_media(mime_type, len(data))
        files = {"file": (filename, data, mime_type)}
        form = {"messaging_product": "whatsapp", "type": mime_type}
        resp = self._transport.request(
            "POST", "/media", data=form, files=files, bucket="media_post"
        )
        return str(resp.json()["id"])

    def get_media_info(self, media_id: str) -> MediaInfo:
        """Fetch metadata for a media object (manual p.21-22)."""
        resp = self._transport.request("GET", f"/media/{media_id}", bucket="media_get")
        return MediaInfo.from_dict(resp.json())

    def download_media(self, media_id: str, dest_path: str | Path) -> Path:
        """Fetch a media object's metadata, then download its bytes to
        ``dest_path`` (manual p.23).
        """
        info = self.get_media_info(media_id)
        dest_path = Path(dest_path)
        resp = self._transport.request("GET", info.url, bucket="media_get")
        dest_path.write_bytes(resp.content)
        return dest_path

    def delete_media(self, media_id: str) -> bool:
        """Delete a media object you uploaded, or one that was sent to you
        (manual p.23-24). Media also expires automatically after 30 days.
        """
        resp = self._transport.request(
            "DELETE", f"/media/{media_id}", bucket="media_delete"
        )
        return bool(resp.json().get("success", False))


# ---- module-level helpers ---------------------------------------------------


def verify_media_sha256(base64_sha256: str, hex_sha256: str) -> bool:
    """Compare a message payload's ``<type>.sha256`` (Base64, manual p.13)
    against ``GET /media/<id>``'s ``sha256`` (hex, manual p.22) -- the same
    digest, encoded two different ways depending on which endpoint returned
    it. Comparing the two strings directly always returns False even when
    the underlying bytes match; use this instead.
    """
    try:
        decoded = base64.b64decode(base64_sha256, validate=True)
    except (binascii.Error, ValueError):
        return False
    return decoded.hex() == hex_sha256.lower()


def hash_media_bytes(data: bytes) -> str:
    """SHA-256 of ``data`` as lowercase hex, matching the encoding
    ``GET /media/<id>`` uses for its ``sha256`` field (manual p.22) -- for
    verifying downloaded bytes against that field directly.
    """
    return hashlib.sha256(data).hexdigest()


def _media_payload(
    media_id: str, *, caption: str | None = None, filename: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": media_id}
    if caption is not None:
        if len(caption) > const.CAPTION_MAX_LENGTH:
            raise ValueError(
                f"caption is {len(caption)} characters; max is {const.CAPTION_MAX_LENGTH}"
            )
        payload["caption"] = caption
    if filename is not None:
        payload["filename"] = filename
    return payload


def _validate_text_body(body: str) -> None:
    if not body:
        raise ValueError("text body must not be empty")
    if len(body) > const.TEXT_BODY_MAX_LENGTH:
        raise ValueError(
            f"text body is {len(body)} characters; max is {const.TEXT_BODY_MAX_LENGTH} "
            "(manual p.7). Use whatsapp_agent.formatting.truncate() to cut it down safely."
        )


def _contains_previewable_url(body: str) -> bool:
    return "http://" in body or "https://" in body


def _validate_media(mime_type: str, size: int) -> None:
    kind = const.MIME_TO_KIND.get(mime_type)
    if kind is None and mime_type != const.GENERIC_MIME_TYPE:
        raise InvalidRequestError(
            400,
            131053,
            f"({131053}) MIME type not accepted",
            details=(
                f"{mime_type!r} is not in the accepted MIME type list for any media kind, "
                f"and is not {const.GENERIC_MIME_TYPE}. See whatsapp_agent.constants."
                "ACCEPTED_MIME_TYPES (manual pp.19-21)."
            ),
        )
    limit = const.MEDIA_SIZE_LIMITS.get(kind or "", const.GENERIC_MEDIA_SIZE_LIMIT)
    if size > limit:
        raise InvalidRequestError(
            400,
            131053,
            f"({131053}) File too large",
            details=f"{size} bytes exceeds the {limit}-byte limit for {kind or 'this'} media "
            "(manual p.4, p.19).",
        )
