"""Tests for whatsapp_agent.markdown.from_markdown against the Markdown
constructs LLMs actually produce.
"""
from __future__ import annotations

import pytest

from whatsapp_agent.markdown import from_markdown


class TestBoldItalic:
    def test_double_star_bold_becomes_single_star(self):
        assert from_markdown("**Total:** $42") == "*Total:* $42"

    def test_double_underscore_bold_becomes_single_star(self):
        assert from_markdown("__Total:__ $42") == "*Total:* $42"

    def test_single_star_italic_becomes_single_underscore(self):
        assert from_markdown("*today*") == "_today_"

    def test_single_underscore_italic_stays_single_underscore(self):
        assert from_markdown("_today_") == "_today_"

    def test_bold_is_not_double_processed_into_italic(self):
        # Regression test: a naive two-pass (bold then italic) converter
        # re-matches its own bold output ("*text*") as italic and wraps it
        # again ("_*text*_"), destroying the bold styling. A single
        # combined pass must not do this.
        result = from_markdown("**important**")
        assert result == "*important*"
        assert "_" not in result

    def test_mixed_bold_and_italic_in_one_line(self):
        result = from_markdown("**bold** and *italic*")
        assert result == "*bold* and _italic_"


class TestStrike:
    def test_double_tilde_becomes_single(self):
        assert from_markdown("~~old price~~") == "~old price~"


class TestHeadings:
    def test_heading_becomes_bold_line(self):
        assert from_markdown("# Order confirmed") == "*Order confirmed*"

    def test_heading_level_is_irrelevant(self):
        assert from_markdown("### Section") == "*Section*"


class TestLinks:
    def test_default_inline_mode(self):
        result = from_markdown("[invoice](https://example.com/inv.pdf)")
        assert result == "invoice (https://example.com/inv.pdf)"

    def test_url_only_mode(self):
        result = from_markdown("[invoice](https://example.com/inv.pdf)", links="url_only")
        assert result == "https://example.com/inv.pdf"

    def test_text_only_mode(self):
        result = from_markdown("[invoice](https://example.com/inv.pdf)", links="text_only")
        assert result == "invoice"

    def test_unknown_links_mode_raises(self):
        with pytest.raises(ValueError):
            from_markdown("[a](b)", links="bogus")


class TestCodeProtection:
    def test_inline_code_is_untouched(self):
        result = from_markdown("Run `pip install **not-bold**` first")
        assert "`pip install **not-bold**`" in result

    def test_fenced_code_block_is_untouched_inside(self):
        md = "```python\nprint('**not bold**')\n```"
        result = from_markdown(md)
        assert "**not bold**" in result
        assert "print('**not bold**')" in result

    def test_fenced_code_language_tag_is_dropped(self):
        md = "```python\nprint('hi')\n```"
        result = from_markdown(md)
        assert "python" not in result.split("\n")[0]


class TestHorizontalRule:
    def test_hr_is_removed(self):
        result = from_markdown("Before\n\n---\n\nAfter")
        assert "---" not in result
        assert "Before" in result and "After" in result


class TestTables:
    def test_default_mono_mode_renders_aligned_block(self):
        md = "| Item | Qty |\n|---|---|\n| Widget | 3 |\n"
        result = from_markdown(md)
        assert result.startswith("```")
        assert result.endswith("```")
        assert "Item" in result and "Widget" in result

    def test_drop_mode_removes_table_entirely(self):
        md = "Before\n\n| Item | Qty |\n|---|---|\n| Widget | 3 |\n\nAfter"
        result = from_markdown(md, tables="drop")
        assert "Item" not in result
        assert "Widget" not in result
        assert "Before" in result and "After" in result

    def test_unknown_tables_mode_raises(self):
        with pytest.raises(ValueError):
            from_markdown("x", tables="bogus")

    def test_line_with_stray_pipe_but_no_separator_is_not_a_table(self):
        result = from_markdown("Cost: $3 | $4 depending on size")
        assert "Cost: $3 | $4 depending on size" in result


class TestFullDocument:
    def test_llm_style_reply_end_to_end(self):
        md = (
            "# Order confirmed\n\n"
            "**Total:** $42.00\n\n"
            "See the [invoice](https://example.com/inv.pdf) for details.\n"
        )
        result = from_markdown(md)
        assert "*Order confirmed*" in result
        assert "*Total:* $42.00" in result
        assert "invoice (https://example.com/inv.pdf)" in result
        assert "**" not in result
        assert "[" not in result and "](" not in result
