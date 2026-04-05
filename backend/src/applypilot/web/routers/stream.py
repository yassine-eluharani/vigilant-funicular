"""SSE streaming routes — task logs and apply worker state."""

from __future__ import annotations

import asyncio
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from applypilot.web.auth import get_current_user
from applypilot.web.core import _tasks

router = APIRouter(dependencies=[Depends(get_current_user)])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
}


@router.get("/api/stream/task/{task_id}")
async def stream_task_logs(task_id: str):
    """SSE: stream log lines for a background task until completion."""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    async def _generate():
        sent = 0
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
            await asyncio.sleep(0.25)

    return StreamingResponse(_generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/api/stream/apply")
async def stream_apply_status():
    """SSE: stream apply worker states every 500ms."""

    async def _generate():
        import dataclasses
        from applypilot.apply import dashboard as _dash

        while True:
            with _dash._lock:
                workers = [dataclasses.asdict(s) for s in _dash._worker_states.values()]
                events_raw = list(_dash._events)
            clean_events = [re.sub(r"\[.*?\]", "", e) for e in events_raw]
            payload = json.dumps({
                "workers": workers,
                "events": clean_events,
                "totals": _dash.get_totals(),
            })
            yield f"data: {payload}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(_generate(), media_type="text/event-stream", headers=_SSE_HEADERS)
