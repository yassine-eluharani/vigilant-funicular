"""SSE streaming routes — task logs and per-user event bus."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from applypilot.web.auth import verify_clerk_jwt, upsert_user
from applypilot.web.core import _tasks, _register_user_queue, _unregister_user_queue

router = APIRouter()

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
}


@router.get("/api/stream/task/{task_id}")
async def stream_task_logs(task_id: str, token: str | None = Query(None)):
    """SSE: stream log lines for a background task until completion.

    Auth is via ?token= query param because EventSource cannot send custom headers.
    Uses asyncio.Event for instant delivery instead of 250ms sleep polling.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    verify_clerk_jwt(token)  # raises 401 on invalid/expired token

    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    async def _generate():
        sent = 0
        loop = asyncio.get_running_loop()
        event = asyncio.Event()

        # Register event so the background thread can wake us up
        task = _tasks.get(task_id)
        if task:
            task["_loop"] = loop
            task["_event"] = event

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
            # Clean up references so GC can collect the event/loop
            task = _tasks.get(task_id)
            if task:
                task["_loop"] = None
                task["_event"] = None

    return StreamingResponse(_generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/api/stream/user/events")
async def stream_user_events(token: str | None = Query(None)):
    """SSE: per-user event bus — stats_changed, etc.

    Frontend connects once on mount and reacts to server-pushed events instead
    of polling /api/stats every N seconds.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_clerk_jwt(token)
    clerk_id: str = payload.get("sub", "")
    email: str | None = payload.get("email")
    name: str | None = payload.get("name") or payload.get("full_name")
    user = upsert_user(clerk_id, email, name)
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
