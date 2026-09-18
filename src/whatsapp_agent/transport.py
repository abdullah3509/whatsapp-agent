"""HTTP transport: request dispatch, retries, rate limiting and error
mapping, split out from :class:`~whatsapp_agent.client.WhatsAppAgentClient`
so it is the single seam an async transport (using ``httpx``) can replace
without touching the client's public API. See the project roadmap in the
README for the planned ``AsyncWhatsAppAgentClient``.
"""
from __future__ import annotations

import time
from typing import Any, NoReturn

import requests

from .errors import build_error
from .ratelimit import RateLimiter


class Transport:
    """Wraps a :class:`requests.Session` with the retry policy and rate
    limiting described in the manual (pp.9, 25-28).

    Retry policy, matching "Retrying a send" (manual p.9):

    - ``2xx``: success, returned as-is.
    - ``429``: always safe to retry -- the request was rejected before being
      acted on. Backs off using ``Retry-After`` if the server sent one, else
      exponential backoff.
    - ``503`` with ``error.code == 131016`` ("not accepted for delivery"):
      the manual guarantees this means the message was *never sent*, so it is
      safe to auto-retry.
    - Any other ``4xx``: never retried automatically -- the request itself is
      wrong (bad token, bad payload, disallowed recipient) and retrying it
      unchanged fails the same way.
    - ``500`` / connection errors / read timeouts: **not** auto-retried. The
      manual is explicit that these leave it unknown whether the request was
      acted on (e.g. a message send), so blindly retrying can duplicate it.
      Left to the caller, who knows whether a duplicate is tolerable.
    """

    def __init__(
        self,
        session: requests.Session,
        base_url: str,
        *,
        http_timeout: float,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.http_timeout = http_timeout
        self.rate_limiter = rate_limiter

    def request(
        self,
        method: str,
        path: str,
        *,
        bucket: str | None = None,
        auto_retry_not_accepted: bool = False,
        max_retries: int = 5,
        backoff_base: float = 1.0,
        http_timeout: float | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Issue one logical request, retrying per the policy above.

        ``bucket`` names the rate-limit counter to consult before each
        attempt (see :mod:`whatsapp_agent.ratelimit`); pass ``None`` to skip
        client-side limiting for this call.
        """
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        attempt = 0
        while True:
            if self.rate_limiter is not None and bucket is not None:
                self.rate_limiter.acquire(bucket)
            resp = self.session.request(
                method, url, timeout=http_timeout or self.http_timeout, **kwargs
            )
            if resp.status_code == 204 or resp.ok:
                return resp

            retryable = resp.status_code == 429 or (
                auto_retry_not_accepted and resp.status_code == 503
            )
            if retryable and attempt < max_retries:
                if resp.status_code == 429 and self.rate_limiter is not None and bucket:
                    retry_after = _parse_retry_after(resp)
                    if retry_after is not None:
                        self.rate_limiter.note_retry_after(bucket, retry_after)
                delay = _retry_delay(resp, attempt, backoff_base)
                time.sleep(delay)
                attempt += 1
                continue
            _raise_for_error(resp)

    def close(self) -> None:
        self.session.close()


def _parse_retry_after(resp: requests.Response) -> float | None:
    header = resp.headers.get("Retry-After")
    if not header:
        return None
    try:
        return float(header)
    except ValueError:
        return None


def _retry_delay(resp: requests.Response, attempt: int, backoff_base: float) -> float:
    retry_after = _parse_retry_after(resp)
    if retry_after is not None:
        return retry_after
    return float(backoff_base * (2**attempt))


def _raise_for_error(resp: requests.Response) -> NoReturn:
    """Raise the appropriate :class:`~whatsapp_agent.errors.WhatsAppAPIError`
    subclass for a non-2xx/204 response. Always raises; never returns.
    """
    try:
        payload = resp.json()
        err = payload["error"]
    except (ValueError, KeyError):
        raise build_error(resp.status_code, -1, resp.text or "unknown error") from None
    error_data = err.get("error_data") or {}
    retry_after = _parse_retry_after(resp)
    raise build_error(
        http_status=resp.status_code,
        code=err.get("code", -1),
        message=err.get("message", ""),
        details=error_data.get("details"),
        fbtrace_id=err.get("fbtrace_id"),
        retry_after=retry_after,
    )
