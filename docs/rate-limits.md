# Rate limits

Every endpoint has its own budget, on a rolling 60-second window, per agent (manual p.28):

| Limit | Value | Scope |
|---|---|---|
| Outbound messages (`POST /messages`) | 12/min | Per agent |
| Read receipts and typing (`POST /statuses`) | 12/min | Per agent |
| Update polls (`GET /updates`) | 15/min | Per agent |
| Media requests (`POST`/`GET`/`DELETE /media`) | 12/min each | Per agent, per method |

Each method has its own counter — sending 12 messages in a minute doesn't touch your polling budget, and `POST /media`, `GET /media/<id>`, and `DELETE /media/<id>` each have their own independent 12/min counter rather than sharing one.

## How the client handles this

By default (`client_side_rate_limiting=True`), `WhatsAppAgentClient` tracks each counter locally and **blocks the calling thread** before a call that would exceed its budget, rather than firing a request the server will reject with a `429`. This matters most for a `listen()` loop: a tight polling loop with a short timeout can otherwise burn through the 15/min `GET /updates` budget on its own, with no sends or media activity involved at all.

If the server does return a `429` anyway (e.g. another process shares this agent's token), the client reads its `Retry-After` header and waits at least that long before the local counter allows another call against that endpoint — this takes priority over the local counter's own estimate.

Disable this if you're coordinating rate limits externally yourself (e.g. multiple processes sharing one token, budgeted by something outside this SDK):

```python
client = WhatsAppAgentClient(client_side_rate_limiting=False)
```

With it disabled, a `429` surfaces as `RateLimitError` (see [errors.md](errors.md)) instead of being waited out.

## Why a hard sliding window, not a smoothed rate

`whatsapp_agent.ratelimit.RateLimiter` implements exactly what the manual describes — a hard rolling-60-second counter per bucket — rather than an approximation like a token bucket with continuous refill. The manual's own wording ("Each method has its own counter over a rolling 60-second window, per agent," p.28) describes a counter, and matching that shape means the client's behavior is predictable against the server's, instead of merely close to it.
