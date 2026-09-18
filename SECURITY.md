# Security Policy

## Reporting a vulnerability

Please **do not** open a public GitHub issue for a security vulnerability. Instead, use GitHub's private [Security Advisories](https://github.com/abdullah3509/whatsapp-agent/security/advisories/new) reporting feature, or email the maintainer directly. Include:

- A description of the vulnerability and its impact.
- Steps to reproduce (a minimal script is ideal).
- The version of `whatsapp-agent` affected.

You should get an initial response within a few days. Please don't include a live `WHATSAPP_API_KEY` or any other real credential in a report.

## Handling your API token

A few things worth stating plainly, since this SDK's entire job is holding and using that token:

- `WhatsAppAgentClient` never logs, prints, or includes your API token in an exception message.
- The token is sent only as the `Authorization: Bearer` header to `api.whatsapp.com` (or whatever `base_url` you configure) — never anywhere else, and never in a query string or request body.
- Treat the token as you would any other bearer credential: don't commit `.env` (it's in `.gitignore`), don't paste it into an issue or a log aggregator, and regenerate it if you suspect it's leaked (WhatsApp → Settings → Agents → your agent → Chat info → API key).
- The MCP server (`whatsapp-agent mcp`) reads the token from the server process's own environment — it is never accepted as a tool argument, so it can't end up in an n8n execution log or a model's context window.

## Supported versions

Only the latest published release is actively supported with security fixes, consistent with this project's pre-1.0 status.
