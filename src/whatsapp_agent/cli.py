"""Command-line entry point: ``whatsapp-agent``.

Subcommands:

- ``listen``  -- print inbound messages as they arrive (a debugging tool).
- ``send``    -- send one text message and exit.
- ``upload``  -- upload a local file and print its media id.
- ``mcp``     -- run the MCP server (stdio, or HTTP with ``--http``).
- ``doctor``  -- sanity-check that WHATSAPP_API_KEY is set and valid.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from .client import WhatsAppAgentClient
from .errors import WhatsAppAPIError


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="whatsapp-agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p_listen = sub.add_parser("listen", help="Print inbound messages as they arrive")
    p_listen.add_argument("--start", choices=["new", "all"], default="new")
    p_listen.add_argument("--mark-read", action="store_true", dest="mark_read")

    p_send = sub.add_parser("send", help="Send one text message")
    p_send.add_argument("to", help="Recipient, e.g. user:15551234567 or a bare phone number")
    p_send.add_argument("body", help="Message text")
    p_send.add_argument(
        "--markdown", action="store_true", help="Convert body from Markdown before sending"
    )

    p_upload = sub.add_parser("upload", help="Upload a local file, print its media id")
    p_upload.add_argument("file_path")
    p_upload.add_argument("--mime-type", dest="mime_type")

    p_mcp = sub.add_parser("mcp", help="Run the MCP server")
    p_mcp.add_argument(
        "--http", action="store_true", help="Serve streamable HTTP instead of stdio"
    )
    p_mcp.add_argument("--host", default="127.0.0.1")
    p_mcp.add_argument("--port", type=int, default=8765)

    sub.add_parser("doctor", help="Check that WHATSAPP_API_KEY is set and valid")

    args = parser.parse_args(argv)

    if args.command == "listen":
        return _cmd_listen(args)
    if args.command == "send":
        return _cmd_send(args)
    if args.command == "upload":
        return _cmd_upload(args)
    if args.command == "mcp":
        return _cmd_mcp(args)
    if args.command == "doctor":
        return _cmd_doctor()
    parser.error(f"unknown command {args.command!r}")
    return 2  # pragma: no cover -- argparse.error() exits before this


def _cmd_listen(args: argparse.Namespace) -> int:
    client = WhatsAppAgentClient()
    print("Listening for messages (Ctrl+C to stop)...", file=sys.stderr)
    try:
        for message in client.listen(start=args.start, auto_mark_read=args.mark_read):
            text = message.text if message.text is not None else f"[{message.type}]"
            print(f"{message.from_}: {text}")
    except KeyboardInterrupt:
        pass
    return 0


def _cmd_send(args: argparse.Namespace) -> int:
    client = WhatsAppAgentClient()
    body = args.body
    if args.markdown:
        from .markdown import from_markdown

        body = from_markdown(body)
    try:
        result = client.send_text(args.to, body)
    except WhatsAppAPIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _cmd_upload(args: argparse.Namespace) -> int:
    client = WhatsAppAgentClient()
    try:
        media_id = client.upload_media(args.file_path, mime_type=args.mime_type)
    except WhatsAppAPIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(media_id)
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    try:
        from .mcp import build_server
    except ImportError:
        print(
            "The MCP server requires the 'mcp' extra: pip install 'whatsapp-agent[mcp]'",
            file=sys.stderr,
        )
        return 1
    server = build_server()
    if args.http:
        server.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        server.run()
    return 0


def _cmd_doctor() -> int:
    try:
        client = WhatsAppAgentClient()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        # A cheap, harmless call: a 15-second poll for offset=0, limit=1,
        # timeout=0-ish just to confirm the token authenticates. We use a
        # timeout of 1s (the platform floors it at 0 and won't reject 1).
        client.get_updates(limit=1, timeout=1)
    except WhatsAppAPIError as exc:
        print(f"token rejected: {exc}", file=sys.stderr)
        return 1
    print("OK: WHATSAPP_API_KEY is set and accepted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
