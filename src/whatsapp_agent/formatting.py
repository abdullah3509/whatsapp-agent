r"""WhatsApp's own text formatting syntax.

WhatsApp is **not** Markdown. It uses a small, Markdown-*like* set of inline
markers that a WhatsApp client renders in the chat UI, but several of the
most common Markdown conventions either mean something different or do
nothing at all:

=====================  =================  =========================
Style                  WhatsApp            Markdown (for contrast)
=====================  =================  =========================
Bold                   ``*text*``          ``**text**``
Italic                 ``_text_``          ``*text*`` or ``_text_``
Strikethrough          ``~text~``          ``~~text~~``
Monospace block        ` ```text``` `      ` ```lang\ntext\n``` `
Inline code            `` `text` ``        `` `text` `` (same)
Blockquote             ``> text``          ``> text`` (same)
Bulleted list          ``- item``          ``- item`` (same)
Numbered list          ``1. item``         ``1. item`` (same)
=====================  =================  =========================

The most common way agent output ends up looking broken in a WhatsApp chat is
sending Markdown's ``**bold**`` -- WhatsApp renders that literally, as two
asterisks either side of the text, because a single ``*`` is its bold marker
and two of them just means "bold marker, then a literal asterisk, then
non-bold text, then a literal asterisk, then bold marker."

WhatsApp has **no equivalent at all** for Markdown headings, links
(``[text](url)``), images, tables, horizontal rules, or nested lists -- see
:mod:`whatsapp_agent.markdown` for how ``from_markdown`` degrades each of
these to something that reads sensibly in a chat instead of leaking raw
Markdown syntax.

See ``docs/formatting.md`` for the full reference with rendered examples.
"""
from __future__ import annotations

import unicodedata
from collections.abc import Sequence

#: Zero-width joiner used by :func:`escape` to break up a marker sequence
#: without a visible artifact. WhatsApp has no escape character (there is no
#: backslash-escape for ``*``, ``_``, ``~`` or a backtick) -- inserting an
#: invisible codepoint between two characters that would otherwise form a
#: marker is the only known workaround, not a documented feature of the
#: format. See :func:`escape` for the caveats.
_WORD_JOINER = "⁠"

_MARKER_CHARS = "*_~`"


def _wrap(text: str, marker: str) -> str:
    """Wrap non-empty, non-whitespace-only ``text`` in ``marker`` on both
    sides. WhatsApp's markers must hug the text with no surrounding
    whitespace -- ``* text *`` renders as literal asterisks, not bold
    (verified against the WhatsApp client; not separately called out in the
    manual, which does not cover the chat UI's rendering rules) -- so this
    strips leading/trailing whitespace from ``text`` before wrapping and
    raises if nothing is left.
    """
    stripped = text.strip()
    if not stripped:
        raise ValueError(
            f"cannot apply {marker!r} formatting to empty or whitespace-only text"
        )
    return f"{marker}{stripped}{marker}"


def bold(text: str) -> str:
    """Wrap ``text`` in WhatsApp's bold marker: ``*text*``.

    Composes with the other inline wrappers for combined styles, e.g.
    ``bold(italic("x"))`` -> ``"*_x_*"``, which WhatsApp renders bold *and*
    italic.
    """
    return _wrap(text, "*")


def italic(text: str) -> str:
    """Wrap ``text`` in WhatsApp's italic marker: ``_text_``."""
    return _wrap(text, "_")


def strike(text: str) -> str:
    """Wrap ``text`` in WhatsApp's strikethrough marker: ``~text~``.

    Note this is a single tilde on each side, unlike Markdown's ``~~text~~``.
    """
    return _wrap(text, "~")


def code(text: str) -> str:
    """Wrap ``text`` in WhatsApp's inline code marker: `` `text` ``.

    Same syntax as Markdown inline code.
    """
    return _wrap(text, "`")


def mono(text: str) -> str:
    """Wrap ``text`` in a triple-backtick monospace block.

    Unlike Markdown, WhatsApp's monospace block does not support a language
    tag after the opening fence -- ```` ```python ```` renders the word
    ``python`` as the first line of the block, not as syntax-highlighting
    metadata.
    """
    stripped = text.strip("\n")
    if not stripped.strip():
        raise ValueError("cannot apply mono formatting to empty or whitespace-only text")
    return f"```{stripped}```"


def quote(text: str) -> str:
    """Prefix every line of ``text`` with WhatsApp's blockquote marker
    (``> `` at the start of a line). Multi-line input becomes a multi-line
    quote, one ``>`` per line -- WhatsApp has no "lazy continuation" the way
    some Markdown renderers do.
    """
    lines = text.strip("\n").splitlines()
    if not any(line.strip() for line in lines):
        raise ValueError("cannot apply quote formatting to empty or whitespace-only text")
    return "\n".join(f"> {line}" if line else ">" for line in lines)


def bullet_list(items: Sequence[str], *, marker: str = "-") -> str:
    """Build a bulleted list, one ``marker`` per item. ``marker`` must be
    ``"-"`` or ``"*"`` -- WhatsApp's two accepted bullet markers.
    """
    if marker not in ("-", "*"):
        raise ValueError('marker must be "-" or "*"')
    if not items:
        raise ValueError("items must not be empty")
    return "\n".join(f"{marker} {item}" for item in items)


def numbered_list(items: Sequence[str], *, start: int = 1) -> str:
    """Build a numbered list: ``1. item``, ``2. item``, ...``."""
    if not items:
        raise ValueError("items must not be empty")
    return "\n".join(f"{i}. {item}" for i, item in enumerate(items, start=start))


def escape(text: str, *, method: str = "word_joiner") -> str:
    """Neutralize WhatsApp formatting markers (``*_~\\```` ) inside ``text``
    so user-supplied content can't accidentally trigger formatting or break
    out of formatting you applied around it.

    **WhatsApp has no escape character** -- there is no backslash-escape for
    a marker the way Markdown has ``\\*``. This is a workaround, not a
    documented feature of the format:

    - ``method="word_joiner"`` (default): inserts U+2060 WORD JOINER, an
      invisible zero-width codepoint, immediately after every marker
      character. A marker followed by a word joiner cannot pair with another
      marker to form a formatting span, but the joiner does not display and
      does not survive being copy-pasted back out character-for-character in
      most WhatsApp clients as a visible artifact. It is still an extra
      codepoint in the string, which matters if you later measure length
      against WhatsApp's 4096-character cap -- use :func:`truncate` on
      already-escaped text, or truncate before escaping.
    - ``method="none"``: returns ``text`` unchanged. Provided so callers can
      make the "do nothing" choice explicit rather than by omission.

    Raises :class:`ValueError` for any other ``method``.
    """
    if method == "none":
        return text
    if method != "word_joiner":
        raise ValueError(f"unknown escape method: {method!r}")
    return "".join(f"{ch}{_WORD_JOINER}" if ch in _MARKER_CHARS else ch for ch in text)


def strip_formatting(text: str) -> str:
    """Remove WhatsApp formatting markers, returning plain text.

    Handles ``*bold*``, ``_italic_``, ``~strike~``, `` `code` ``, and
    ```` ```mono``` ```` spans, plus a leading ``> `` on quoted lines. This is
    a best-effort strip for display/logging purposes, not a full parser --
    each marker type is stripped by pairing occurrences left to right, so it
    does not attempt to disambiguate a marker used as formatting from the
    same character appearing as ordinary punctuation (WhatsApp's own client
    has the same ambiguity, since the format has no escape character; see
    :func:`escape`). Mono blocks are stripped first so a ``*`` inside one
    is never mistaken for a bold marker.
    """
    lines = text.split("\n")
    unquoted = "\n".join(
        line[2:] if line.startswith("> ") else ("" if line == ">" else line) for line in lines
    )

    result = _strip_marker_pairs(unquoted, "```")
    for marker in ("*", "_", "~", "`"):
        result = _strip_marker_pairs(result, marker)
    return result


def _strip_marker_pairs(text: str, marker: str) -> str:
    """Remove ``marker`` wherever it appears in a balanced (even-count) pair,
    pairing occurrences left to right. A trailing unpaired occurrence -- an
    odd one out -- is left in place untouched, on the assumption it is
    ordinary punctuation rather than an unclosed formatting span.
    """
    parts = text.split(marker)
    if len(parts) < 3:
        return text
    pair_count = (len(parts) - 1) // 2 * 2
    paired, rest = parts[: pair_count + 1], parts[pair_count + 1 :]
    stripped = "".join(paired)
    if rest:
        stripped += marker + marker.join(rest)
    return stripped


def truncate(text: str, limit: int = 4096) -> str:
    """Truncate ``text`` to at most ``limit`` characters -- WhatsApp's cap
    counts formatting markers as ordinary characters (manual p.7: 4096 for a
    message body, 1024 for a caption), so this does too.

    Cuts on a Unicode grapheme-safe boundary (never splits a surrogate pair)
    and never leaves a truncated string with an odd number of a given
    marker character trailing at the very end, which would otherwise turn
    the rest of a long message into one giant unintended bold/italic span
    for the reader. If the natural cut point lands inside an open marker
    span, the incomplete trailing marker is dropped rather than closed,
    since we cannot know what the writer intended to put inside it.
    """
    if limit < 0:
        raise ValueError("limit must be >= 0")
    if len(text) <= limit:
        return text

    cut = text[:limit]
    # `limit < len(text)` here (we returned early otherwise), so `cut` is
    # always strictly shorter than `text` and `text[len(cut)]` is safe to
    # index. Back off past any combining mark or ZWJ/variation-selector that
    # would otherwise be severed from the base character it modifies --
    # Python `str` code points are already composed, so full surrogate pairs
    # are never at risk, but multi-codepoint grapheme clusters are.
    while cut and _is_combining_or_joiner(text[len(cut)]):
        cut = cut[:-1]

    # Trim a dangling, unpaired marker run at the very end so we don't leave
    # e.g. a lone "*" that turns everything after it (in a later concatenation)
    # into unintended formatting, and so each marker type has an even count.
    for marker in ("*", "_", "~", "`"):
        while cut.count(marker) % 2 == 1 and cut.endswith(marker):
            cut = cut[:-1]
    return cut


def _is_combining_or_joiner(ch: str) -> bool:
    return unicodedata.combining(ch) != 0 or ch in ("‍", "️")
