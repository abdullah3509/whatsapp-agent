"""Tests for the offset-tracking fix in WhatsAppAgentClient.listen() --
the most important correctness fix in this project relative to the
original single-file prototype. See docs/migration.md and the module
docstring on listen() for the full rationale.
"""
from __future__ import annotations

import responses

from tests.conftest import BASE_URL


def _updates_response(next_offset: int, messages: list[dict] | None = None) -> dict:
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


class TestListenOffsetTracking:
    @responses.activate
    def test_204_then_204_keeps_polling_offset_less_before_first_message(self, client):
        """Before anything has arrived, re-polling offset-less on a 204 is
        correct (there's nothing to have missed yet) -- this is the
        documented 'omit offset to start from now' behavior (manual p.15).
        """
        responses.add(responses.GET, f"{BASE_URL}/updates", status=204)
        responses.add(responses.GET, f"{BASE_URL}/updates", status=204)
        responses.add(
            responses.GET,
            f"{BASE_URL}/updates",
            json=_updates_response(
                100, [{"id": "wamid.1", "from": "user:1", "timestamp": "1", "type": "text",
                       "text": {"body": "hi"}}]
            ),
            status=200,
        )

        gen = client.listen(start="new")
        message = next(gen)
        assert message.id == "wamid.1"

        # All three requests before the message arrived must have been
        # offset-less (re-resolving "now" is fine and correct here, since
        # nothing had arrived yet for there to be a gap in).
        for call in responses.calls[:3]:
            assert "offset" not in call.request.url

    @responses.activate
    def test_after_first_message_offset_is_always_carried(self, client):
        """Once next_offset is known, every subsequent poll -- including
        ones that come back empty (204) -- must carry it. Re-omitting
        offset here would silently re-resolve 'now' and could skip a
        message that arrived in the gap. This is the bug this project
        fixes relative to the original prototype.
        """
        responses.add(
            responses.GET,
            f"{BASE_URL}/updates",
            json=_updates_response(
                100, [{"id": "wamid.1", "from": "user:1", "timestamp": "1", "type": "text",
                       "text": {"body": "first"}}]
            ),
            status=200,
        )
        # An empty poll after the first message -- offset must be present
        # and equal to the prior next_offset.
        responses.add(responses.GET, f"{BASE_URL}/updates", status=204)
        # A second message -- offset must still be the same value (the
        # server hasn't told us to advance past it, since 204s carry none).
        responses.add(
            responses.GET,
            f"{BASE_URL}/updates",
            json=_updates_response(
                101, [{"id": "wamid.2", "from": "user:1", "timestamp": "2", "type": "text",
                       "text": {"body": "second"}}]
            ),
            status=200,
        )

        gen = client.listen(start="new")
        first = next(gen)
        assert first.id == "wamid.1"
        second = next(gen)
        assert second.id == "wamid.2"

        assert "offset" not in responses.calls[0].request.url  # the initial "new" poll
        assert "offset=100" in responses.calls[1].request.url  # 204 after first message
        assert "offset=100" in responses.calls[2].request.url  # second poll, same offset
        # (next_offset only advances to 101 *after* this poll's response.)

    @responses.activate
    def test_start_all_begins_at_offset_zero(self, client):
        # Include a message so next(gen) returns after exactly one HTTP
        # call, rather than the generator immediately polling again for a
        # second HTTP call we haven't mocked.
        responses.add(
            responses.GET,
            f"{BASE_URL}/updates",
            json=_updates_response(
                1, [{"id": "wamid.1", "from": "user:1", "timestamp": "1", "type": "text",
                     "text": {"body": "hi"}}]
            ),
            status=200,
        )
        gen = client.listen(start="all", timeout=1)
        next(gen)
        assert "offset=0" in responses.calls[0].request.url

    @responses.activate
    def test_explicit_offset_overrides_start(self, client):
        responses.add(
            responses.GET,
            f"{BASE_URL}/updates",
            json=_updates_response(
                51, [{"id": "wamid.1", "from": "user:1", "timestamp": "1", "type": "text",
                      "text": {"body": "hi"}}]
            ),
            status=200,
        )
        gen = client.listen(start="new", offset=50, timeout=1)
        next(gen)
        assert "offset=50" in responses.calls[0].request.url


class TestGetUpdates:
    @responses.activate
    def test_204_returns_none(self, client):
        responses.add(responses.GET, f"{BASE_URL}/updates", status=204)
        assert client.get_updates() is None

    @responses.activate
    def test_parses_messages_and_statuses(self, client):
        payload = _updates_response(
            200,
            [
                {
                    "id": "wamid.1",
                    "from": "user:1",
                    "timestamp": "1700000000",
                    "type": "text",
                    "text": {"body": "hello"},
                }
            ],
        )
        payload["entry"][0]["changes"][0]["value"]["statuses"] = [
            {"id": "wamid.OUT", "status": "read", "recipient_id": "user:1", "timestamp": "1700000001"}
        ]
        responses.add(responses.GET, f"{BASE_URL}/updates", json=payload, status=200)

        updates = client.get_updates()
        assert updates is not None
        assert updates.messages[0].text == "hello"
        assert updates.statuses[0].status == "read"
        assert updates.next_offset == 200
