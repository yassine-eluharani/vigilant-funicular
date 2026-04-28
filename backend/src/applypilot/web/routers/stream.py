"""SSE streaming routes — task logs and per-user event bus."""

from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from applypilot.web.auth import verify_clerk_jwt, upsert_user
from applypilot.web.core import _tasks, _register_user_queue, _unregister_user_queue

router = APIRouter()

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
}


# BE-024: per-task fan-out registry. The previous design stored a single
# `_loop` + `_event` pair in the task entry, so a second SSE client on the
# same task_id silently overwrote the first one's wakeup channel — leaving
# the first client stuck on its 5s keep-alive cadence and never getting
# instant log delivery. Replaced with a per-task list of subscribers, each
# with their own (loop, event). The `_event` slot in the task dict is now a
# `_FanOut` object whose `.set()` walks the subscribers and signals each
# one's event on its own loop, which is what the background thread's
# `_signal()` in web/core.py invokes via `loop.call_soon_threadsafe(event.set)`.

_listeners_lock = threading.Lock()
_listeners: dict[str, list[tuple[asyncio.AbstractEventLoop, asyncio.Event]]] = {}


class _FanOut:
    """Stand-in for asyncio.Event placed in `_tasks[id]["_event"]`.

    Exposes only `.set()` because that's all `_run_task._signal` calls. When
    fired, it iterates the subscribed listeners and signals each on its own
    event loop (thread-safe via call_soon_threadsafe).
    """

    def __init__(self, task_id: str) -> None:
        self._task_id = task_id

    def set(self) -> None:
        with _listeners_lock:
            subs = list(_listeners.get(self._task_id, ()))
        for loop, ev in subs:
            if loop.is_closed():
                continue
            try:
                loop.call_soon_threadsafe(ev.set)
            except RuntimeError:
                # Loop may have shut down between our check and the call.
                pass


def _subscribe(task_id: str, loop: asyncio.AbstractEventLoop, event: asyncio.Event) -> None:
    with _listeners_lock:
        _listeners.setdefault(task_id, []).append((loop, event))
    # Ensure the task entry's `_event` slot is a fan-out, and that `_loop` is
    # set to *some* live loop so `_signal()` in core.py is willing to call it.
    # We pick this listener's loop arbitrarily; `_FanOut.set()` ignores it
    # and walks all subscribed loops, so any non-closed loop suffices.
    task = _tasks.get(task_id)
    if task is not None:
        if not isinstance(task.get("_event"), _FanOut):
            task["_event"] = _FanOut(task_id)
        task["_loop"] = loop


def _unsubscribe(task_id: str, loop: asyncio.AbstractEventLoop, event: asyncio.Event) -> None:
    with _listeners_lock:
        subs = _listeners.get(task_id)
        if not subs:
            return
        try:
            subs.remove((loop, event))
        except ValueError:
            pass
        if not subs:
            _listeners.pop(task_id, None)
            # Last listener gone — drop the fan-out reference so the task entry
            # can be GC'd cleanly when it's evicted from the TTLCache.
            task = _tasks.get(task_id)
            if task is not None and isinstance(task.get("_event"), _FanOut):
                task["_event"] = None
                task["_loop"] = None


@router.get("/api/stream/task/{task_id}")
async def stream_task_logs(task_id: str, token: str | None = Query(None)):
    """SSE: stream log lines for a background task until completion.

    Auth is via ?token= query param because EventSource cannot send custom headers.
    Uses asyncio.Event for instant delivery instead of 250ms sleep polling.
    Multiple clients on the same task_id are now supported (BE-024) — each gets
    their own wakeup event fanned out via `_FanOut`.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # BE-002: verify_clerk_jwt does sync httpx.get() to fetch JWKS — offload to
    # the threadpool so a slow Clerk doesn't pin the event loop on SSE connect.
    await asyncio.to_thread(verify_clerk_jwt, token)

    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    async def _generate():
        sent = 0
        loop = asyncio.get_running_loop()
        event = asyncio.Event()

        _subscribe(task_id, loop, event)

        try:
            while True:
                task = _tasks.get(task_id)
                if not task:
                    break
                lines = task.get("log_lines", [])
                for line in lines[sent:]:
                    safe = line.replace("\n", " ").replace("\r", "")
                    yield f"data: {safe}\n\n"
                    sent += 1
                status = task.get("status", "pending")
                if status in ("done", "error"):
                    yield f"event: status\ndata: {status}\n\n"
                    break
                # Block until background thread signals a new log line or timeout
                try:
                    await asyncio.wait_for(event.wait(), timeout=5.0)
                    event.clear()
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            _unsubscribe(task_id, loop, event)

    return StreamingResponse(_generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/api/stream/user/events")
async def stream_user_events(token: str | None = Query(None)):
    """SSE: per-user event bus — stats_changed, etc.

    Frontend connects once on mount and reacts to server-pushed events instead
    of polling /api/stats every N seconds.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # BE-002: both verify_clerk_jwt (sync httpx) and upsert_user (sync sqlite3 /
    # Turso HTTP) block the event loop. Offload them to the threadpool.
    payload = await asyncio.to_thread(verify_clerk_jwt, token)
    clerk_id: str = payload.get("sub", "")
    email: str | None = payload.get("email")
    name: str | None = payload.get("name") or payload.get("full_name")
    user = await asyncio.to_thread(upsert_user, clerk_id, email, name)
    user_id: int = user["id"]

    async def _generate():
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        _register_user_queue(user_id, q)
        try:
            while True:
                try:
                    item = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"event: {item['type']}\ndata: {item['payload']}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _unregister_user_queue(user_id, q)

    return StreamingResponse(_generate(), media_type="text/event-stream", headers=_SSE_HEADERS)
