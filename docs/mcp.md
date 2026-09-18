# MCP server

`whatsapp-agent` bundles an [MCP](https://modelcontextprotocol.io) server so any MCP-compatible host — n8n's MCP Client Tool node, Claude Desktop, Cursor, or your own agent loop — gets WhatsApp send/receive as callable tools without writing glue code.

Requires the `mcp` extra:

```bash
pip install "whatsapp-agent[mcp]"
```

## Running it

**Stdio** (for Claude Desktop, Cursor, and most desktop MCP hosts):

```bash
whatsapp-agent mcp
```

**Streamable HTTP** (for n8n and anything that talks to a URL):

```bash
whatsapp-agent mcp --http --host 0.0.0.0 --port 8765
# serves at http://<host>:<port>/mcp
```

`WHATSAPP_API_KEY` must be set in the environment (or `.env`) wherever the server process runs.

## Tools

| Tool | Purpose |
|---|---|
| `wa_send_text` | Send a text message. `reply_to` threads a quote; `from_markdown_source=True` converts Markdown input first. |
| `wa_send_media` | Send previously uploaded image/audio/video/document/sticker. |
| `wa_upload_media` | Upload a local file or base64 payload, get back a media id. |
| `wa_download_media` | Download a media object's bytes to a local file. |
| `wa_get_updates` | One poll for inbound messages/statuses. This is the *only* way to receive messages through MCP — see below. |
| `wa_mark_read` | Mark a message read, optionally with a typing indicator. |
| `wa_format_text` | Convert Markdown (or plain text with selected bold words) to WhatsApp's formatting syntax. |

Every tool's docstring (visible to the calling model as its description) states the constraints that matter — recipient format, character caps, which media types support a caption — so the model calling it doesn't have to guess or read this page.

Errors come back as a structured payload (`{"error": true, "code": ..., "message": ..., "fbtrace_id": ...}`), not a bare stack trace, so a failing tool call in a workflow is something a human can act on.

## Receiving messages: polling, not push

MCP doesn't have a push/webhook primitive here, so there's no way for this server to *notify* a workflow when a message arrives — the workflow has to call `wa_get_updates` itself, on a schedule (an n8n Cron/Interval trigger feeding into the MCP Client Tool node, for example).

**Persist `next_offset` between calls.** `wa_get_updates` returns it in its response; pass it back as `offset` on the next call. If you omit `offset` every time, each call only sees what arrived since *that particular call* started — anything that arrived between two scheduled runs is silently missed. This is the same offset-tracking `WhatsAppAgentClient.listen()` does automatically for a plain Python script; a scheduled MCP tool call has to do it explicitly because there's no long-running loop to hold the state.

A push-based bridge (`whatsapp-agent bridge --webhook <url>`, long-polling and forwarding to an n8n Webhook node) is on the roadmap for a later release — see the README.

## Claude Desktop / Cursor config

Add to your MCP client's config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "whatsapp-agent": {
      "command": "whatsapp-agent",
      "args": ["mcp"],
      "env": {
        "WHATSAPP_API_KEY": "your-token-here"
      }
    }
  }
}
```

## n8n

See [n8n.md](n8n.md) for a full workflow walkthrough.

## Verifying the server

Without any MCP host, use the reference inspector:

```bash
npx @modelcontextprotocol/inspector whatsapp-agent mcp
```

This lists every tool with its schema and lets you invoke one manually — `wa_format_text` works with no API token at all, useful as a first smoke test.
