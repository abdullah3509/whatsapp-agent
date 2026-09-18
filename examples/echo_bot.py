#!/usr/bin/env python3
"""A minimal echo bot: replies to every inbound message with its own text,
formatted back in bold. Demonstrates listen(), reply_text(), and the typing
indicator context manager.

Run:
    export WHATSAPP_API_KEY=...   # or put it in a .env file
    python examples/echo_bot.py
"""
from __future__ import annotations

from whatsapp_agent import WhatsAppAgentClient
from whatsapp_agent.formatting import bold


def main() -> None:
    client = WhatsAppAgentClient()
    print("Echo bot running. Message the agent from WhatsApp to try it. Ctrl+C to stop.")

    for message in client.listen(auto_mark_read=True):
        text = message.text or f"[{message.type} message]"
        print(f"{message.from_}: {text}")

        with client.typing(message.id):
            reply = f"You said: {bold(text)}"

        client.reply_text(message, reply)


if __name__ == "__main__":
    main()
