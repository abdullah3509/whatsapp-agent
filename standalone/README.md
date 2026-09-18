# Standalone client

`whatsapp_agent.py` in this folder is a single, dependency-light file (`requests` + `python-dotenv`, nothing else) for projects that want to send/receive WhatsApp messages without installing the full `whatsapp-agent` package.

**Usage:** copy `whatsapp_agent.py` into your own project's source directory — do not `pip install` anything from this folder. Its filename is deliberate: once copied, `from whatsapp_agent import WhatsAppAgentClient` in your code is the exact same import you'd write after `pip install whatsapp-agent`, so switching to the full package later needs no code changes, just a deleted file and a pip install.

See the main [README](../README.md#two-ways-to-use-this) for when to reach for this versus the full package, and [`docs/migration.md`](../docs/migration.md) for the two correctness fixes this file carries relative to the original prototype.
