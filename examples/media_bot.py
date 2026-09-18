#!/usr/bin/env python3
"""A bot that echoes back any image it receives, and answers a text message
by uploading and sending a local file. Demonstrates upload_media,
download_media, send_image, and verify_media_sha256.

Run:
    export WHATSAPP_API_KEY=...
    python examples/media_bot.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from whatsapp_agent import WhatsAppAgentClient
from whatsapp_agent.client import hash_media_bytes, verify_media_sha256


def main() -> None:
    client = WhatsAppAgentClient()
    print("Media bot running. Send an image or say 'send me the logo'. Ctrl+C to stop.")

    for message in client.listen(auto_mark_read=True):
        if message.image is not None:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "incoming"
                path = client.download_media(message.image.id, dest)
                data = path.read_bytes()

                # Sanity-check the download against the digest WhatsApp sent
                # with the message (Base64) using the raw bytes' own hash,
                # and separately against get_media_info()'s hex digest.
                local_hex = hash_media_bytes(data)
                info = client.get_media_info(message.image.id)
                assert local_hex == info.sha256, "downloaded bytes don't match reported sha256"
                if message.image.sha256:
                    assert verify_media_sha256(message.image.sha256, info.sha256)

                print(f"Downloaded {len(data)} bytes, sha256 verified.")
            client.reply_text(message, "Got your image, thanks!")
            continue

        if message.text and "logo" in message.text.lower():
            media_id = client.upload_media("examples/assets/logo.png")  # swap in your own image path
            client.send_image(message.from_, media_id, caption="Here's the logo")
            continue

        client.reply_text(message, "Send me an image, or say 'send me the logo'.")


if __name__ == "__main__":
    main()
