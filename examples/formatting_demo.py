#!/usr/bin/env python3
"""Demonstrates whatsapp_agent.formatting and whatsapp_agent.markdown without
needing an API token -- these are pure string functions.

Run:
    python examples/formatting_demo.py
"""
from __future__ import annotations

from whatsapp_agent.formatting import (
    bold,
    bullet_list,
    escape,
    italic,
    numbered_list,
    quote,
    strike,
    strip_formatting,
    truncate,
)
from whatsapp_agent.markdown import from_markdown


def main() -> None:
    print("-- inline wrappers --")
    print(bold("Order #1234"))
    print(italic("shipped today"))
    print(strike("was $50"))
    print(bold(italic("urgent")))  # composes: bold AND italic

    print("\n-- lists --")
    print(bullet_list(["Milk", "Eggs", "Bread"]))
    print(numbered_list(["First step", "Second step"]))
    print(quote("Thanks for your order!"))

    print("\n-- escaping user input --")
    user_name = "Rock*Star"
    print(bold(f"Welcome, {escape(user_name)}!"))

    print("\n-- stripping formatting for a log line --")
    print(strip_formatting("*Hello* _world_, this is ~old~ new"))

    print("\n-- truncating safely --")
    long_text = "x" * 4100
    print(f"truncated length: {len(truncate(long_text))}")  # 4096

    print("\n-- converting an LLM's Markdown reply --")
    llm_reply = (
        "# Order confirmed\n\n"
        "**Total:** $42.00\n\n"
        "See the [invoice](https://example.com/inv.pdf) for details.\n\n"
        "| Item | Qty |\n|---|---|\n| Widget | 3 |\n"
    )
    print(from_markdown(llm_reply))


if __name__ == "__main__":
    main()
