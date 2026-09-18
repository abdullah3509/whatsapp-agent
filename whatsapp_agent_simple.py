#!/usr/bin/env python3
"""Simple, single-file client for the WhatsApp Agent Platform
(https://api.whatsapp.com/agent/v1).

This is the "just fire off a request" option: copy this one file into a
project (it needs only `requests` and `python-dotenv`) when you want to send
or receive WhatsApp messages from a plain script, a cron job, a monitoring
alert, or any other system that isn't an AI agent and doesn't need the full
package's typed models, per-endpoint rate limiting, or MCP server.

For an agent/workflow integration -- typed models, automatic rate limiting,
WhatsApp text formatting, and an MCP server for n8n/Claude/Cursor -- install
the full package instead: `pip install whatsapp-agent`. See README.md
("Two ways to use this") for when to reach for which.

Reads the agent's API token from WHATSAPP_API_KEY (.env or environment)
unless passed explicitly. Covers every endpoint in the developer manual:
sending messages, long-polling for updates, read receipts/typing, and media
upload/fetch/download/delete.
"""
from __future__ import annotations

import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.whatsapp.com/agent/v1"
MESSAGE_TYPES = {"text", "image", "audio", "video", "document", "sticker"}


class WhatsAppAPIError(Exception):
    """Raised for any non-2xx/204 response, mirroring the API's error envelope."""

    def __init__(self, http_status: int, code: int, message: str,
                 details: Optional[str] = None, fbtrace_id: Optional[str] = None):
        text = f"[HTTP {http_status}] error.code={code}: {message}"
        if details:
            text += f" -- {details}"
        super().__init__(text)
        self.http_status = http_status
        self.code = code
        self.message = message
        self.details = details
        self.fbtrace_id = fbtrace_id


@dataclass
class Updates:
    messages: list[dict]
    statuses: list[dict]
    contacts: list[dict]
    next_offset: Optional[int]
    raw: dict


class WhatsAppAgentClient:
    def __init__(self, api_key: Optional[str] = None, base_url: str = BASE_URL,
                 http_timeout: float = 30.0):
        self.api_key = api_key or os.getenv("WHATSAPP_API_KEY")
        if not self.api_key:
            raise ValueError("WHATSAPP_API_KEY is not set (pass api_key=, or set it in .env)")
        self.base_url = base_url.rstrip("/")
        self.http_timeout = http_timeout
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self.api_key}"

    # ---- low-level request handling ------------------------------------

    def _request(self, method: str, path: str, *, retry_on: frozenset[int] = frozenset(),
                 max_retries: int = 5, backoff_base: float = 1.0,
                 http_timeout: Optional[float] = None, **kwargs) -> requests.Response:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        attempt = 0
        while True:
            resp = self.session.request(method, url, timeout=http_timeout or self.http_timeout, **kwargs)
            if resp.status_code == 204 or resp.ok:
                return resp
            if resp.status_code in retry_on and attempt < max_retries:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else backoff_base * (2 ** attempt)
                time.sleep(delay)
                attempt += 1
                continue
            self._raise_for_error(resp)

    @staticmethod
    def _raise_for_error(resp: requests.Response) -> "None":
        try:
            err = resp.json()["error"]
        except (ValueError, KeyError):
            resp.raise_for_status()
            raise WhatsAppAPIError(resp.status_code, -1, resp.text or "unknown error")
        raise WhatsAppAPIError(
            http_status=resp.status_code,
            code=err.get("code", -1),
            message=err.get("message", ""),
            details=(err.get("error_data") or {}).get("details"),
            fbtrace_id=err.get("fbtrace_id"),
        )

    @staticmethod
    def _normalize_recipient(to: str) -> str:
        """Coerce a bare id into user:<id>. `to` only ever accepts user:<id>
        (manual p.5) -- an agent:<id> is rejected locally rather than
        forwarded to a request that is guaranteed to fail with HTTP 400 /
        error.code 131009.
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

    def send_message(self, to: Optional[str], type: str, payload: dict, *,
                      context_message_id: Optional[str] = None) -> dict:
        """`to=None` sends to WHATSAPP_USER_ID (from .env/the environment) --
        handy for a script that always notifies the same person.
        """
        if type not in MESSAGE_TYPES:
            raise ValueError(f"type must be one of {sorted(MESSAGE_TYPES)}, got {type!r}")
        to = to or os.getenv("WHATSAPP_USER_ID")
        if not to:
            raise ValueError(
                "'to' was not given and WHATSAPP_USER_ID is not set "
                "(pass to=, or set WHATSAPP_USER_ID in .env)"
            )
        body = {
            "messaging_product": "whatsapp",
            "to": self._normalize_recipient(to),
            "type": type,
            type: payload,
        }
        if context_message_id:
            body["context"] = {"message_id": context_message_id}
        # 503 (not accepted for delivery) means it was never sent, so it's safe to auto-retry;
        # a 500/timeout is left to the caller since a blind retry there can double-send.
        resp = self._request("POST", "/messages", json=body, retry_on=frozenset({429, 503}))
        return resp.json()

    def send_text(self, to: Optional[str], body: str, *, preview_url: bool = False,
                  context_message_id: Optional[str] = None) -> dict:
        payload = {"body": body}
        if preview_url:
            payload["preview_url"] = True
        return self.send_message(to, "text", payload, context_message_id=context_message_id)

    def send_image(self, to: Optional[str], media_id: str, *, caption: Optional[str] = None,
                   context_message_id: Optional[str] = None) -> dict:
        payload = {"id": media_id, **({"caption": caption} if caption else {})}
        return self.send_message(to, "image", payload, context_message_id=context_message_id)

    def send_audio(self, to: Optional[str], media_id: str, *,
                   context_message_id: Optional[str] = None) -> dict:
        return self.send_message(to, "audio", {"id": media_id}, context_message_id=context_message_id)

    def send_video(self, to: Optional[str], media_id: str, *, caption: Optional[str] = None,
                   context_message_id: Optional[str] = None) -> dict:
        payload = {"id": media_id, **({"caption": caption} if caption else {})}
        return self.send_message(to, "video", payload, context_message_id=context_message_id)

    def send_document(self, to: Optional[str], media_id: str, *, filename: Optional[str] = None,
                      caption: Optional[str] = None, context_message_id: Optional[str] = None) -> dict:
        payload = {"id": media_id}
        if filename:
            payload["filename"] = filename
        if caption:
            payload["caption"] = caption
        return self.send_message(to, "document", payload, context_message_id=context_message_id)

    def send_sticker(self, to: Optional[str], media_id: str, *,
                     context_message_id: Optional[str] = None) -> dict:
        return self.send_message(to, "sticker", {"id": media_id}, context_message_id=context_message_id)

    def notify(self, body: str, **kwargs) -> dict:
        """Send a text message to WHATSAPP_USER_ID -- for a script that
        always messages the same person (a monitoring alert, a cron job)
        without repeating the recipient id on every call.
        """
        return self.send_text(None, body, **kwargs)

    # ---- 2. receive messages ----------------------------------------------

    def get_updates(self, *, offset: Optional[int] = None, limit: int = 50,
                    timeout: int = 15) -> Optional[Updates]:
        params: dict[str, Any] = {"limit": limit, "timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        resp = self._request(
            "GET", "/updates", params=params,
            retry_on=frozenset({429, 500}),
            http_timeout=timeout + 10,  # long-poll: give the server room to hold the connection open
        )
        if resp.status_code == 204:
            return None
        data = resp.json()
        value = data["entry"][0]["changes"][0]["value"]
        return Updates(
            messages=value.get("messages", []),
            statuses=value.get("statuses", []),
            contacts=value.get("contacts", []),
            next_offset=data.get("next_offset"),
            raw=data,
        )

    def listen(self, *, offset: Optional[int] = None, limit: int = 50, timeout: int = 25,
               on_message: Optional[Callable[[dict], None]] = None,
               on_status: Optional[Callable[[dict], None]] = None,
               auto_mark_read: bool = False, error_backoff: float = 2.0) -> Iterator[dict]:
        """Long-poll forever, yielding each inbound message and advancing
        offset automatically.

        Starts offset-less (reads from "now") unless `offset` is given, and
        resolves that starting point exactly once: after the first
        successful (non-204) response, `next_offset` is always carried from
        then on, including across empty (204) polls. Re-omitting `offset` on
        every empty poll would re-resolve "now" each time and can silently
        skip a message that arrived between two polls -- pass `offset=0` to
        replay up to 30 days of backlog instead of starting from "now".
        """
        current_offset = offset
        resolved_head = current_offset is not None
        while True:
            try:
                update = self.get_updates(offset=current_offset, limit=limit, timeout=timeout)
            except WhatsAppAPIError as exc:
                if exc.http_status == 409:
                    raise  # a second poller is running for this agent -- that's a caller bug, not transient
                time.sleep(error_backoff)
                continue
            if update is None:
                continue  # 204: nothing to advance past, keep the same (possibly None) offset
            if not resolved_head:
                resolved_head = True
            current_offset = update.next_offset
            for status in update.statuses:
                if on_status:
                    on_status(status)
            for message in update.messages:
                if auto_mark_read:
                    self.mark_read(message["id"])
                if on_message:
                    on_message(message)
                yield message

    # ---- 3. read receipts & typing indicator -------------------------------

    def mark_read(self, message_id: str, *, show_typing: bool = False) -> bool:
        body = {"messaging_product": "whatsapp", "status": "read", "message_id": message_id}
        if show_typing:
            body["typing_indicator"] = {"type": "text"}
        resp = self._request("POST", "/statuses", json=body, retry_on=frozenset({429, 500, 503}))
        return resp.json().get("success", False)

    # ---- 4. media -----------------------------------------------------------

    def upload_media(self, file_path: str | Path, *, mime_type: Optional[str] = None) -> str:
        file_path = Path(file_path)
        mime_type = mime_type or mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        with open(file_path, "rb") as fh:
            files = {"file": (file_path.name, fh, mime_type)}
            data = {"messaging_product": "whatsapp", "type": mime_type}
            resp = self._request("POST", "/media", data=data, files=files, retry_on=frozenset({429, 500}))
        return resp.json()["id"]

    def get_media_info(self, media_id: str) -> dict:
        resp = self._request("GET", f"/media/{media_id}", retry_on=frozenset({429, 500}))
        return resp.json()

    def download_media(self, media_id: str, dest_path: str | Path) -> Path:
        info = self.get_media_info(media_id)
        dest_path = Path(dest_path)
        resp = self._request("GET", info["url"], retry_on=frozenset({429, 500}))
        dest_path.write_bytes(resp.content)
        return dest_path

    def delete_media(self, media_id: str) -> bool:
        resp = self._request("DELETE", f"/media/{media_id}", retry_on=frozenset({429, 500}))
        return resp.json().get("success", False)


if __name__ == "__main__":
    # Example: fire a one-off notification, the way a monitoring script or
    # cron job would -- no listen loop, no agent framework, just a request.
    client = WhatsAppAgentClient()
    if os.getenv("WHATSAPP_USER_ID"):
        client.notify("Notification: this script just ran.")
    else:
        print("Set WHATSAPP_USER_ID in .env to send a one-off notification, "
              "or import WhatsAppAgentClient and use it directly.")
