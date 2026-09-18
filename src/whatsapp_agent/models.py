"""Typed views over the JSON payloads described in the developer manual.

Every ``from_dict`` reads optional keys with ``.get`` rather than assuming
they are present with an empty value. The manual is explicit that fields like
``profile``, ``caption`` and ``audio.voice`` are *present-or-absent*, not
present-with-an-empty-string (manual p.11, p.12) -- treating a missing key as
``""`` would silently misreport "no profile name set" as "profile name is
empty string", which is a different fact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Contact:
    """One entry in ``contacts[]`` -- the WhatsApp user on the other side of
    the conversation (manual p.11).
    """

    wa_id: str
    input: str | None = None
    #: The user's profile name, or None if they haven't set one. Do not treat
    #: an absent name the same as an empty string -- check for None.
    profile_name: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Contact:
        profile = data.get("profile") or {}
        return cls(
            wa_id=data["wa_id"],
            input=data.get("input"),
            profile_name=profile.get("name"),
            raw=data,
        )


@dataclass
class MediaRef:
    """A media payload nested in a :class:`Message` (manual pp.12-13). Only
    the fields relevant to the message's ``type`` are populated; the rest
    stay ``None``.
    """

    id: str
    mime_type: str
    #: Base64-encoded SHA-256 digest of the stored bytes. Note this is
    #: *Base64* here but *hex* when returned by ``GET /media/<id>`` (manual
    #: p.13 vs p.22) -- see :func:`whatsapp_agent.client.verify_media_sha256`
    #: before comparing the two directly.
    sha256: str | None = None
    caption: str | None = None
    filename: str | None = None
    #: True on a voice note (audio only); absent/None otherwise.
    voice: bool | None = None
    #: False for a static sticker, True for animated (sticker only). Always
    #: False on a sticker *received* -- animated stickers can only be sent.
    animated: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MediaRef:
        return cls(
            id=data["id"],
            mime_type=data.get("mime_type", ""),
            sha256=data.get("sha256"),
            caption=data.get("caption"),
            filename=data.get("filename"),
            voice=data.get("voice"),
            animated=data.get("animated"),
            raw=data,
        )


@dataclass
class MessageContext:
    """Present when a message quotes an earlier one (manual p.12)."""

    message_id: str
    from_: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MessageContext:
        return cls(message_id=data["id"], from_=data["from"], raw=data)


@dataclass
class Reaction:
    """An inbound, receive-only reaction (manual p.12). ``emoji`` is an empty
    string when the reaction was removed, not absent -- check for ``""``,
    not ``None``.
    """

    message_id: str
    emoji: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Reaction:
        return cls(message_id=data["message_id"], emoji=data.get("emoji", ""), raw=data)


@dataclass
class Message:
    """One inbound message from ``entry[].changes[].value.messages[]``
    (manual p.11-13).
    """

    id: str
    from_: str
    timestamp: str
    type: str
    text: str | None = None
    image: MediaRef | None = None
    audio: MediaRef | None = None
    video: MediaRef | None = None
    document: MediaRef | None = None
    sticker: MediaRef | None = None
    reaction: Reaction | None = None
    context: MessageContext | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        msg_type = data.get("type", "")
        context_data = data.get("context")
        text_data = data.get("text")
        return cls(
            id=data["id"],
            from_=data["from"],
            timestamp=data.get("timestamp", ""),
            type=msg_type,
            text=text_data.get("body") if text_data else None,
            image=MediaRef.from_dict(data["image"]) if "image" in data else None,
            audio=MediaRef.from_dict(data["audio"]) if "audio" in data else None,
            video=MediaRef.from_dict(data["video"]) if "video" in data else None,
            document=MediaRef.from_dict(data["document"]) if "document" in data else None,
            sticker=MediaRef.from_dict(data["sticker"]) if "sticker" in data else None,
            reaction=Reaction.from_dict(data["reaction"]) if "reaction" in data else None,
            context=MessageContext.from_dict(context_data) if context_data else None,
            raw=data,
        )

    @property
    def media(self) -> MediaRef | None:
        """The populated media payload, whatever the type -- convenience for
        code that doesn't need to branch on ``type`` first.
        """
        return self.image or self.audio or self.video or self.document or self.sticker


@dataclass
class Status:
    """A delivery/read receipt for a message *your* agent sent (manual
    p.14).
    """

    id: str
    status: str
    recipient_id: str
    timestamp: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Status:
        return cls(
            id=data["id"],
            status=data.get("status", ""),
            recipient_id=data.get("recipient_id", ""),
            timestamp=data.get("timestamp", ""),
            raw=data,
        )


@dataclass
class Updates:
    """One ``GET /updates`` response (manual pp.9-15)."""

    messages: list[Message]
    statuses: list[Status]
    contacts: list[Contact]
    next_offset: int | None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Updates:
        value = data["entry"][0]["changes"][0]["value"]
        return cls(
            messages=[Message.from_dict(m) for m in value.get("messages", [])],
            statuses=[Status.from_dict(s) for s in value.get("statuses", [])],
            contacts=[Contact.from_dict(c) for c in value.get("contacts", [])],
            next_offset=data.get("next_offset"),
            raw=data,
        )


@dataclass
class MediaInfo:
    """Response of ``GET /media/<MEDIA_ID>`` (manual p.21-22)."""

    id: str
    url: str
    mime_type: str
    #: **Hex**-encoded SHA-256 digest -- the same bytes as a message's
    #: ``<type>.sha256`` field, but Base64 there and hex here (manual p.22).
    sha256: str
    file_size: int
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MediaInfo:
        return cls(
            id=data["id"],
            url=data["url"],
            mime_type=data.get("mime_type", ""),
            sha256=data.get("sha256", ""),
            file_size=data.get("file_size", 0),
            raw=data,
        )
