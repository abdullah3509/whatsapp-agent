# Contributing

Thanks for considering a contribution to `whatsapp-agent`.

## Setup

```bash
git clone https://github.com/abdullah3509/whatsapp-agent.git
cd whatsapp-agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,mcp]"
pre-commit install   # optional, runs ruff/mypy on commit
```

## Running checks locally

```bash
ruff check src tests
mypy src
pytest --cov
```

All three run in CI on every PR (Python 3.9–3.13). Tests use the `responses` library to mock HTTP — no live `WHATSAPP_API_KEY` is needed to run the suite, and none should ever be required for a test to pass.

## Ground rules

- **Cite the manual.** This SDK's behavior tracks the WhatsApp Agent Platform developer manual closely — if you're changing a limit, an error mapping, or a retry rule, reference the manual section/page in a comment or the PR description, the way the existing code does.
- **New client behavior needs a test.** Especially anything touching offset tracking in `listen()`, rate limiting, or error-code mapping — these are exactly the places a subtle regression is easy to introduce and hard to notice.
- **Formatting/Markdown changes need a fixture.** `whatsapp_agent.formatting` and `whatsapp_agent.markdown` are tested against concrete before/after strings in `tests/test_formatting.py` and `tests/test_markdown.py` — add cases there rather than only asserting on new helper functions in isolation.
- **Don't break the public API silently.** `WhatsAppAgentClient`'s existing method signatures, and the base `WhatsAppAPIError` and its public attributes, are relied on by existing code (see `docs/migration.md`). If a change is unavoidably breaking, call it out explicitly in the PR and in `CHANGELOG.md`.
- **MCP tool docstrings are user-facing** — they're what the calling model reads to decide how to use a tool. Keep them accurate and specific if you touch `mcp/server.py`.

## Reporting a bug

Open an issue with: the method/tool called, the exception or output you got, and — if it's API-facing — the `error.code`/`fbtrace_id` from the response (never the API token itself).

## Security issues

Please don't open a public issue for a security vulnerability — see [SECURITY.md](SECURITY.md).
