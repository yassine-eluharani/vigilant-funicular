"""Apply worker routes — start, stop, status."""

from __future__ import annotations

import multiprocessing as _mp
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from applypilot.web.auth import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])

# Module-level process handle (one apply session at a time)
_apply_process: Optional[_mp.Process] = None


def _run_apply_workers(workers: int, limit: int, min_score: int,
                       headless: bool, continuous: bool, model: str) -> None:
    """Target for apply subprocess. Isolated so signal handlers don't conflict with FastAPI."""
    from applypilot.config import load_env, ensure_dirs
    from applypilot.database import init_db
    load_env()
    ensure_dirs()
    init_db()
    from applypilot.apply.launcher import apply_jobs
    apply_jobs(
        workers=workers,
        continuous=continuous,
        headless=headless,
        limit=limit if limit > 0 else None,
        min_score=min_score,
        model=model or None,
    )


@router.get("/api/apply/status")
def apply_status() -> JSONResponse:
    import dataclasses
    import re
    from applypilot.apply import dashboard as _dash

    with _dash._lock:
        workers = [dataclasses.asdict(s) for s in _dash._worker_states.values()]
        events_raw = list(_dash._events)

    clean_events = [re.sub(r"\[.*?\]", "", e) for e in events_raw]

    return JSONResponse({
        "running": _apply_process is not None and _apply_process.is_alive(),
        "workers": workers,
        "events": clean_events,
        "totals": _dash.get_totals(),
    })


@router.post("/api/apply/start")
async def start_apply(request: Request) -> JSONResponse:
    global _apply_process

    if _apply_process is not None and _apply_process.is_alive():
        return JSONResponse({"ok": False, "error": "Apply workers already running"}, status_code=409)

    body = await request.json()
    workers = int(body.get("workers", 1))
    limit = int(body.get("limit", 0))
    min_score = int(body.get("min_score", 7))
    headless = bool(body.get("headless", True))
    continuous = bool(body.get("continuous", False))
    model = str(body.get("model", ""))

    _apply_process = _mp.Process(
        target=_run_apply_workers,
        args=(workers, limit, min_score, headless, continuous, model),
        daemon=True,
    )
    _apply_process.start()
    return JSONResponse({"ok": True, "pid": _apply_process.pid})


@router.post("/api/apply/stop")
def stop_apply() -> JSONResponse:
    global _apply_process

    if _apply_process is None or not _apply_process.is_alive():
        return JSONResponse({"ok": False, "error": "No apply workers running"}, status_code=409)

    _apply_process.join(timeout=5)
    if _apply_process.is_alive():
        _apply_process.terminate()
    _apply_process = None
    return JSONResponse({"ok": True})
