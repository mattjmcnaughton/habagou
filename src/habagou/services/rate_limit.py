"""Per-user fixed-window rate limiting for billed generation requests.

In-memory and per-process: this is deliberately the simplest thing that caps
per-user model spend on Habagou's single-machine deployment, where one uvicorn
process serves all traffic. A multi-process or multi-host deployment would need
a shared store (e.g. Redis) instead; that is out of scope here.

The limiter counts *every* authenticated attempt — :meth:`acquire` is called
before the model request, so a draft that later fails, or one rejected because
generation is unconfigured, still consumes quota. Counting on attempt (rather
than on a successful model call) is the safe choice for cost control: a caller
cannot burn provider budget by triggering repeated failures, and it keeps the
accounting trivial and deterministic.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class _Window:
    """A single key's live window: when it started and how many attempts it holds."""

    start: float
    count: int


class FixedWindowRateLimiter:
    """Per-key fixed-window attempt counter.

    Each key (a user id) gets an independent window of ``window_seconds``. The
    first attempt in a fresh or expired window resets the counter; once ``limit``
    attempts land inside a live window, further attempts are denied until the
    window expires.

    The clock is injected (``time.monotonic`` by default) so tests can drive
    window expiry deterministically without sleeping. ``time.monotonic`` is used
    rather than wall-clock time so the window is immune to system clock changes.
    """

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock
        self._windows: dict[str, _Window] = {}

    @property
    def enabled(self) -> bool:
        """Whether the cap is active. A non-positive ``limit`` disables it."""
        return self._limit > 0

    def acquire(self, key: str) -> bool:
        """Record an attempt for ``key``; return ``True`` if allowed.

        When disabled (``limit <= 0``) every call is allowed. On a fresh or
        expired window the counter resets to a single attempt. Within a live
        window the ``(limit + 1)``-th call returns ``False`` and does not
        advance the counter further, so a key stuck over the cap stays exactly
        at the limit until the window rolls over.
        """
        if not self.enabled:
            return True
        now = self._clock()
        window = self._windows.get(key)
        if window is None or now - window.start >= self._window_seconds:
            self._windows[key] = _Window(start=now, count=1)
            return True
        if window.count >= self._limit:
            return False
        window.count += 1
        return True
