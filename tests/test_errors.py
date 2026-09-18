"""Tests for the error.code -> exception class mapping (manual p.28 and the
per-endpoint 4xx tables, pp.25-27).
"""
from __future__ import annotations

import pytest

from whatsapp_agent.errors import (
    AuthenticationError,
    InvalidRequestError,
    MediaError,
    NotAcceptedError,
    PollConflictError,
    RateLimitError,
    RecipientNotAllowedError,
    ServerError,
    WhatsAppAPIError,
    build_error,
)


@pytest.mark.parametrize(
    "code,http_status,expected_cls",
    [
        (2, 500, ServerError),
        (100, 400, InvalidRequestError),
        (100, 404, InvalidRequestError),
        (190, 401, AuthenticationError),
        (130429, 429, RateLimitError),
        (131005, 403, RecipientNotAllowedError),
        (131009, 400, InvalidRequestError),
        (131016, 503, NotAcceptedError),
        (131053, 400, MediaError),
        (1752041, 409, PollConflictError),
    ],
)
def test_known_codes_map_to_expected_class(code, http_status, expected_cls):
    exc = build_error(http_status, code, "some message")
    assert isinstance(exc, expected_cls)
    assert isinstance(exc, WhatsAppAPIError)
    assert exc.code == code
    assert exc.http_status == http_status


def test_unknown_code_falls_back_to_base_class():
    exc = build_error(418, 999999, "unrecognized")
    assert type(exc) is WhatsAppAPIError


@pytest.mark.parametrize(
    "http_status,expected_cls",
    [(401, AuthenticationError), (429, RateLimitError), (500, ServerError), (400, InvalidRequestError)],
)
def test_missing_code_falls_back_on_http_status(http_status, expected_cls):
    # code=-1 is what the transport passes when the response body has no
    # parseable error envelope at all.
    exc = build_error(http_status, -1, "unknown error")
    assert isinstance(exc, expected_cls)


def test_rate_limit_error_carries_retry_after():
    exc = build_error(429, 130429, "Too many requests", retry_after=12.5)
    assert isinstance(exc, RateLimitError)
    assert exc.retry_after == 12.5


def test_non_rate_limit_error_ignores_retry_after_kwarg():
    # retry_after is only meaningful on RateLimitError; passing it for
    # another code must not raise or attach a bogus attribute silently.
    exc = build_error(400, 131009, "bad request", retry_after=12.5)
    assert not hasattr(exc, "retry_after")


def test_details_and_fbtrace_id_are_preserved():
    exc = build_error(
        400, 131009, "Missing or malformed required fields",
        details="text is required when type=text", fbtrace_id="AW7bqWj4...",
    )
    assert exc.details == "text is required when type=text"
    assert exc.fbtrace_id == "AW7bqWj4..."


def test_error_str_includes_code_and_message():
    exc = WhatsAppAPIError(400, 131009, "Missing or malformed required fields")
    text = str(exc)
    assert "400" in text
    assert "131009" in text
    assert "Missing or malformed required fields" in text
