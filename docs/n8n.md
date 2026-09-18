# Using whatsapp-agent from n8n

n8n's **MCP Client Tool** node (n8n ≥ 1.6x with the LangChain/AI nodes enabled) can call any MCP server's tools directly from an AI Agent node, or you can call them from a plain workflow with the standalone **MCP Client** node.

## 1. Start the server

Run it somewhere n8n can reach over HTTP — alongside n8n in Docker Compose, on the same host, or on a small VM:

```bash
pip install "whatsapp-agent[mcp]"
export WHATSAPP_API_KEY=your-token-here
whatsapp-agent mcp --http --host 0.0.0.0 --port 8765
```

This serves at `http://<host>:8765/mcp`.

## 2. Point n8n at it

In n8n, add an **MCP Client Tool** node (inside an AI Agent) or an **MCP Client** node (standalone):

- **SSE/HTTP Streamable URL**: `http://<host>:8765/mcp`
- **Authentication**: none needed at the MCP layer — the WhatsApp API token lives in the server's environment, not in n8n. Put the MCP endpoint itself behind a reverse proxy or VPN if it's reachable outside your own network.

n8n will discover all seven tools (`wa_send_text`, `wa_send_media`, `wa_upload_media`, `wa_download_media`, `wa_get_updates`, `wa_mark_read`, `wa_format_text`) automatically from the server's tool list.

## 3. A worked example: auto-reply workflow

A minimal "poll for messages, reply with an LLM, send the reply" workflow:

1. **Schedule Trigger** — every 15–30 seconds. (Keep this comfortably above `wa_get_updates`'s own long-poll `timeout`, which tops out at 25 seconds, so runs don't overlap.)
2. **NoOp / Set node** — read `next_offset` from wherever you're persisting it (a Postgres/Redis node, or n8n's static data on the workflow, for a simple setup).
3. **MCP Client** node → `wa_get_updates` with `offset` = the value from step 2, `timeout` = 20.
4. **IF** node — branch on `messages` being non-empty.
5. **AI Agent** node (or a plain LLM node) — generate a reply from `messages[0].text.body`.
6. **MCP Client** node → `wa_format_text` on the LLM's output (`source: "markdown"`) — LLMs default to Markdown, and WhatsApp isn't Markdown; skipping this step is the most common way the reply comes out with stray asterisks in the chat.
7. **MCP Client** node → `wa_send_text` with `to` = `messages[0].from`, `body` = the formatted text from step 6, `reply_to` = `messages[0].id`.
8. **Set/Postgres node** — persist the workflow's `next_offset` from step 3's response for the next run.

An [example workflow JSON](../examples/n8n-workflow.json) implementing this is included — import it via n8n's **Import from File**, then update the MCP node's URL and swap in your own storage node for the offset.

## Why polling instead of a webhook trigger

MCP has no push/webhook primitive for tool servers — there's no way for `whatsapp-agent mcp` to call *into* n8n when a message arrives, only for n8n to call *into* it. A Schedule Trigger polling `wa_get_updates` is the correct shape for this given that constraint. If you want push-based delivery instead (an n8n Webhook node fired the moment a message arrives), track the `bridge` command on the project roadmap, or long-poll with the plain Python SDK (`client.listen()`) in a small always-on service that POSTs to an n8n Webhook node yourself.

## Sending media from a workflow

```
MCP Client → wa_upload_media (file_path or base64_data) → media_id
MCP Client → wa_send_media (media_type, media_id, to, caption)
```

For a file already living in n8n as binary data, base64-encode it (n8n's "Move Binary Data" node, or a Function node) before passing it as `base64_data`.
