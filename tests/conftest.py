from __future__ import annotations

import pytest

from whatsapp_agent import WhatsAppAgentClient

API_KEY = "test-token-123"
BASE_URL = "https://api.whatsapp.com/agent/v1"


@pytest.fixture
def client() -> WhatsAppAgentClient:
    """A client with client-side rate limiting off by default, so tests
    aren't slowed down by throttling unless they specifically opt in via
    ``rate_limited_client``.
    """
    return WhatsAppAgentClient(api_key=API_KEY, client_side_rate_limiting=False)


@pytest.fixture
def rate_limited_client() -> WhatsAppAgentClient:
    return WhatsAppAgentClient(api_key=API_KEY, client_side_rate_limiting=True)


def error_body(code: int, message: str, details: str | None = None) -> dict:
    body = {
        "error": {
            "message": f"(#{code}) {message}",
            "type": "OAuthException",
            "code": code,
            "fbtrace_id": "AW7bqWj4TEST",
        }
    }
    if details:
        body["error"]["error_data"] = {"messaging_product": "whatsapp", "details": details}
    return body
