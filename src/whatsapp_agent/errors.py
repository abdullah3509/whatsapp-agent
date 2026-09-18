"""Exceptions for the WhatsApp Agent Platform API.

The API returns every error in one envelope (manual p.24)::

    {
      "error": {
        "message": "(#131009) Missing or malformed required fields",
        "type": "OAuthException",
        "code": 131009,
        "error_data": {"messaging_product": "whatsapp", "details": "..."},
        "fbtrace_id": "AW7bqWj4..."
      }
    }

``type`` is always ``"OAuthException"`` -- including for errors that have
nothing to do with authentication -- so it is not useful for branching and is
not exposed as its own attribute. Branch on ``error.code`` (or, in this SDK,
on the exception's class) instead. The mapping from ``error.code`` to a class
below follows the manual's error reference table (p.28) and the per-endpoint
tables (pp.25-27).
"""
from __future__ import annotations


class WhatsAppAPIError(Exception):
    """Base class for every API error. Raised as-is for a code with no
    dedicated subclass (chiefly ``error.code == 2``, an opaque server error).
    """

    def __init__(
        self,
        http_status: int,
        code: int,
        message: str,
        details: str | None = None,
        fbtrace_id: str | None = None,
    ):
        text = f"[HTTP {http_status}] error.code={code}: {message}"
        if details:
            text += f" -- {details}"
        super().__init__(text)
        self.http_status = http_status
        self.code = code
        self.message = message
        self.details = details
        self.fbtrace_id = fbtrace_id


class AuthenticationError(WhatsAppAPIError):
    """The Authorization header is absent/malformed (401, code 190), or the
    token is present but not valid (400, code 100). Regenerate the token --
    manual p.4: uninstalling the app invalidates it and it must be reissued.
    """


class RateLimitError(WhatsAppAPIError):
    """More requests than the endpoint's rolling-60s budget allow (429, code
    130429). See :mod:`whatsapp_agent.constants` (``RATE_LIMITS``) for the
    per-endpoint limits and :mod:`whatsapp_agent.ratelimit` for the client-side
    throttle that is meant to prevent this from ever reaching the server.
    """

    def __init__(
        self,
        http_status: int,
        code: int,
        message: str,
        details: str | None = None,
        fbtrace_id: str | None = None,
        *,
        retry_after: float | None = None,
    ):
        super().__init__(http_status, code, message, details, fbtrace_id)
        #: Seconds to wait before retrying, from the response's Retry-After
        #: header when present. None if the server didn't send one.
        self.retry_after = retry_after


class NotAcceptedError(WhatsAppAPIError):
    """The message was not accepted for delivery (503, code 131016). The
    manual is explicit that this means the message was *never sent*, so it is
    always safe to retry after backing off (manual p.9, "Retrying a send").
    """


class InvalidRequestError(WhatsAppAPIError):
    """A required field is missing or malformed, the recipient is not a
    WhatsApp user, or a referenced media id is unknown/expired (400, code
    131009). Also raised for a plain schema violation with no numeric
    ``error.code`` payload (e.g. a length-cap rejection, where ``message`` is
    just the field name -- manual p.24).
    """


class RecipientNotAllowedError(WhatsAppAPIError):
    """The recipient is not the agent's creator (403, code 131005 on
    ``POST /messages``), or the message being marked read was not sent by the
    agent's creator (403, same code, on ``POST /statuses``). An agent may only
    message the WhatsApp account that created it.
    """


class MediaError(WhatsAppAPIError):
    """A media operation failed: the upload exceeded its type's size limit or
    used an unaccepted MIME type (400, code 131053). Note: an unknown/expired
    media id (manual p.27) also uses code 100, the same code as "token
    present but not valid" (manual p.4) -- that specific case is raised as
    :class:`InvalidRequestError`, since the code alone doesn't distinguish
    the two. Check ``.details`` if you need to tell them apart.
    """


class PollConflictError(WhatsAppAPIError):
    """A second concurrent poll for this agent replaced this one (409, code
    1752041). This means the caller is running more than one poller for the
    same agent, which the manual says is not supported -- run exactly one
    ``GET /updates`` loop per agent. This is a caller bug, not a transient
    condition, so :meth:`whatsapp_agent.client.WhatsAppAgentClient.listen`
    re-raises it instead of retrying.
    """


class ServerError(WhatsAppAPIError):
    """An internal server error (500, code 2 or no code at all). The manual
    is explicit that a 500 leaves it *unknown* whether a send went through
    (manual p.9): retrying blindly can double-send. Decide in advance whether
    your use case tolerates a possible duplicate before retrying one of
    these.
    """


#: error.code -> exception class, from the manual's error reference table
#: (p.28) plus the per-endpoint 4xx tables (pp.25-27) for codes that aren't
#: in the main reference (131005 appears only in the endpoint tables).
_CODE_TO_EXCEPTION: dict[int, type[WhatsAppAPIError]] = {
    2: ServerError,
    100: InvalidRequestError,
    190: AuthenticationError,
    130429: RateLimitError,
    131005: RecipientNotAllowedError,
    131009: InvalidRequestError,
    131016: NotAcceptedError,
    131053: MediaError,
    1752041: PollConflictError,
}


def build_error(
    http_status: int,
    code: int,
    message: str,
    details: str | None = None,
    fbtrace_id: str | None = None,
    retry_after: float | None = None,
) -> WhatsAppAPIError:
    """Construct the right :class:`WhatsAppAPIError` subclass for ``code``.

    Falls back to a few HTTP-status-based heuristics for responses that carry
    no ``error.code`` at all -- notably 401s with a malformed Authorization
    header, and generic 500s -- before falling back to the base class.
    """
    cls = _CODE_TO_EXCEPTION.get(code)
    if cls is None:
        if code == -1 and http_status == 401:
            cls = AuthenticationError
        elif code == -1 and http_status == 429:
            cls = RateLimitError
        elif code == -1 and http_status == 500:
            cls = ServerError
        elif code == -1 and http_status == 400:
            cls = InvalidRequestError
        else:
            cls = WhatsAppAPIError
    if cls is RateLimitError:
        return RateLimitError(
            http_status, code, message, details, fbtrace_id, retry_after=retry_after
        )
    return cls(http_status, code, message, details, fbtrace_id)
