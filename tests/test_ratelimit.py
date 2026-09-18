"""Tests for whatsapp_agent.ratelimit.RateLimiter and its wiring into
Transport -- the client-side throttle that keeps calls within the manual's
documented per-endpoint rolling-60s budgets (p.28).

Uses a fake, manually-advanced clock (rather than real threading/sleeping)
so the 60-second rolling window can be tested deterministically and fast.
"""
from __future__ import annotations

import responses

from tests.conftest import BASE_URL, error_body
from whatsapp_agent.ratelimit import RateLimiter


class FakeClock:
    """A monotonic clock under test control. Pass ``.now`` as the monotonic
    function and ``.sleep`` as the sleep function so every simulated sleep
    advances the same clock ``acquire()`` reads.
    """

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


class TestRateLimiterUnit:
    def test_allows_calls_up_to_the_limit_without_sleeping(self, monkeypatch):
        clock = FakeClock()
        monkeypatch.setattr("whatsapp_agent.ratelimit.time.monotonic", clock.now)
        limiter = RateLimiter({"messages": 12}, sleep=clock.sleep)
        for _ in range(12):
            limiter.acquire("messages")
        assert clock.sleeps == []

    def test_13th_call_waits_out_the_rolling_window(self, monkeypatch):
        clock = FakeClock()
        monkeypatch.setattr("whatsapp_agent.ratelimit.time.monotonic", clock.now)
        limiter = RateLimiter({"messages": 12}, sleep=clock.sleep)
        for _ in range(12):
            limiter.acquire("messages")
        assert clock.sleeps == []

        limiter.acquire("messages")  # the 13th call must wait for room
        assert clock.sleeps == [60.0]

    def test_calls_outside_the_window_dont_count(self, monkeypatch):
        clock = FakeClock()
        monkeypatch.setattr("whatsapp_agent.ratelimit.time.monotonic", clock.now)
        limiter = RateLimiter({"messages": 12}, sleep=clock.sleep)
        for _ in range(12):
            limiter.acquire("messages")
        clock.t += 61  # let the whole window elapse
        limiter.acquire("messages")  # room again -- must not sleep
        assert clock.sleeps == []

    def test_unknown_bucket_is_a_no_op(self):
        limiter = RateLimiter({"messages": 12})
        limiter.acquire("nonexistent-bucket")  # must not raise or block

    def test_note_retry_after_forces_a_wait_even_with_budget_left(self, monkeypatch):
        clock = FakeClock()
        monkeypatch.setattr("whatsapp_agent.ratelimit.time.monotonic", clock.now)
        limiter = RateLimiter({"messages": 12}, sleep=clock.sleep)
        limiter.note_retry_after("messages", 30)
        limiter.acquire("messages")  # only 0/12 used, but retry_after must still apply
        assert clock.sleeps == [30.0]

    def test_note_retry_after_on_unknown_bucket_is_a_no_op(self):
        limiter = RateLimiter({"messages": 12})
        limiter.note_retry_after("nonexistent-bucket", 30)  # must not raise


class TestClientRateLimiting:
    @responses.activate
    def test_disabled_by_default_in_test_client_does_not_block(self, client):
        # The `client` fixture disables client-side rate limiting so tests
        # run fast; confirm 13 rapid sends never sleep/block.
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json={"messaging_product": "whatsapp", "contacts": [], "messages": [{"id": "x"}]},
            status=200,
        )
        for _ in range(13):
            client.send_text("15551234567", "hi")
        assert len(responses.calls) == 13

    @responses.activate
    def test_429_retry_after_is_honored(self, client, monkeypatch):
        sleeps = []
        monkeypatch.setattr(
            "whatsapp_agent.transport.time.sleep", lambda seconds: sleeps.append(seconds)
        )
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json=error_body(130429, "Too many requests"),
            status=429,
            headers={"Retry-After": "7"},
        )
        responses.add(
            responses.POST,
            f"{BASE_URL}/messages",
            json={"messaging_product": "whatsapp", "contacts": [], "messages": [{"id": "x"}]},
            status=200,
        )
        result = client.send_text("15551234567", "hi")
        assert result["messages"][0]["id"] == "x"
        assert 7.0 in sleeps
