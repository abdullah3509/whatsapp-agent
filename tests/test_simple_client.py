"""Tests for the standalone whatsapp_agent_simple.py -- specifically the two
correctness fixes it carries forward from the full package (offset
tracking in listen(), and rejecting an agent:<id> recipient locally).
Everything else in that file mirrors the original prototype and isn't
re-tested exhaustively here.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import responses

BASE_URL = "https://api.whatsapp.com/agent/v1"

_MODULE_PATH = Path(__file__).resolve().parent.parent / "whatsapp_agent_simple.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("whatsapp_agent_simple", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["whatsapp_agent_simple"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def simple():
    return _load_module()


@pytest.fixture
def simple_client(simple):
    return simple.WhatsAppAgentClient(api_key="test-token")


def _updates_response(next_offset: int, messages=None) -> dict:
    return {
        "object": "whatsapp_agent_platform",
        "entry": [
            {
                "id": "123456789",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "contacts": [],
                            "messages": messages or [],
                            "statuses": [],
                        },
                    }
                ],
            }
        ],
        "next_offset": next_offset,
    }


class TestRecipientValidation:
    def test_bare_id_is_normalized(self, simple_client):
        assert simple_client._normalize_recipient("15551234567") == "user:15551234567"

    def test_user_prefix_is_kept(self, simple_client):
        assert simple_client._normalize_recipient("user:15551234567") == "user:15551234567"

    def test_agent_prefix_is_rejected(self, simple_client):
        with pytest.raises(ValueError, match="agent:<id>"):
            simple_client._normalize_recipient("agent:987")


class TestListenOffsetTracking:
    @responses.activate
    def test_offset_is_carried_after_first_message(self, simple_client):
        responses.add(
            responses.GET,
            f"{BASE_URL}/updates",
            json=_updates_response(
                100, [{"id": "wamid.1", "from": "user:1", "timestamp": "1", "type": "text",
                       "text": {"body": "first"}}]
            ),
            status=200,
        )
        responses.add(responses.GET, f"{BASE_URL}/updates", status=204)
        responses.add(
            responses.GET,
            f"{BASE_URL}/updates",
            json=_updates_response(
                101, [{"id": "wamid.2", "from": "user:1", "timestamp": "2", "type": "text",
                       "text": {"body": "second"}}]
            ),
            status=200,
        )

        gen = simple_client.listen()
        first = next(gen)
        assert first["id"] == "wamid.1"
        second = next(gen)
        assert second["id"] == "wamid.2"

        assert "offset" not in responses.calls[0].request.url
        assert "offset=100" in responses.calls[1].request.url  # 204 after first message
        assert "offset=100" in responses.calls[2].request.url  # second poll, same offset
