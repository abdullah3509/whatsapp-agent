from __future__ import annotations

import json

import pytest
import responses

from tests.conftest import BASE_URL, error_body
from whatsapp_agent import (
    AuthenticationError,
    InvalidRequestError,
    MediaError,
    NotAcceptedError,
    RecipientNotAllowedError,
)
from whatsapp_agent.client import hash_media_bytes, verify_media_sha256


class TestSendText:
    @responses.activate
    def test_send_text_success(self, client):
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json={
                "messaging_product": "whatsapp",
                "contacts": [{"input": "user:15551234567", "wa_id": "user:15551234567"}],
                "messages": [{"id": "wamid.ABC"}],
            },
            status=200,
        )
        result = client.send_text("15551234567", "Hello!")
        assert result["messages"][0]["id"] == "wamid.ABC"

        sent_body = json.loads(responses.calls[0].request.body)
        assert sent_body["to"] == "user:15551234567"
        assert sent_body["type"] == "text"
        assert sent_body["text"] == {"body": "Hello!"}

    def test_send_text_rejects_agent_prefix(self, client):
        with pytest.raises(ValueError, match="agent:<id>"):
            client.send_text("agent:987", "Hello!")

    def test_send_text_rejects_oversized_body(self, client):
        with pytest.raises(ValueError, match="4096"):
            client.send_text("15551234567", "x" * 4097)

    def test_send_text_rejects_empty_body(self, client):
        with pytest.raises(ValueError):
            client.send_text("15551234567", "")

    def test_preview_url_requires_a_url(self, client):
        with pytest.raises(ValueError, match="preview_url"):
            client.send_text("15551234567", "no links here", preview_url=True)

    @responses.activate
    def test_context_message_id_is_threaded(self, client):
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json={"messaging_product": "whatsapp", "contacts": [], "messages": [{"id": "x"}]},
            status=200,
        )
        client.send_text("15551234567", "hi", context_message_id="wamid.PARENT")
        sent_body = json.loads(responses.calls[0].request.body)
        assert sent_body["context"] == {"message_id": "wamid.PARENT"}


class TestSendMediaHelpers:
    @responses.activate
    def test_send_image_with_caption(self, client):
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json={"messaging_product": "whatsapp", "contacts": [], "messages": [{"id": "x"}]},
            status=200,
        )
        client.send_image("15551234567", "media-id-1", caption="look at this")
        sent_body = json.loads(responses.calls[0].request.body)
        assert sent_body["image"] == {"id": "media-id-1", "caption": "look at this"}

    def test_caption_over_limit_raises(self, client):
        with pytest.raises(ValueError, match="1024"):
            client.send_image("15551234567", "media-id-1", caption="x" * 1025)

    @responses.activate
    def test_send_audio_has_no_caption_field(self, client):
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json={"messaging_product": "whatsapp", "contacts": [], "messages": [{"id": "x"}]},
            status=200,
        )
        client.send_audio("15551234567", "media-id-1")
        sent_body = json.loads(responses.calls[0].request.body)
        assert sent_body["audio"] == {"id": "media-id-1"}


class TestErrorMapping:
    @responses.activate
    def test_401_maps_to_authentication_error(self, client):
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json=error_body(190, "The Authorization header is absent or malformed"),
            status=401,
        )
        with pytest.raises(AuthenticationError):
            client.send_text("15551234567", "hi")

    @responses.activate
    def test_recipient_not_allowed(self, client):
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json=error_body(131005, "The recipient is not the agent's creator"),
            status=403,
        )
        with pytest.raises(RecipientNotAllowedError):
            client.send_text("15559999999", "hi")

    @responses.activate
    def test_invalid_request(self, client):
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json=error_body(131009, "Missing or malformed required fields"),
            status=400,
        )
        with pytest.raises(InvalidRequestError):
            client.send_text("15551234567", "hi")

    @responses.activate
    def test_media_error(self, client):
        # error.code 100 is ambiguous in the manual (it also means "token
        # not valid" elsewhere), so it maps to InvalidRequestError, not
        # MediaError -- see errors.py's MediaError docstring. 131053
        # (media rejected -- size/MIME) is the unambiguous MediaError code.
        responses.add(
            responses.POST,
            f"{BASE_URL}/media",
            json=error_body(131053, "Media rejected"),
            status=400,
        )
        with pytest.raises(MediaError):
            client.upload_media_bytes(b"x" * 100, "big.bin", mime_type="application/pdf")

    @responses.activate
    def test_503_not_accepted_is_retried_then_raises(self, client, monkeypatch):
        # Don't actually sleep through the exponential backoff in a unit test.
        monkeypatch.setattr("whatsapp_agent.transport.time.sleep", lambda seconds: None)
        # Every attempt returns 503 -- exhausts retries and raises NotAcceptedError.
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json=error_body(131016, "Message not accepted for delivery"),
            status=503,
        )
        with pytest.raises(NotAcceptedError):
            client.send_text("15551234567", "hi")
        # 1 initial attempt + retries -- confirm it did retry, not just fail once.
        assert len(responses.calls) >= 2


class TestMediaSha256:
    def test_verify_media_sha256_matches(self):
        import base64
        import hashlib

        data = b"hello world"
        digest = hashlib.sha256(data).digest()
        b64 = base64.b64encode(digest).decode()
        hexd = digest.hex()
        assert verify_media_sha256(b64, hexd) is True

    def test_verify_media_sha256_mismatch(self):
        import base64
        import hashlib

        digest1 = hashlib.sha256(b"hello").digest()
        digest2 = hashlib.sha256(b"world").digest()
        assert verify_media_sha256(base64.b64encode(digest1).decode(), digest2.hex()) is False

    def test_hash_media_bytes(self):
        import hashlib

        data = b"some bytes"
        assert hash_media_bytes(data) == hashlib.sha256(data).hexdigest()


class TestReplyText:
    @responses.activate
    def test_reply_text_from_message_model(self, client):
        from whatsapp_agent.models import Message

        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json={"messaging_product": "whatsapp", "contacts": [], "messages": [{"id": "x"}]},
            status=200,
        )
        msg = Message.from_dict(
            {"id": "wamid.IN", "from": "user:15551234567", "timestamp": "1", "type": "text",
             "text": {"body": "hi"}}
        )
        client.reply_text(msg, "hello back")
        sent_body = json.loads(responses.calls[0].request.body)
        assert sent_body["to"] == "user:15551234567"
        assert sent_body["context"] == {"message_id": "wamid.IN"}

    @responses.activate
    def test_reply_text_from_raw_dict(self, client):
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json={"messaging_product": "whatsapp", "contacts": [], "messages": [{"id": "x"}]},
            status=200,
        )
        raw = {"id": "wamid.IN", "from": "user:15551234567"}
        client.reply_text(raw, "hello back")
        sent_body = json.loads(responses.calls[0].request.body)
        assert sent_body["context"] == {"message_id": "wamid.IN"}


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("WHATSAPP_API_KEY", raising=False)
    from whatsapp_agent import WhatsAppAgentClient

    with pytest.raises(ValueError, match="WHATSAPP_API_KEY"):
        WhatsAppAgentClient()
