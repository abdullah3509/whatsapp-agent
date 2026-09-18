"""Tests for whatsapp_agent.formatting -- WhatsApp's own text formatting
syntax (single-* bold, single-_ italic, single-~ strike; see docs/formatting.md).
"""
from __future__ import annotations

import pytest

from whatsapp_agent.formatting import (
    bold,
    bullet_list,
    code,
    escape,
    italic,
    mono,
    numbered_list,
    quote,
    strike,
    strip_formatting,
    truncate,
)


class TestInlineWrappers:
    def test_bold(self):
        assert bold("Hello") == "*Hello*"

    def test_italic(self):
        assert italic("Hello") == "_Hello_"

    def test_strike_is_single_tilde_not_double(self):
        assert strike("Hello") == "~Hello~"

    def test_code(self):
        assert code("Hello") == "`Hello`"

    def test_mono_is_triple_backtick(self):
        assert mono("print('hi')") == "```print('hi')```"

    def test_bold_strips_surrounding_whitespace(self):
        assert bold("  Hello  ") == "*Hello*"

    def test_nesting_bold_and_italic_composes(self):
        assert bold(italic("urgent")) == "*_urgent_*"

    @pytest.mark.parametrize("fn", [bold, italic, strike, code, mono])
    def test_empty_text_raises(self, fn):
        with pytest.raises(ValueError):
            fn("")

    @pytest.mark.parametrize("fn", [bold, italic, strike, code])
    def test_whitespace_only_text_raises(self, fn):
        with pytest.raises(ValueError):
            fn("   ")


class TestQuote:
    def test_single_line(self):
        assert quote("Hello") == "> Hello"

    def test_multi_line_quotes_every_line(self):
        assert quote("Line one\nLine two") == "> Line one\n> Line two"

    def test_empty_line_gets_bare_marker(self):
        assert quote("A\n\nB") == "> A\n>\n> B"

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError):
            quote("   \n  ")


class TestLists:
    def test_bullet_list_default_marker(self):
        assert bullet_list(["a", "b"]) == "- a\n- b"

    def test_bullet_list_star_marker(self):
        assert bullet_list(["a", "b"], marker="*") == "* a\n* b"

    def test_bullet_list_rejects_bad_marker(self):
        with pytest.raises(ValueError):
            bullet_list(["a"], marker="+")

    def test_bullet_list_rejects_empty(self):
        with pytest.raises(ValueError):
            bullet_list([])

    def test_numbered_list(self):
        assert numbered_list(["First", "Second"]) == "1. First\n2. Second"

    def test_numbered_list_custom_start(self):
        assert numbered_list(["a", "b"], start=5) == "5. a\n6. b"

    def test_numbered_list_rejects_empty(self):
        with pytest.raises(ValueError):
            numbered_list([])


class TestEscape:
    def test_default_inserts_word_joiner_after_markers(self):
        result = escape("a*b_c~d`e")
        # Every marker character is immediately followed by U+2060.
        assert "*⁠" in result
        assert "_⁠" in result
        assert "~⁠" in result
        assert "`⁠" in result

    def test_escaped_text_strips_back_to_something_sane(self):
        # After escaping, the markers can no longer pair up into a
        # formatting span -- stripping should leave the text unchanged
        # (module the invisible joiners), not silently eat characters.
        original = "3 * 4 = 12"
        escaped = escape(original)
        assert escaped.replace("⁠", "") == original

    def test_method_none_is_a_no_op(self):
        assert escape("*bold*", method="none") == "*bold*"

    def test_unknown_method_raises(self):
        with pytest.raises(ValueError):
            escape("x", method="bogus")

    def test_escaped_marker_is_distinguishable_from_wrapping_markers(self):
        # The point: after escape() + bold(), the user's own '*' can be
        # told apart from the two markers bold() added, because only the
        # user's is immediately followed by the word joiner.
        user_input = "Rock*Star"
        wrapped = bold(escape(user_input))
        assert wrapped == "*Rock*\u2060Star*"
        joined_markers = [
            i for i, ch in enumerate(wrapped)
            if ch == "*" and wrapped[i + 1 : i + 2] == "\u2060"
        ]
        assert len(joined_markers) == 1


class TestStripFormatting:
    def test_strips_bold(self):
        assert strip_formatting("*Hello*") == "Hello"

    def test_strips_multiple_styles(self):
        assert strip_formatting("*Hello* _world_") == "Hello world"

    def test_strips_mono_block_before_single_backtick(self):
        assert strip_formatting("```code block```") == "code block"

    def test_leaves_unpaired_marker_alone(self):
        assert strip_formatting("3 * 4 = 12") == "3 * 4 = 12"

    def test_strips_leading_quote_marker(self):
        assert strip_formatting("> quoted line") == "quoted line"

    def test_round_trips_through_bold_and_italic(self):
        original = "urgent"
        assert strip_formatting(bold(italic(original))) == original


class TestTruncate:
    def test_shorter_than_limit_is_unchanged(self):
        assert truncate("hello", 10) == "hello"

    def test_cuts_to_limit(self):
        assert len(truncate("x" * 100, 10)) <= 10

    def test_default_limit_is_4096(self):
        text = "x" * 5000
        assert len(truncate(text)) <= 4096

    def test_never_leaves_a_trailing_unpaired_marker(self):
        # "*bold" with no closing marker, cut right after the opening '*'.
        text = "*bold text that keeps going"
        result = truncate(text, 1)
        assert not result.endswith("*")

    def test_does_not_split_a_zwj_emoji_sequence(self):
        family = "\U0001F468‍\U0001F469‍\U0001F467"  # man-woman-girl ZWJ sequence
        text = "a" + family + "b"
        result = truncate(text, len("a") + 1)  # cut right after 'a', mid-sequence
        # Must not end on a lone combining/joiner codepoint.
        assert not result or result[-1] not in ("‍",)

    def test_negative_limit_raises(self):
        with pytest.raises(ValueError):
            truncate("hello", -1)

    def test_limit_zero_returns_empty(self):
        assert truncate("hello", 0) == ""
