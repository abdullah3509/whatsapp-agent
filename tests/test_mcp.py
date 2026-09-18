"""Tests for whatsapp_agent.mcp.tools -- the pure functions behind the MCP
server, tested directly against a mocked HTTP layer (via `responses`)
without spinning up an actual MCP protocol server.

Skipped entirely if the optional `mcp` extra isn't installed, since these
tools import from whatsapp_agent.mcp which requires it.
"""
from __future__ import annotations

import base64
import json

import pytest
import responses

pytest.importorskip("mcp")

from tests.conftest import BASE_URL  # noqa: E402
from whatsapp_agent.mcp import tools  # noqa: E402


class TestSendText:
    @responses.activate
    def test_send_text_plain(self, client):
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json={"messaging_product": "whatsapp", "contacts": [], "messages": [{"id": "x"}]},
            status=200,
        )
        result = tools.send_text(client, "15551234567", "hello")
        assert result["messages"][0]["id"] == "x"

    @responses.activate
    def test_send_text_from_markdown_source_converts_first(self, client):
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json={"messaging_product": "whatsapp", "contacts": [], "messages": [{"id": "x"}]},
            status=200,
        )
        tools.send_text(client, "15551234567", "**bold**", from_markdown_source=True)
        sent_body = json.loads(responses.calls[0].request.body)
        assert sent_body["text"]["body"] == "*bold*"


class TestSendMedia:
    @responses.activate
    def test_dispatches_to_correct_sender(self, client):
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json={"messaging_product": "whatsapp", "contacts": [], "messages": [{"id": "x"}]},
            status=200,
        )
        tools.send_media(client, "15551234567", "image", "media-1", caption="hi")
        sent_body = json.loads(responses.calls[0].request.body)
        assert sent_body["type"] == "image"
        assert sent_body["image"] == {"id": "media-1", "caption": "hi"}

    def test_unknown_media_type_raises(self, client):
        with pytest.raises(ValueError, match="media_type"):
            tools.send_media(client, "15551234567", "carrier_pigeon", "media-1")


class TestUploadMedia:
    def test_requires_exactly_one_source(self, client):
        with pytest.raises(ValueError, match="exactly one"):
            tools.upload_media(client)
        with pytest.raises(ValueError, match="exactly one"):
            tools.upload_media(client, file_path="a.pdf", base64_data="Zm9v")

    def test_base64_without_filename_raises(self, client):
        with pytest.raises(ValueError, match="filename"):
            tools.upload_media(client, base64_data=base64.b64encode(b"data").decode())

    @responses.activate
    def test_base64_upload(self, client):
        responses.add(
            responses.POST,
            f"{BASE_URL}/media",
            json={"id": "media-123"},
            status=200,
        )
        result = tools.upload_media(
            client, base64_data=base64.b64encode(b"%PDF-1.4 fake").decode(), filename="doc.pdf"
        )
        assert result == {"id": "media-123"}


class TestGetUpdates:
    @responses.activate
    def test_204_returns_empty_with_same_offset(self, client):
        responses.add(responses.GET, f"{BASE_URL}/updates", status=204)
        result = tools.get_updates(client, offset=42)
        assert result == {"messages": [], "statuses": [], "contacts": [], "next_offset": 42}

    @responses.activate
    def test_returns_raw_dicts_for_json_serializability(self, client):
        payload = {
            "object": "whatsapp_agent_platform",
            "entry": [
                {
                    "id": "1",
                    "changes": [
                        {
                            "field": "messages",
                            "value": {
                                "messaging_product": "whatsapp",
                                "contacts": [],
                                "messages": [
                                    {"id": "wamid.1", "from": "user:1", "timestamp": "1",
                                     "type": "text", "text": {"body": "hi"}}
                                ],
                                "statuses": [],
                            },
                        }
                    ],
                }
            ],
            "next_offset": 5,
        }
        responses.add(responses.GET, f"{BASE_URL}/updates", json=payload, status=200)
        result = tools.get_updates(client)
        assert result["next_offset"] == 5
        assert result["messages"][0]["id"] == "wamid.1"
        json.dumps(result)  # must be plain-JSON-serializable for an MCP tool response


class TestMarkRead:
    @responses.activate
    def test_mark_read(self, client):
        responses.add(
            responses.POST, f"{BASE_URL}/statuses", json={"success": True}, status=200
        )
        assert tools.mark_read(client, "wamid.1") == {"success": True}


class TestFormatText:
    def test_markdown_source_default(self):
        result = tools.format_text("**bold**")
        assert result == {"formatted": "*bold*"}

    def test_plain_source_leaves_text_unchanged(self):
        result = tools.format_text("**bold**", source="plain")
        assert result == {"formatted": "**bold**"}

    def test_bold_words_applied_after_conversion(self):
        result = tools.format_text("Order status", source="plain", bold_words=["Order"])
        assert result == {"formatted": "*Order* status"}

    def test_unknown_source_raises(self):
        with pytest.raises(ValueError):
            tools.format_text("x", source="bogus")


class TestToolErrorPayload:
    def test_shapes_a_whatsapp_api_error(self):
        from whatsapp_agent.errors import InvalidRequestError

        exc = InvalidRequestError(400, 131009, "bad request", details="text is required")
        payload = tools.tool_error_payload(exc)
        assert payload["error"] is True
        assert payload["code"] == 131009
        assert payload["type"] == "InvalidRequestError"
        json.dumps(payload)  # must be JSON-serializable
