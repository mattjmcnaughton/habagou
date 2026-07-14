"""Unit tests for the fixed-window generation rate limiter (HAB-085)."""

from __future__ import annotations

from habagou.services.rate_limit import FixedWindowRateLimiter


class _FakeClock:
    """A manually advanced monotonic clock for deterministic window tests."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_limit_then_denies() -> None:
    clock = _FakeClock()
    limiter = FixedWindowRateLimiter(limit=2, window_seconds=60, clock=clock)

    assert limiter.acquire("user") is True
    assert limiter.acquire("user") is True
    # Third attempt inside the same window is over the cap.
    assert limiter.acquire("user") is False
    # Staying over the cap keeps denying, without advancing state.
    assert limiter.acquire("user") is False


def test_window_expiry_resets_the_counter() -> None:
    clock = _FakeClock()
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60, clock=clock)

    assert limiter.acquire("user") is True
    assert limiter.acquire("user") is False

    # Just before expiry the window is still live.
    clock.now = 59.9
    assert limiter.acquire("user") is False

    # At/after the window boundary a fresh window begins.
    clock.now = 60.0
    assert limiter.acquire("user") is True
    assert limiter.acquire("user") is False


def test_windows_are_isolated_per_key() -> None:
    clock = _FakeClock()
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60, clock=clock)

    assert limiter.acquire("alice") is True
    assert limiter.acquire("alice") is False
    # A different user has their own independent window.
    assert limiter.acquire("bob") is True
    assert limiter.acquire("bob") is False


def test_disabled_when_limit_is_zero_or_negative() -> None:
    for limit in (0, -1):
        limiter = FixedWindowRateLimiter(limit=limit, window_seconds=60)
        assert limiter.enabled is False
        # Disabled limiters never deny, no matter how many attempts.
        for _ in range(100):
            assert limiter.acquire("user") is True


def test_enabled_when_limit_is_positive() -> None:
    assert FixedWindowRateLimiter(limit=1, window_seconds=60).enabled is True


def test_defaults_to_monotonic_clock() -> None:
    # With the real clock and a generous window, the first calls are allowed and
    # the cap still bites — exercising the default clock path.
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=3600)
    assert limiter.acquire("user") is True
    assert limiter.acquire("user") is False


def test_expired_windows_are_pruned() -> None:
    # Stale keys must not accumulate for the life of the process.
    clock = _FakeClock()
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60, clock=clock)

    assert limiter.acquire("gone-user") is True
    clock.now = 61.0
    assert limiter.acquire("active-user") is True

    assert "gone-user" not in limiter._windows
    assert "active-user" in limiter._windows
