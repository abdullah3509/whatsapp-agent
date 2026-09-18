# API reference

`WhatsAppAgentClient` covers every endpoint in the developer manual. This page groups methods by manual section; see each method's docstring (or `help(WhatsAppAgentClient.method)`) for full parameter details.

```python
from whatsapp_agent import WhatsAppAgentClient
client = WhatsAppAgentClient(api_key=None, base_url=..., http_timeout=30.0, client_side_rate_limiting=True)
```

- `api_key` — falls back to the `WHATSAPP_API_KEY` environment variable.
- `client_side_rate_limiting` — when `True` (default), calls block to stay within the manual's per-endpoint budgets instead of firing a request the server would 429. See [rate-limits.md](rate-limits.md).
- Use as a context manager (`with WhatsAppAgentClient() as client:`) to close the underlying session automatically, or call `client.close()`.

## §1 Send a message

| Method | Description |
|---|---|
| `send_message(to, type, payload, *, context_message_id=None)` | Low-level send for any message type. Prefer the typed helpers below. |
| `send_text(to, body, *, preview_url=False, context_message_id=None)` | Send text, max 4096 chars. `preview_url=True` previews the first `http(s)` URL in `body`. |
| `send_image(to, media_id, *, caption=None, context_message_id=None)` | Send a previously uploaded image. |
| `send_audio(to, media_id, *, context_message_id=None)` | Send audio. No caption field. |
| `send_video(to, media_id, *, caption=None, context_message_id=None)` | Send video. |
| `send_document(to, media_id, *, filename=None, caption=None, context_message_id=None)` | Send a document. |
| `send_sticker(to, media_id, *, context_message_id=None)` | Send a sticker. No caption field. |
| `reply_text(message, body, **kwargs)` | Convenience: `send_text` that threads `context_message_id` from an inbound `Message` or raw dict automatically. |
| `notify(body, **kwargs)` | Convenience: `send_text` to `WHATSAPP_USER_ID` (from `.env`/the environment). For a script that always messages the same person. |

All `send_*` methods validate length/caption caps locally and raise `ValueError` before making a request if they're violated. `to` accepts a bare id (`"15551234567"`) or an explicit `"user:15551234567"` — an `"agent:..."` id is rejected locally, since the API always rejects it too (manual p.5). Pass `to=None` (or use `notify()`) to send to `WHATSAPP_USER_ID` instead of naming a recipient every call.

**Retry behavior**: `429` and `503` (message not accepted for delivery) are retried automatically — both are documented as safe to retry. A `500`, a connection reset, or a client-side read timeout is *not* retried automatically, because the manual is explicit that these leave it unknown whether the message actually sent; retrying blindly risks a duplicate. Configure `http_timeout` well above your typical send latency so an ordinary delay isn't mistaken for a failure.

## §2 Receive messages

| Method | Description |
|---|---|
| `get_updates(*, offset=None, limit=50, timeout=15)` | One long-poll call. Returns an `Updates` object, or `None` on a 204 (nothing arrived before the timeout). |
| `listen(*, start="new", offset=None, limit=50, timeout=25, on_message=None, on_status=None, auto_mark_read=False, error_backoff=2.0)` | Loop `get_updates` forever, yielding each inbound `Message` and tracking the offset for you. |

`listen(start=...)`:

- `"new"` (default) — only messages from now on. Resolves "now" once, on the first successful poll, then always carries `next_offset` — it does **not** keep omitting `offset` on every empty poll, which would silently re-resolve "now" each time and could skip a message that arrived between two polls.
- `"all"` — replay up to 30 days of backlog (`offset=0`). Deduplicate on `message.id` if your handler isn't naturally idempotent.

Pass `offset=<a next_offset you saved>` to resume a specific point across process restarts, overriding `start`.

## §3 Read receipts & typing

| Method | Description |
|---|---|
| `mark_read(message_id, *, show_typing=False)` | Mark an inbound message read; optionally show a typing indicator in the same call. |
| `typing(message_id)` | Context manager: shows a typing indicator and refreshes it every ~20s so it survives past the platform's 25-second TTL, for as long as the `with` block runs. |

```python
with client.typing(message.id):
    reply = slow_llm_call(message.text)
client.reply_text(message, reply)
```

## §4 Media

| Method | Description |
|---|---|
| `upload_media(file_path, *, mime_type=None)` | Upload a local file, return its media id. Validates size/MIME locally first. |
| `upload_media_bytes(data, filename, *, mime_type=None)` | Same, for in-memory bytes. |
| `get_media_info(media_id)` | Fetch metadata (`MediaInfo`: `url`, `mime_type`, `sha256` (hex), `file_size`). |
| `download_media(media_id, dest_path)` | Fetch metadata, then download the bytes to `dest_path`. |
| `delete_media(media_id)` | Delete media you uploaded, or that was sent to you. |

Module-level helpers in `whatsapp_agent.client`:

- `verify_media_sha256(base64_sha256, hex_sha256) -> bool` — a message payload's `<type>.sha256` is Base64; `GET /media/<id>`'s `sha256` is hex (same digest, different encoding, manual p.13 vs p.22). Comparing the raw strings directly always returns `False`; use this.
- `hash_media_bytes(data) -> str` — SHA-256 of `data` as lowercase hex, matching `GET /media/<id>`'s encoding, for verifying downloaded bytes.

## §5 Errors

See [errors.md](errors.md) for the full exception hierarchy.

## §6 Rate limits

See [rate-limits.md](rate-limits.md).

## Data models (`whatsapp_agent.models`)

`Message`, `Status`, `Contact`, `Updates`, `MediaInfo`, `MediaRef`, `MessageContext`, `Reaction` — typed dataclasses parsed from the API's JSON. Every model keeps the original payload on `.raw` if you need a field this SDK doesn't surface yet.

```python
message.text          # str | None
message.media         # the populated MediaRef (image/audio/video/document/sticker), or None
message.image         # MediaRef | None, specifically
message.context       # MessageContext | None, if this message quotes another
message.raw           # the original dict
```
