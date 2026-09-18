# Quickstart

## 1. Install

```bash
pip install whatsapp-agent
```

Add `[mcp]` if you want the MCP server too: `pip install "whatsapp-agent[mcp]"`.

## 2. Get an API token

On the phone WhatsApp is installed on:

1. **Settings → Agents → Create an agent** — set a display name and avatar.
2. Open the agent's chat, then **Chat info → API key**.
3. Copy the key. This is your API token.
4. Store it securely — if you uninstall the app, you must regenerate it.

Put it in a `.env` file next to your script:

```bash
WHATSAPP_API_KEY=your-token-here
```

`WhatsAppAgentClient()` reads this automatically (via `python-dotenv`) unless you pass `api_key=` explicitly.

## 3. Receive a message

```python
from whatsapp_agent import WhatsAppAgentClient

client = WhatsAppAgentClient()

for message in client.listen():
    print(message.from_, "says:", message.text)
    break  # just the first one, for this example
```

`listen()` long-polls `GET /updates` in a loop and yields each inbound `Message`. It's safe to leave running indefinitely — it handles offset tracking, empty polls, and transient errors for you.

## 4. Send a reply

```python
client.send_text(message.from_, "Got it, thanks!")
```

Or, to thread the reply as a quote of the original message:

```python
client.reply_text(message, "Got it, thanks!")
```

An agent can only message the WhatsApp account that created it — `to` must be that account's identifier, most reliably obtained from an inbound message's `from` field rather than typed in by hand.

## 5. Send media

```python
media_id = client.upload_media("photo.jpg")
client.send_image(message.from_, media_id, caption="Here's the photo")
```

## 6. Verify your setup

```bash
whatsapp-agent doctor
```

Confirms `WHATSAPP_API_KEY` is set and accepted by the API.

## Next steps

- [Formatting your replies correctly](formatting.md) — WhatsApp isn't Markdown
- [Running the MCP server](mcp.md) for n8n/Claude/Cursor
- [Full API reference](api-reference.md)
