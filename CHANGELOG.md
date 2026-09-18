# Changelog

All notable changes to this project are documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows [Semantic Versioning](https://semver.org/) once it reaches 1.0.

## [0.1.0] - 2026-09-18

Initial public release. Restructures the original single-file `whatsapp_agent.py` prototype into an installable package — see `docs/migration.md` for what changed for existing users of that file.

### Added

- `WhatsAppAgentClient` covering every endpoint in the WhatsApp Agent Platform developer manual (v1): sending text/image/audio/video/document/sticker messages, long-polling for updates, read receipts and typing indicators, and media upload/fetch/download/delete.
- Typed exception hierarchy (`AuthenticationError`, `RateLimitError`, `NotAcceptedError`, `InvalidRequestError`, `RecipientNotAllowedError`, `MediaError`, `PollConflictError`, `ServerError`) mapped from `error.code`, all subclassing the original `WhatsAppAPIError`.
- Typed data models (`Message`, `Status`, `Contact`, `Updates`, `MediaInfo`, `MediaRef`, `MessageContext`, `Reaction`) in place of raw dicts, each keeping the original payload on `.raw`.
- Automatic, per-endpoint client-side rate limiting matching the manual's documented rolling-60s budgets.
- `whatsapp_agent.formatting` — WhatsApp's own inline text formatting syntax (`bold`, `italic`, `strike`, `code`, `mono`, `quote`, `bullet_list`, `numbered_list`, `escape`, `strip_formatting`, `truncate`).
- `whatsapp_agent.markdown.from_markdown` — converts Markdown (LLMs' default output style) to WhatsApp formatting, degrading headings/links/tables/rules to something readable in a chat.
- MCP server (`whatsapp-agent mcp`, stdio or `--http`) exposing `wa_send_text`, `wa_send_media`, `wa_upload_media`, `wa_download_media`, `wa_get_updates`, `wa_mark_read`, and `wa_format_text` as tools for n8n, Claude Desktop, Cursor, or any MCP host.
- `whatsapp-agent` CLI: `listen`, `send`, `upload`, `mcp`, `doctor`.
- `client.typing()` context manager that keeps a typing indicator alive past its 25-second TTL.
- `client.reply_text()` convenience for threaded replies.
- `verify_media_sha256()` / `hash_media_bytes()` handling the Base64-vs-hex encoding mismatch between an inbound message's `sha256` and `GET /media/<id>`'s.
- `standalone/whatsapp_agent.py` — a standalone, dependency-light (`requests` + `python-dotenv` only) single-file client for notification-sending use cases outside an agent/workflow context, carrying forward the two correctness fixes (offset tracking, `agent:` recipient rejection) without the rest of the package's machinery. Named to match the installed package's import path, so `from whatsapp_agent import WhatsAppAgentClient` works identically whether you copied this file or ran `pip install`.

### Fixed (relative to the original single-file prototype)

- `listen()` could silently miss a message: it re-resolved "now" on every offset-less poll instead of exactly once, so anything written between an empty poll's response and the next request could be dropped. Fixed to resolve the head once and always carry `next_offset` afterward.
- No client-side rate limiting existed at all, so a tight `listen()` loop could burn through its own polling budget.
- 429 backoff used a fixed exponential schedule and ignored the response's `Retry-After` header.
- No local validation of text/caption length or media size/MIME type before sending, costing an avoidable round trip on every violation.
- `to` accepted an `agent:<id>` recipient, which the API always rejects — now rejected locally with a clear message.
- No handling for the Base64 (inbound message) vs. hex (`GET /media/<id>`) encoding mismatch in the `sha256` field.
- No typing-indicator refresh; a reply slower than 25 seconds silently lost the indicator partway through.

[0.1.0]: https://github.com/abdullah3509/whatsapp-agent/releases/tag/v0.1.0
