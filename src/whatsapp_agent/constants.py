"""Constants pulled directly from the WhatsApp Agent Platform developer manual
(v1, originally published August 25, 2026).

Every value here has a page reference in the manual so it can be re-checked
against a future revision. Keep this module free of behavior -- it is a data
file that ``client.py``, ``transport.py`` and ``ratelimit.py`` read from.
"""
from __future__ import annotations

BASE_URL = "https://api.whatsapp.com/agent/v1"

#: Outbound message types accepted by POST /messages (manual p.6).
MESSAGE_TYPES = frozenset({"text", "image", "audio", "video", "document", "sticker"})

#: Inbound-only message type -- reactions can never be sent (manual p.12, p.25).
RECEIVE_ONLY_TYPES = frozenset({"reaction"})

# ---- Length caps (manual p.4, p.7) -----------------------------------------

TEXT_BODY_MAX_LENGTH = 4096
CAPTION_MAX_LENGTH = 1024

# ---- Media size caps in bytes, per message type (manual p.4, p.19) --------

MEDIA_SIZE_LIMITS: dict[str, int] = {
    "image": 5 * 1024 * 1024,
    "sticker": 500 * 1024,
    "audio": 16 * 1024 * 1024,
    "video": 16 * 1024 * 1024,
    "document": 16 * 1024 * 1024,
}
#: Fallback for a generic/unknown binary upload (manual p.19).
GENERIC_MEDIA_SIZE_LIMIT = 16 * 1024 * 1024

# ---- Accepted MIME types per media kind (manual pp.19-21) ------------------

ACCEPTED_MIME_TYPES: dict[str, frozenset[str]] = {
    "image": frozenset({"image/jpeg", "image/png"}),
    "video": frozenset({"video/mp4", "video/3gpp"}),
    "audio": frozenset(
        {
            "audio/aac",
            "audio/mp4",
            "audio/mpeg",
            "audio/amr",
            "audio/ogg",
            "audio/opus",
        }
    ),
    "document": frozenset(
        {
            "application/pdf",
            "text/plain",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }
    ),
    "sticker": frozenset({"image/webp"}),
}
#: A generic binary upload is always accepted regardless of media kind (manual p.19).
GENERIC_MIME_TYPE = "application/octet-stream"

#: Which media kind a MIME type belongs to, for caption/filename/caps lookups.
MIME_TO_KIND: dict[str, str] = {
    mime: kind for kind, mimes in ACCEPTED_MIME_TYPES.items() for mime in mimes
}

# ---- Captions and filenames (manual p.21) ----------------------------------

#: Message types that accept a caption.
CAPTION_ALLOWED_TYPES = frozenset({"image", "video", "document"})
#: Message types that accept a filename (document only).
FILENAME_ALLOWED_TYPES = frozenset({"document"})

# ---- Rate limits: requests per rolling 60s window, per agent (manual p.28) -

RATE_LIMITS: dict[str, int] = {
    "messages": 12,
    "statuses": 12,
    "updates": 15,
    "media_post": 12,
    "media_get": 12,
    "media_delete": 12,
}

# ---- Update polling (manual pp.9-15) ---------------------------------------

DEFAULT_POLL_LIMIT = 50
MAX_POLL_LIMIT = 100
DEFAULT_POLL_TIMEOUT = 15
MAX_POLL_TIMEOUT = 25
UPDATE_RETENTION_DAYS = 30

# ---- Typing indicator (manual p.17) ----------------------------------------

#: The indicator disappears after this many seconds unless refreshed or replied to.
TYPING_INDICATOR_TTL = 25
#: How long we wait between refreshes inside the `typing()` context manager --
#: comfortably under the TTL so a slow scheduler tick never lets it lapse.
TYPING_INDICATOR_REFRESH_INTERVAL = 20
