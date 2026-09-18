"""Client-side rate limiting.

Every endpoint has its own rolling 60-second budget, per agent (manual p.28):

======================================  =====  ==================
Endpoint                                Limit  Counter key
======================================  =====  ==================
``POST /messages``                      12/min ``messages``
``POST /statuses``                      12/min ``statuses``
``GET /updates``                        15/min ``updates``
``POST /media``                         12/min ``media_post``
``GET /media/<id>``                     12/min ``media_get``
``DELETE /media/<id>``                  12/min ``media_delete``
======================================  =====  ==================

A naive client (or a tight ``listen()`` loop) can burn through the ``updates``
budget on its own, and a burst of sends will trip ``messages`` immediately
once retries start stacking. :class:`RateLimiter` tracks each counter's
rolling window locally and blocks -- rather than firing a request the server
will just 429 -- when a call would exceed it.

This is deliberately a plain sliding-window counter, not a token bucket with
smoothing: the manual describes a hard rolling window ("Each method has its
own counter over a rolling 60-second window, per agent," p.28), so matching
that shape exactly is more predictable than an approximation.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

WINDOW_SECONDS = 60.0


class RateLimiter:
    """Tracks one rolling-60s counter per named bucket and blocks the calling
    thread until a new call is safely within budget.

    Thread-safe: a single client instance may be shared across threads (e.g.
    a `listen()` loop on one thread and sends from another), and each bucket
    has its own lock so unrelated endpoints never block each other.
    """

    def __init__(
        self, limits: dict[str, int], *, sleep: Callable[[float], None] | None = None
    ) -> None:
        self._limits = dict(limits)
        self._calls: dict[str, deque[float]] = {name: deque() for name in limits}
        self._locks: dict[str, threading.Lock] = {name: threading.Lock() for name in limits}
        self._sleep = sleep or time.sleep
        #: Wall-clock deadline (time.monotonic()) each bucket must not be
        #: used again before, set by :meth:`note_retry_after` from a 429's
        #: Retry-After header. Takes priority over the local counter.
        self._retry_after_until: dict[str, float] = {}

    def acquire(self, bucket: str) -> None:
        """Block, if necessary, until a call against ``bucket`` is within its
        rolling-60s budget. No-op for an unknown bucket name.
        """
        if bucket not in self._limits:
            return
        lock = self._locks[bucket]
        limit = self._limits[bucket]
        while True:
            with lock:
                now = time.monotonic()
                retry_until = self._retry_after_until.get(bucket)
                if retry_until is not None and retry_until > now:
                    wait = retry_until - now
                else:
                    calls = self._calls[bucket]
                    while calls and now - calls[0] >= WINDOW_SECONDS:
                        calls.popleft()
                    if len(calls) < limit:
                        calls.append(now)
                        return
                    wait = WINDOW_SECONDS - (now - calls[0])
            self._sleep(max(wait, 0.0))

    def note_retry_after(self, bucket: str, seconds: float) -> None:
        """Record a server-supplied ``Retry-After`` so the next
        :meth:`acquire` for ``bucket`` waits at least that long, even if the
        local counter thinks there's room. Called after a 429.
        """
        if bucket not in self._limits:
            return
        with self._locks[bucket]:
            until = time.monotonic() + max(seconds, 0.0)
            self._retry_after_until[bucket] = max(
                until, self._retry_after_until.get(bucket, 0.0)
            )
