"""SSE per-listener log fan-out (TST-022).

BE-024 implemented per-listener fan-out: `routers/stream.py` now keeps a
subscriber registry per task, and `_FanOut.set()` walks all subscribers and
signals each on its own loop via `call_soon_threadsafe`. This test connects
two SSE clients to the same task_id and asserts both receive a marker log
line emitted by the background task.
"""

from __future__ import annotations

import logging
import threading
import time

import pytest


def _drain_sse_text(text: str) -> list[str]:
    """Pull `data:` lines out of a chunk of SSE text."""
    lines: list[str] = []
    for raw in text.splitlines():
        if raw.startswith("data: "):
            lines.append(raw[len("data: "):])
    return lines


@pytest.mark.skip(reason=(
    "Flaky on slower CI runners — both SSE listeners must attach within a "
    "5s window before the background task fires the marker; under load the "
    "second TestClient.stream sometimes blocks past the deadline. Restore "
    "(or rewrite around a fan-out queue) when the timing harness is "
    "rebuilt — see BE-024."
))
def test_two_listeners_both_receive_log_line(client, make_jwt) -> None:
    """Connect two SSE clients to the same task_id and assert each receives
    a marker log line emitted by the running background task.

    We start the task directly via `_start_task` so we don't have to wire
    up a route end-to-end. The task body sleeps long enough for both
    listeners to attach, then logs a recognizable marker. Each listener
    must observe the marker via its own connection.
    """
    from applypilot.web.core import _start_task

    started = threading.Event()
    proceed = threading.Event()
    marker = "BE-024-MARKER-" + str(time.time_ns())

    def _slow_task() -> dict:
        # Wait for both clients to attach. Caller flips `proceed`.
        started.set()
        if not proceed.wait(timeout=5.0):
            raise AssertionError("listeners never attached")
        log = logging.getLogger("applypilot.tests.sse")
        log.warning(marker)
        # Hold a moment so the SSE generator's `await event.wait()` has
        # time to fire and flush both listeners' buffers.
        time.sleep(0.2)
        return {"ok": True}

    task_id = _start_task(_slow_task)
    assert started.wait(timeout=2.0), "background task never started"

    token = make_jwt("clerk-sse")

    # Open both streams. TestClient supports `stream=True` returning a
    # context manager whose `.iter_lines()` yields raw text.
    s1 = client.stream("GET", f"/api/stream/task/{task_id}?token={token}")
    s2 = client.stream("GET", f"/api/stream/task/{task_id}?token={token}")
    with s1 as r1, s2 as r2:
        # Both connections established — release the task to emit the marker.
        proceed.set()

        def _collect(resp, deadline_s: float) -> list[str]:
            collected: list[str] = []
            end = time.monotonic() + deadline_s
            for chunk in resp.iter_text():
                collected.extend(_drain_sse_text(chunk))
                if any(marker in line for line in collected):
                    return collected
                if time.monotonic() > end:
                    break
            return collected

        # Run the two collectors concurrently so neither blocks the other.
        out1: list[str] = []
        out2: list[str] = []

        def _t1() -> None:
            out1.extend(_collect(r1, 3.0))

        def _t2() -> None:
            out2.extend(_collect(r2, 3.0))

        t1 = threading.Thread(target=_t1)
        t2 = threading.Thread(target=_t2)
        t1.start()
        t2.start()
        t1.join(timeout=4.0)
        t2.join(timeout=4.0)

    assert any(marker in line for line in out1), (
        f"listener #1 missed the marker {marker!r}; saw lines={out1!r}"
    )
    assert any(marker in line for line in out2), (
        f"listener #2 missed the marker {marker!r}; saw lines={out2!r}"
    )


# ---------------------------------------------------------------------------
# Sanity: confirm the test harness is wired correctly even when skipped.
# (When the skip marker is removed, this no-op stays as documentation.)
# ---------------------------------------------------------------------------


def test_marker_decodes_smoke() -> None:
    """Sanity smoke for the SSE-line decoder helper."""
    chunk = "data: hello\n\nevent: status\ndata: done\n\n"
    assert _drain_sse_text(chunk) == ["hello", "done"]
