# Errors

Every API error arrives in one envelope (manual p.24):

```json
{
  "error": {
    "message": "(#131009) Missing or malformed required fields",
    "type": "OAuthException",
    "code": 131009,
    "error_data": {"messaging_product": "whatsapp", "details": "..."},
    "fbtrace_id": "AW7bqWj4..."
  }
}
```

`error.type` is always `"OAuthException"`, including for errors that have nothing to do with authentication — it's not useful for branching. This SDK maps `error.code` to a dedicated exception class instead, all subclassing `WhatsAppAPIError`:

| Exception | `error.code` / HTTP | Meaning | What to do |
|---|---|---|---|
| `AuthenticationError` | 190/401, 100/400 | Missing/malformed `Authorization` header, or a token that's present but invalid | Regenerate the token (uninstalling the app invalidates it) |
| `RateLimitError` | 130429/429 | More requests than the endpoint's rolling-60s budget | Back off; `.retry_after` holds the server's `Retry-After` value if it sent one. The client already does this automatically for you — see [rate-limits.md](rate-limits.md) |
| `NotAcceptedError` | 131016/503 | Message not accepted for delivery | **Never sent** — always safe to retry after backing off. Retried automatically |
| `InvalidRequestError` | 131009/400 | Missing/malformed field, disallowed recipient, unknown/expired media id, or a length-cap violation | Fix the request — retrying unchanged fails the same way |
| `RecipientNotAllowedError` | 131005/403 | The recipient isn't the agent's creator, or the message being marked read wasn't sent by the creator | Verify `to`/`message_id` |
| `MediaError` | 131053/400, 100/404 | Upload exceeded its type's size limit, used an unaccepted MIME type, or referenced an unknown/expired media id | Re-encode/split the file, or re-request/re-upload |
| `PollConflictError` | 1752041/409 | A second concurrent poll for this agent replaced this one | Run exactly one `listen()`/`get_updates()` loop per agent — never retried automatically |
| `ServerError` | 2/500 | Internal server error | **Ambiguous** — the request may or may not have been acted on. Decide in advance whether a retry's possible duplicate is acceptable for your use case before retrying |

Every exception carries:

```python
exc.http_status   # int
exc.code          # int, the error.code value
exc.message       # str, human-readable summary (format not guaranteed -- branch on .code)
exc.details       # str | None, error_data.details when present
exc.fbtrace_id    # str | None, include this in support requests
```

```python
from whatsapp_agent import WhatsAppAgentClient, RateLimitError, NotAcceptedError

client = WhatsAppAgentClient()
try:
    client.send_text(to, body)
except NotAcceptedError:
    # never sent -- safe to just try again after a short wait
    time.sleep(2)
    client.send_text(to, body)
except RateLimitError as exc:
    time.sleep(exc.retry_after or 5)
    client.send_text(to, body)
```

In practice you'll rarely need to catch `RateLimitError` yourself — the client's built-in rate limiter (on by default) blocks *before* a call that would exceed the budget, so you only see this if it's disabled or another process shares the same token.

## Local validation errors

Some failures never reach the network: an empty/over-length text body, a caption over 1024 characters, or an `agent:<id>` passed as `to` all raise a plain `ValueError` immediately, since the API would reject them identically and there's no reason to spend a round trip finding that out.
