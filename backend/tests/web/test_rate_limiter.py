"""Unit tests for ``applypilot.web.core.RateLimiter`` (TST-004).

These are pure unit tests — they don't import the FastAPI ``app`` or touch the
DB. We import only the ``RateLimiter`` class and exercise it directly.
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi import HTTPException

from applypilot.web.core import RateLimiter


# ---------------------------------------------------------------------------
# Window edge: fill to N, the (N+1)th call must raise 429.
# ---------------------------------------------------------------------------


def test_window_fill_raises_429() -> None:
    rl = RateLimiter(max_calls=3, window_seconds=60)
    # First three calls are allowed
    for _ in range(3):
        rl.check(user_id=1)
    # Fourth must be refused with HTTP 429
    with pytest.raises(HTTPException) as exc_info:
        rl.check(user_id=1)
    assert exc_info.value.status_code == 429
    assert "Rate limit" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Time advance past window: monkeypatch the clock and assert the window
# slides correctly.
# ---------------------------------------------------------------------------


def test_window_slides_after_time_advance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Once the sliding window expires, the limiter accepts new calls again."""
    rl = RateLimiter(max_calls=2, window_seconds=10)

    # Patch the monotonic clock used inside RateLimiter via the imported alias.
    fake_now = {"t": 1000.0}
    monkeypatch.setattr("applypilot.web.core._time.monotonic", lambda: fake_now["t"])

    # Two calls at t=1000 — both allowed
    rl.check(user_id=42)
    rl.check(user_id=42)

    # Third call at t=1000 must fail
    with pytest.raises(HTTPException):
        rl.check(user_id=42)

    # Advance 11s — window has fully passed, both old entries should be evicted
    fake_now["t"] = 1011.0
    rl.check(user_id=42)  # allowed
    rl.check(user_id=42)  # allowed

    # Third again — fails
    with pytest.raises(HTTPException):
        rl.check(user_id=42)


# ---------------------------------------------------------------------------
# Multi-user isolation: hitting the limit on user A doesn't affect user B.
# ---------------------------------------------------------------------------


def test_multi_user_isolation() -> None:
    rl = RateLimiter(max_calls=2, window_seconds=60)
    # Saturate user A
    rl.check(user_id=1)
    rl.check(user_id=1)
    with pytest.raises(HTTPException):
        rl.check(user_id=1)
    # User B is untouched — should still get its full quota
    rl.check(user_id=2)
    rl.check(user_id=2)
    with pytest.raises(HTTPException):
        rl.check(user_id=2)


# ---------------------------------------------------------------------------
# Threading sanity: 10 threads racing on the same user_id — exactly `max_calls`
# of them should succeed, the rest must raise.
# ---------------------------------------------------------------------------


def test_threading_concurrent_check() -> None:
    rl = RateLimiter(max_calls=4, window_seconds=60)
    user_id = 99
    successes: list[bool] = []
    failures: list[bool] = []
    lock = threading.Lock()

    barrier = threading.Barrier(10)

    def worker() -> None:
        # All threads start at roughly the same instant
        barrier.wait()
        try:
            rl.check(user_id=user_id)
        except HTTPException:
            with lock:
                failures.append(True)
        else:
            with lock:
                successes.append(True)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(successes) == 4, f"expected 4 successes, got {len(successes)}"
    assert len(failures) == 6, f"expected 6 failures, got {len(failures)}"


# ---------------------------------------------------------------------------
# Sleep-based time advance — sanity check that the deque-based eviction also
# works against the real clock (very short window so the test is fast).
# ---------------------------------------------------------------------------


def test_real_clock_window_slides() -> None:
    rl = RateLimiter(max_calls=1, window_seconds=1)
    rl.check(user_id=7)
    with pytest.raises(HTTPException):
        rl.check(user_id=7)
    time.sleep(1.1)
    rl.check(user_id=7)  # window expired — allowed again
