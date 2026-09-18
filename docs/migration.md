# Migrating from the original `whatsapp_agent.py`

Before this became an installable package, this project was a single file, `whatsapp_agent.py`, dropped into a project and imported directly. That file has been replaced by two things:

- **The `whatsapp_agent` package** (`pip install whatsapp-agent`) — the same functionality, restructured, with the correctness fixes described below, plus typed models, automatic rate limiting, text formatting, and an MCP server. Use this for an agent or a long-running workflow.
- **[`standalone/whatsapp_agent.py`](../standalone/whatsapp_agent.py)** — a single-file, dependency-light (`requests` + `python-dotenv` only) client with the same two correctness fixes (offset tracking, `agent:` recipient rejection) applied, for projects that want to keep copy-pasting one file rather than installing a package. Copy it into your project as `whatsapp_agent.py` and `from whatsapp_agent import WhatsAppAgentClient` works exactly as it would after `pip install whatsapp-agent` — this is the direct successor to the original prototype, same shape, same method names, bugs fixed.

If you had the original file vendored into a project, here's what changed in each replacement.

## If you're moving to `standalone/whatsapp_agent.py`

Only two behavioral changes, both bug fixes, described in [Fixes that apply to both replacements](#fixes-that-apply-to-both-replacements) below. Everything else (method names, signatures, the raw-dict-based `Updates`/message shape) is unchanged; just replace your copy of the old file with the new one.

## If you're moving to the full package

Read on for the rest of this page.

## Fixes that apply to both replacements

Both `standalone/whatsapp_agent.py` and the full package fix the same two bugs from the original prototype:

1. **`listen()` no longer risks dropping a message.** See [below](#listen-no-longer-risks-dropping-a-message) for the full explanation.
2. **`to` rejects an `agent:<id>` recipient locally** instead of forwarding a request the API always rejects with HTTP 400 / `error.code` 131009 (manual p.5).

## Import

```diff
- from whatsapp_agent import WhatsAppAgentClient  # local file
+ pip install whatsapp-agent
+ from whatsapp_agent import WhatsAppAgentClient  # installed package, same import path
```

The class name and its constructor are unchanged: `WhatsAppAgentClient(api_key=None, base_url=..., http_timeout=30.0)`.

## `listen()` and `get_updates()` now return typed models, not raw dicts

The old client's `Updates` dataclass held `messages: list[dict]` — plain JSON. The new one holds `messages: list[Message]`, a typed dataclass. If you had code like:

```diff
- text = msg.get("text", {}).get("body", f"[{msg['type']}]")
- client.send_text(msg["from"], "Got it!", context_message_id=msg["id"])
+ text = message.text or f"[{message.type}]"
+ client.reply_text(message, "Got it!")
```

The original dict is still available on `.raw` for anything not yet surfaced as a typed field: `message.raw["type"]`.

<a id="listen-no-longer-risks-dropping-a-message"></a>
## `listen()` no longer risks dropping a message

The original `listen()` started with `offset=None` and, on a `204` (nothing arrived before the timeout), looped back with `offset` still `None`. The manual documents that omitting `offset` *re-resolves "now" on every such request* — so a message written between one empty poll's response and the next request's arrival could be silently skipped. The new `listen()` resolves "now" exactly once, on the first successful (non-204) poll, and always carries `next_offset` from then on. This is an internal fix with no API change — you don't need to do anything, but if you were working around the old behavior (e.g. always starting with `offset=0`), that workaround is no longer necessary.

`start="new"` (default) / `start="all"` replaces manually choosing between an absent `offset` and `offset=0` — see [api-reference.md](api-reference.md#2-receive-messages).

## Rate limiting is now automatic

The old client made no attempt to stay within the manual's per-endpoint budgets (12/min sends, 15/min polls, 12/min per media method). A `listen()` loop with a short timeout could burn through its own polling budget. The new client tracks each budget locally and blocks before a call that would exceed it — see [rate-limits.md](rate-limits.md). Disable with `WhatsAppAgentClient(client_side_rate_limiting=False)` if you're handling this yourself.

## New: local validation before sending

`send_text`, `upload_media`, etc. now check length/size/MIME-type caps locally and raise `ValueError` immediately, rather than making a request that the API would reject with a `400`. If you were catching `WhatsAppAPIError` around every send, you may also want to catch `ValueError` for these — or rely on the fact that a validation failure now surfaces faster and without a wasted network round trip.

## New: typed exceptions

The old client raised one exception class, `WhatsAppAPIError`, for everything. The new one raises a subclass per `error.code` (`AuthenticationError`, `RateLimitError`, `NotAcceptedError`, `InvalidRequestError`, `RecipientNotAllowedError`, `MediaError`, `PollConflictError`, `ServerError`) so you can branch on exception type instead of inspecting `.code`. `WhatsAppAPIError` itself, and all its attributes (`.http_status`, `.code`, `.message`, `.details`, `.fbtrace_id`), are unchanged, so existing `except WhatsAppAPIError:` handlers keep working without modification. See [errors.md](errors.md).

## New, not a replacement for anything

- `whatsapp_agent.formatting` and `whatsapp_agent.markdown` — WhatsApp text formatting, see [formatting.md](formatting.md).
- `whatsapp_agent.mcp` / `whatsapp-agent mcp` — the MCP server, see [mcp.md](mcp.md).
- `client.typing(message_id)` — a context manager that keeps a typing indicator alive past its 25-second TTL.
- `client.reply_text(message, body)` — a `send_text` shortcut that threads the reply automatically.
- `verify_media_sha256()` / `hash_media_bytes()` — handles the Base64-vs-hex encoding mismatch between an inbound message's `sha256` field and `GET /media/<id>`'s.
- The `whatsapp-agent` CLI (`listen`, `send`, `upload`, `mcp`, `doctor`).

## Everything else

Every other method — `send_image`, `send_audio`, `send_video`, `send_document`, `send_sticker`, `mark_read`, `upload_media`, `get_media_info`, `download_media`, `delete_media` — keeps the same name and the same parameters.
