# WhatsApp text formatting

WhatsApp renders a small set of inline formatting markers in its chat UI. It looks like Markdown at a glance, but it isn't — several of Markdown's most common conventions either mean something else in WhatsApp or don't work at all. This is the single most common way an LLM-generated reply shows up looking broken in a WhatsApp chat: the model writes `**bold**` (Markdown), WhatsApp shows it as literal double asterisks, because a *single* `*` is WhatsApp's bold marker.

This page is the full reference. The short version lives in the [README](../README.md#whatsapp-text-formatting).

## Syntax reference

| Style | WhatsApp syntax | Example input | Renders as |
|---|---|---|---|
| Bold | `*text*` | `*Hello*` | **Hello** |
| Italic | `_text_` | `_Hello_` | *Hello* |
| Strikethrough | `~text~` | `~Hello~` | ~~Hello~~ |
| Monospace block | ` ```text``` ` | ` ```Hello``` ` | `Hello` (block) |
| Inline code | `` `text` `` | `` `Hello` `` | `Hello` |
| Blockquote | `> text` (start of line) | `> Hello` | quoted line |
| Bulleted list | `- item` or `* item` | `- Hello` | • Hello |
| Numbered list | `1. item` | `1. Hello` | 1. Hello |

Markers must hug the text with no surrounding whitespace: `* text *` renders as literal asterisks, not bold. `whatsapp_agent.formatting`'s wrappers strip stray whitespace for you before applying a marker.

Styles compose by nesting: `*_text_*` renders bold **and** italic.

## What Markdown has that WhatsApp doesn't

None of these have a WhatsApp equivalent — there is no syntax that produces them:

- Headings (`# Heading`)
- Links (`[text](url)`)
- Images (`![alt](url)`)
- Tables (`| a | b |`)
- Horizontal rules (`---`)
- Arbitrarily nested lists

`whatsapp_agent.markdown.from_markdown` degrades each of these to something a person can still read in a chat instead of leaking raw Markdown syntax — see [Converting from Markdown](#converting-from-markdown) below.

## Double vs. single markers

The single biggest gotcha, worth stating plainly:

| You write (thinking Markdown) | WhatsApp sees | WhatsApp renders |
|---|---|---|
| `**bold**` | `*` + `*bold*` + `*` | `*`bold`*` (literal asterisks around bold text) |
| `~~strike~~` | `~` + `~strike~` + `~` | `~`~~strike~~`~` (literal tildes) |

If your text source is Markdown — which is the default output style of essentially every LLM — always run it through `from_markdown()` before sending, or use the MCP server's `wa_format_text` tool.

## Using the `formatting` module directly

```python
from whatsapp_agent.formatting import (
    bold, italic, strike, code, mono, quote,
    bullet_list, numbered_list,
    escape, strip_formatting, truncate,
)

bold("Total: $42")                      # "*Total: $42*"
italic("today")                         # "_today_"
bold(italic("urgent"))                  # "*_urgent_*"  (bold + italic)
bullet_list(["Milk", "Eggs", "Bread"])  # "- Milk\n- Eggs\n- Bread"
numbered_list(["First", "Second"])      # "1. First\n2. Second"
quote("Thanks for your order")          # "> Thanks for your order"
```

Wrapping empty or whitespace-only text raises `ValueError` — there's nothing sensible to render.

### Converting from Markdown

```python
from whatsapp_agent.markdown import from_markdown

from_markdown("**Total:** $42.00")
# -> "*Total:* $42.00"

from_markdown("See the [invoice](https://example.com/inv.pdf) for details.")
# -> "See the invoice (https://example.com/inv.pdf) for details."

from_markdown("# Order confirmed\n\nThanks!")
# -> "*Order confirmed*\n\nThanks!"
```

`from_markdown` takes two options for the constructs that have no WhatsApp equivalent:

```python
from_markdown(text, links="inline")     # "text (url)" (default)
from_markdown(text, links="url_only")   # just "url"
from_markdown(text, links="text_only")  # just "text"

from_markdown(text, tables="mono")      # render as an aligned monospace block (default)
from_markdown(text, tables="drop")      # remove tables entirely
```

Fenced code blocks and inline code spans are protected from every other conversion — a literal `**` or `#` inside a code block is never touched. A language tag after a fence (`` ```python ``) is dropped, since WhatsApp would otherwise show the word "python" as the block's first line.

This is a pragmatic, regex-based converter tuned for the Markdown that LLMs actually produce, not a full CommonMark implementation.

### Escaping

**WhatsApp has no escape character.** There is no backslash-escape for `*`, `_`, `~`, or `` ` `` the way Markdown has `\*`. If you're interpolating untrusted or unpredictable text (a user's name, a product title) into a message you're formatting yourself, an odd number of `*` in their text can silently start or close a bold span you didn't intend.

`escape()` is a workaround, not a documented WhatsApp feature:

```python
from whatsapp_agent.formatting import escape, bold

user_name = "Rock*Star"
bold(f"Welcome, {escape(user_name)}!")
# The '*' in "Rock*Star" is neutralized so it can't pair with anything else
# and break the surrounding bold span.
```

It works by inserting a U+2060 WORD JOINER — an invisible character — immediately after each marker character. A marker followed by a word joiner can't pair with another marker to form a span, and the joiner doesn't display or show up as a visible artifact in a WhatsApp client. It does add an extra (invisible) code point per marker, which matters if you're about to check length against the 4096-character cap — call `truncate()` on the already-escaped text, not before.

Pass `method="none"` to make "don't escape this" an explicit choice rather than an accidental omission:

```python
escape(text, method="none")  # returns text unchanged
```

### Stripping formatting

```python
from whatsapp_agent.formatting import strip_formatting

strip_formatting("*Hello* _world_")  # -> "Hello world"
```

Best-effort, for logging/display purposes — it pairs up marker occurrences left to right and isn't a full parser, so it has the same ambiguity a WhatsApp client itself has when a marker character is meant as ordinary punctuation rather than formatting (there's no escape character to disambiguate; see above).

### Truncating safely

```python
from whatsapp_agent.formatting import truncate

truncate(long_text)          # cuts to 4096 chars (message body cap)
truncate(long_caption, 1024)  # cuts to 1024 chars (caption cap)
```

WhatsApp's length caps count formatting markers as ordinary characters (a message with `*bold*` around most of it still only gets 4096 characters total). `truncate()`:

- Cuts on a grapheme-safe boundary, so it never splits an emoji or a combining character sequence in half.
- Never leaves a marker character with an odd, unpaired count at the very end of the truncated string — a lone trailing `*` would otherwise turn everything appended after it (e.g. by a later concatenation) into an unintended bold span for the reader.

## Length and size caps (from the manual)

| Field | Cap |
|---|---|
| `text.body` | 4096 characters |
| Caption (image/video/document) | 1024 characters |
| Image | 5 MB |
| Sticker | 500 KB |
| Video / audio / document / generic binary | 16 MB |

`whatsapp_agent.constants` holds these as `TEXT_BODY_MAX_LENGTH`, `CAPTION_MAX_LENGTH`, and `MEDIA_SIZE_LIMITS`. The client validates against them locally before making a request, so a length or size violation raises immediately as a `ValueError`/`InvalidRequestError` rather than costing a round trip to the API.

## "Why did my agent's `**bold**` show up as literal asterisks?"

Because it was sent as Markdown, and WhatsApp isn't Markdown. Fixes, in order of preference:

1. Run the text through `whatsapp_agent.markdown.from_markdown()` before sending.
2. If you're on the MCP server, call `wa_format_text` (or pass `from_markdown_source=True` to `wa_send_text`) instead of sending the model's raw output.
3. If you're composing the message yourself rather than relaying an LLM's output, use `whatsapp_agent.formatting.bold()`/`italic()`/etc. directly instead of hand-writing marker characters.
