# whatsapp-agent

[![CI](https://github.com/abdullahshahid/whatsapp-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/abdullahshahid/whatsapp-agent/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/whatsapp-agent.svg)](https://pypi.org/project/whatsapp-agent/)
[![Python versions](https://img.shields.io/pypi/pyversions/whatsapp-agent.svg)](https://pypi.org/project/whatsapp-agent/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A Python SDK and MCP server for the [WhatsApp Agent Platform](https://api.whatsapp.com/agent/v1) — the API behind agents on personal WhatsApp. Send and receive messages, upload and download media, and drive it all from n8n, Claude, Cursor, or any other MCP-compatible tool.

- **A typed Python client** for every endpoint in the developer manual: sending, long-polling for updates, read receipts/typing, and media.
- **An MCP server** (`whatsapp-agent mcp`) so n8n's MCP Client Tool node — or Claude Desktop, Cursor, or any MCP host — can send/receive WhatsApp messages as tool calls, with no glue code.
- **A WhatsApp text-formatting module.** WhatsApp is *not* Markdown — `*bold*`, not `**bold**` — and this is the most common way agent output shows up broken in a chat. `whatsapp_agent.formatting` and `whatsapp_agent.markdown` handle it.
- **Client-side correctness the manual asks for**: per-endpoint rate limiting, retry semantics that never double-send, and a long-poll loop that can't silently drop a message.

## Two ways to use this

- **Full package** (`pip install whatsapp-agent`) — typed models, automatic per-endpoint rate limiting, WhatsApp text formatting, and an MCP server for n8n/Claude/Cursor. Reach for this for an agent, a workflow, or anything long-running (a `listen()` loop).
- **[`whatsapp_agent_simple.py`](whatsapp_agent_simple.py)** — a single, dependency-light file (`requests` + `python-dotenv`, nothing else) you copy directly into a project. For a monitoring script, a cron job, a web app's notification sender, or anything else that just needs to fire a plain HTTP request to send a WhatsApp message and isn't an AI agent at all. Same method names as the full client (`send_text`, `send_image`, `listen`, ...), no `pip install` required.

Both talk to the same API and cover the same endpoints; the standalone file just trades the package's extra machinery (rate limiting, typed models, MCP) for zero install footprint.

## Install

```bash
pip install whatsapp-agent          # SDK only
pip install "whatsapp-agent[mcp]"   # SDK + MCP server
```

Requires Python 3.9+. Or, for the simple single-file option, just copy [`whatsapp_agent_simple.py`](whatsapp_agent_simple.py) into your project — no install step.

## Get an API token

Open WhatsApp on your phone: **Settings → Agents → Create an agent**, set a name and avatar, open the agent's chat, then **Chat info → API key**. Store it somewhere safe — if you uninstall the app, you have to regenerate it.

```bash
cp .env.example .env   # then paste your key into WHATSAPP_API_KEY
```

## Quick start

```python
from whatsapp_agent import WhatsAppAgentClient

client = WhatsAppAgentClient()  # reads WHATSAPP_API_KEY from the environment

for message in client.listen(auto_mark_read=True):
    text = message.text or f"[{message.type}]"
    print(f"{message.from_}: {text}")
    client.reply_text(message, "Got it!")
```

An agent can only message the WhatsApp account that created it — there's no way to message an arbitrary number. `to` accepts the `from` value of an inbound message, or a bare phone number for the creator.

Sending a one-off notification instead of running a listen loop? Set `WHATSAPP_USER_ID` in `.env` and skip `to` entirely:

```python
client.notify("Backup finished successfully.")
```

Sending media:

```python
media_id = client.upload_media("invoice.pdf")
client.send_document(message.from_, media_id, filename="invoice.pdf", caption="Here you go")
```

Slow reply? Keep the typing indicator alive (it otherwise dies after 25s):

```python
with client.typing(message.id):
    reply = call_your_llm(message.text)
client.reply_text(message, reply)
```

See [`examples/echo_bot.py`](examples/echo_bot.py) and [`examples/media_bot.py`](examples/media_bot.py) for complete, runnable scripts.

## WhatsApp text formatting

WhatsApp has its own inline formatting syntax, and it is **not** Markdown:

| Style | WhatsApp | Markdown (for contrast) |
|---|---|---|
| Bold | `*text*` | `**text**` |
| Italic | `_text_` | `*text*` or `_text_` |
| Strikethrough | `~text~` | `~~text~~` |
| Monospace block | ` ```text``` ` | ` ```lang\ntext\n``` ` |
| Inline code | `` `text` `` | same |
| Blockquote | `> text` | same |
| Bulleted list | `- item` | same |
| Numbered list | `1. item` | same |

Headings, links, images, tables and horizontal rules have **no WhatsApp equivalent** at all. Send an LLM's raw Markdown output and `**bold**` shows up in the chat as two literal asterisks — this is the single most common way agent replies look broken.

```python
from whatsapp_agent.formatting import bold, italic
from whatsapp_agent.markdown import from_markdown

client.send_text(to, f"{bold('Order #1234')} shipped {italic('today')}.")

# Or convert an LLM's Markdown output wholesale:
llm_reply = "**Total:** $42.00\n\nSee the [invoice](https://example.com/inv.pdf)."
client.send_text(to, from_markdown(llm_reply))
# -> "*Total:* $42.00\n\nSee the invoice (https://example.com/inv.pdf)."
```

Full reference, including escaping (WhatsApp has no escape character) and truncation rules: [`docs/formatting.md`](docs/formatting.md).

## Use it from n8n (or Claude, or Cursor)

```bash
whatsapp-agent mcp --http --port 8765
```

Point n8n's **MCP Client Tool** node at `http://localhost:8765/mcp`, and the workflow gets `wa_send_text`, `wa_send_media`, `wa_upload_media`, `wa_download_media`, `wa_get_updates`, `wa_mark_read`, and `wa_format_text` as callable tools — no custom HTTP Request nodes, no hand-rolled auth.

Full setup (including Claude Desktop / Cursor config and an n8n workflow walkthrough): [`docs/mcp.md`](docs/mcp.md) and [`docs/n8n.md`](docs/n8n.md).

## Feature coverage

Everything in the developer manual is implemented:

| Manual section | SDK |
|---|---|
| §1 Send a message | `send_text`, `send_image`, `send_audio`, `send_video`, `send_document`, `send_sticker`, `reply_text` |
| §2 Receive messages | `get_updates`, `listen` |
| §3 Read receipts & typing | `mark_read`, `typing()` |
| §4 Media | `upload_media`, `upload_media_bytes`, `get_media_info`, `download_media`, `delete_media` |
| §5 Errors | typed exceptions per `error.code` — see [`docs/errors.md`](docs/errors.md) |
| §6 Rate limits | automatic, per-endpoint — see [`docs/rate-limits.md`](docs/rate-limits.md) |

## Documentation

- [`docs/quickstart.md`](docs/quickstart.md) — install, auth, first message
- [`docs/api-reference.md`](docs/api-reference.md) — every client method
- [`docs/formatting.md`](docs/formatting.md) — WhatsApp's text formatting, in full
- [`docs/mcp.md`](docs/mcp.md) — running the MCP server, client configs
- [`docs/n8n.md`](docs/n8n.md) — n8n workflow walkthrough
- [`docs/errors.md`](docs/errors.md) — exception types and what to do
- [`docs/rate-limits.md`](docs/rate-limits.md) — per-endpoint budgets and backoff
- [`docs/migration.md`](docs/migration.md) — coming from the original single-file `whatsapp_agent.py`

## Roadmap

Not in v0.1, tracked for later releases:

- `AsyncWhatsAppAgentClient` (httpx-based; the transport layer is already structured for this — see `transport.py`)
- `whatsapp-agent bridge --webhook <url>` — long-poll and forward inbound messages to an n8n/Make webhook, for a push-based inbound path instead of scheduled polling
- OpenAI/Anthropic tool-schema exporters for hand-rolled agent loops that don't use MCP

Contributions welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

MIT — see [`LICENSE`](LICENSE).
