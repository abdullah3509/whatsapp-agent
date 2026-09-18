r"""Convert Markdown (the format most LLMs write by default) into WhatsApp's
own formatting syntax.

This is the module to reach for when wiring an LLM's output straight into
`~whatsapp_agent.client.WhatsAppAgentClient.send_text` -- most models were
trained to write GitHub-flavored Markdown, and sent unchanged it renders
wrong in a WhatsApp chat (``**bold**`` shows up as literal asterisks; a
markdown table shows up as a wall of pipe characters). ``from_markdown``
handles the constructs that map onto WhatsApp's syntax and degrades the ones
that don't into something a person reading the chat can still make sense of.

======================  ===========================================
Markdown construct      WhatsApp rendering
======================  ===========================================
``**bold**`` / ``__b__``  -> ``*bold*``
``*italic*`` / ``_i_``    -> ``_italic_``
``~~strike~~``            -> ``~strike~``
`` `code` ``              -> `` `code` `` (unchanged)
` ```block``` `           -> ` ```block``` ` (language tag dropped)
``> quote``               -> ``> quote`` (unchanged)
``- item`` / ``* item``   -> ``- item`` (unchanged)
``1. item``               -> ``1. item`` (unchanged)
``# Heading``             -> ``*Heading*`` (bold line; no heading concept)
``[text](url)``           -> ``text (url)`` (no link concept)
``| table |``             -> monospace block (no table concept)
``---`` / ``***``         -> dropped (no horizontal rule concept)
======================  ===========================================

This is a pragmatic, regex-based converter for LLM-generated prose, not a
full CommonMark implementation -- it does not build an AST and does not
handle every edge case of nested/adjacent emphasis that the CommonMark spec
defines. It is tested against the constructs LLMs actually produce.
"""
from __future__ import annotations

import re

_FENCE_RE = re.compile(r"```(?:[^\n`]*)\n(.*?)```", re.DOTALL)
# Bold and italic are matched in a single alternation, tried in this order,
# rather than as two sequential re.sub() passes: a second pass over already
# -converted output can't tell "*text*" it just produced (WhatsApp bold)
# apart from Markdown italic, and would re-wrap it as `_*text*_`. A single
# pass never re-scans its own replacements, so bold alternatives are listed
# first and win at each position.
_EMPHASIS_RE = re.compile(
    r"\*\*(?P<bold1>.+?)\*\*"
    r"|__(?P<bold2>.+?)__"
    r"|(?<!\*)\*(?!\*)(?P<italic1>.+?)(?<!\*)\*(?!\*)"
    r"|(?<!_)_(?!_)(?P<italic2>.+?)(?<!_)_(?!_)",
    re.DOTALL,
)
_STRIKE_RE = re.compile(r"~~(.+?)~~", re.DOTALL)
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)
_HR_RE = re.compile(r"^ {0,3}([-*_])(?:\s*\1){2,}\s*$", re.MULTILINE)
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")

_PLACEHOLDER = "\x00{}\x00"


def from_markdown(md: str, *, links: str = "inline", tables: str = "mono") -> str:
    """Convert Markdown ``md`` to WhatsApp-formatted text.

    :param links: how to render ``[text](url)``.

        - ``"inline"`` (default): ``text (url)``.
        - ``"url_only"``: just ``url``, dropping the link text.
        - ``"text_only"``: just ``text``, dropping the URL.

    :param tables: how to render a GitHub-flavored Markdown table.

        - ``"mono"`` (default): the table's rows and columns, aligned with
          spaces, inside a triple-backtick monospace block -- the closest a
          WhatsApp chat can get to a readable table.
        - ``"drop"``: tables are removed entirely.

    Code spans and fenced code blocks are protected from every other
    transformation (so a literal ``**`` inside a code block is never turned
    into a bold marker) by extracting them first and splicing them back in
    verbatim at the end.
    """
    if links not in ("inline", "url_only", "text_only"):
        raise ValueError(f"unknown links mode: {links!r}")
    if tables not in ("mono", "drop"):
        raise ValueError(f"unknown tables mode: {tables!r}")

    protected: list[str] = []

    def _protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return _PLACEHOLDER.format(len(protected) - 1)

    # Fenced code blocks first (may contain backticks/asterisks that must
    # survive untouched), then inline code spans.
    text = _FENCE_RE.sub(lambda m: _protect_fence(m, protected), md)
    text = re.sub(r"`([^`\n]+)`", _protect, text)

    # Tables and headings both *produce* new formatting markers (a
    # monospace block; a bold line). Both are protected behind a placeholder
    # as soon as they're built, the same way a code span is, so the
    # emphasis/strike passes below -- which run once, over the whole text --
    # never see and re-wrap the markers these steps just added. Without
    # this, "# Heading" -> "*Heading*" gets re-matched by the italic
    # pattern's single-asterisk rule and corrupted into "_Heading_".
    text = _convert_tables(text, mode=tables, protected=protected)
    text = _HR_RE.sub("", text)
    text = _HEADING_RE.sub(lambda m: _render_heading(m, protected), text)
    text = _LINK_RE.sub(lambda m: _render_link(m, links), text)
    text = _STRIKE_RE.sub(lambda m: f"~{m.group(1)}~", text)
    text = _EMPHASIS_RE.sub(_render_emphasis, text)

    # Collapse runs of 3+ blank lines left behind by dropped constructs
    # (headings, hrules, tables) down to a single blank line.
    text = re.sub(r"\n{3,}", "\n\n", text)

    for i, original in enumerate(protected):
        text = text.replace(_PLACEHOLDER.format(i), original)
    return text.strip()


def _protect_fence(match: re.Match[str], protected: list[str]) -> str:
    # Re-emit the fence without a language tag -- WhatsApp shows the tag as
    # a literal first line of the block, which is worse than dropping it.
    body = match.group(1)
    rendered = f"```{body}```"
    protected.append(rendered)
    return _PLACEHOLDER.format(len(protected) - 1)


def _render_heading(match: re.Match[str], protected: list[str]) -> str:
    # Convert any inline emphasis within the heading's own text first (e.g.
    # "# **Order** confirmed"), then wrap the whole line in bold and protect
    # the result -- see the note in from_markdown() for why.
    content = match.group(2)
    content = _STRIKE_RE.sub(lambda m: f"~{m.group(1)}~", content)
    content = _EMPHASIS_RE.sub(_render_emphasis, content)
    rendered = f"*{content}*"
    protected.append(rendered)
    return _PLACEHOLDER.format(len(protected) - 1)


def _render_emphasis(match: re.Match[str]) -> str:
    bold = match.group("bold1") if match.group("bold1") is not None else match.group("bold2")
    if bold is not None:
        return f"*{bold}*"
    italic = (
        match.group("italic1") if match.group("italic1") is not None else match.group("italic2")
    )
    return f"_{italic}_"


def _render_link(match: re.Match[str], mode: str) -> str:
    text, url = match.group(1), match.group(2)
    if mode == "url_only":
        return url
    if mode == "text_only":
        return text or url
    return f"{text} ({url})" if text else url


def _convert_tables(text: str, *, mode: str, protected: list[str]) -> str:
    """Find GitHub-flavored Markdown tables (a header row containing ``|``,
    immediately followed by a ``|---|---|``-style separator row) and replace
    each one per ``mode``. Lines that merely contain a stray ``|`` with no
    following separator row are left alone.

    A rendered table (``mode="mono"``) is a triple-backtick block built
    fresh here, *after* the original text's own fenced code blocks were
    already protected -- so it must be pushed onto ``protected`` and
    replaced with a placeholder itself, or a cell containing a stray ``*``
    or ``_`` would get mangled by the emphasis pass later.
    """
    lines = text.split("\n")
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        is_table_start = (
            "|" in lines[i] and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1]) is not None
        )
        if is_table_start:
            table_lines = [lines[i], lines[i + 1]]
            j = i + 2
            while j < n and "|" in lines[j]:
                table_lines.append(lines[j])
                j += 1
            if mode != "drop":
                rendered = _render_table_mono(table_lines)
                protected.append(rendered)
                out.append(_PLACEHOLDER.format(len(protected) - 1))
            i = j
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def _render_table_mono(table_lines: list[str]) -> str:
    rows = []
    for idx, line in enumerate(table_lines):
        if idx == 1 and _TABLE_SEP_RE.match(line):
            continue  # the |---|---| separator row carries no content
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    col_widths = [0] * width
    for row in rows:
        for c, cell in enumerate(row):
            col_widths[c] = max(col_widths[c], len(cell))
    lines_out = []
    for row in rows:
        padded = [cell.ljust(col_widths[c]) for c, cell in enumerate(row)]
        lines_out.append("  ".join(padded).rstrip())
    return "```\n" + "\n".join(lines_out) + "\n```"
