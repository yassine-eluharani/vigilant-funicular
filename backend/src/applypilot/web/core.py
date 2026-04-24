"""Shared utilities for ApplyPilot API routers."""

from __future__ import annotations

import base64
import logging
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Background task registry (shared across routers)
# ---------------------------------------------------------------------------

_tasks: dict[str, dict[str, Any]] = {}
_MAX_LOG_LINES = 300


class _TaskLogHandler(logging.Handler):
    """Captures log records and appends them to a task's log_lines list."""

    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self._lines = lines
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._lines.append(self.format(record))
            if len(self._lines) > _MAX_LOG_LINES:
                self._lines.pop(0)
        except Exception:
            pass


def _run_task(task_id: str, fn, *args) -> None:
    log_lines: list[str] = _tasks[task_id]["log_lines"]
    handler = _TaskLogHandler(log_lines)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        _tasks[task_id]["status"] = "running"
        result = fn(*args)
        _tasks[task_id].update({"status": "done", "result": result})
    except Exception as exc:
        _tasks[task_id].update({"status": "error", "error": str(exc)})
    finally:
        root.removeHandler(handler)


def _start_task(fn, *args) -> str:
    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {"status": "pending", "result": None, "error": None, "log_lines": []}
    threading.Thread(target=_run_task, args=(task_id, fn, *args), daemon=True).start()
    return task_id


# ---------------------------------------------------------------------------
# Rate limiter — sliding window, in-memory per user
# ---------------------------------------------------------------------------

import time as _time
import collections as _collections


class RateLimiter:
    """Thread-safe sliding-window rate limiter.

    Usage:
        _limiter = RateLimiter(max_calls=5, window_seconds=60)

        @router.post("/api/...")
        def my_endpoint(user = Depends(get_current_user)):
            _limiter.check(user["id"])   # raises HTTP 429 if exceeded
    """

    def __init__(self, max_calls: int, window_seconds: int):
        self._max = max_calls
        self._window = window_seconds
        self._history: dict[int, _collections.deque] = {}
        self._lock = threading.Lock()

    def check(self, user_id: int) -> None:
        from fastapi import HTTPException
        now = _time.time()
        with self._lock:
            if user_id not in self._history:
                self._history[user_id] = _collections.deque()
            dq = self._history[user_id]
            cutoff = now - self._window
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self._max:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit: max {self._max} requests per {self._window}s. Try again shortly.",
                )
            dq.append(now)


# Shared limiters — applied to expensive LLM endpoints
tailor_limiter = RateLimiter(max_calls=5, window_seconds=60)
cover_limiter  = RateLimiter(max_calls=5, window_seconds=60)
score_limiter  = RateLimiter(max_calls=3, window_seconds=60)


# ---------------------------------------------------------------------------
# Auto-scoring helper
# ---------------------------------------------------------------------------

# Track the most recent score task per user so we don't double-start
_score_task_by_user: dict[int, str] = {}


def trigger_score_for_user(user_id: int) -> str | None:
    """Start a background scoring task for this user if one isn't already running.

    Returns the task_id if started (or already running), None if no unscored
    jobs exist for this user.
    """
    # Check if an active task exists for this user
    existing_id = _score_task_by_user.get(user_id)
    if existing_id:
        existing = _tasks.get(existing_id)
        if existing and existing.get("status") in ("pending", "running"):
            return existing_id

    # Check if the user has unscored jobs (filtered but not yet scored for them)
    from applypilot.database import get_connection
    conn = get_connection()
    unscored = conn.execute(
        "SELECT COUNT(*) FROM jobs j "
        "WHERE j.full_description IS NOT NULL "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM user_jobs uj "
        "  WHERE uj.job_url = j.url AND uj.user_id = ? AND uj.fit_score IS NOT NULL"
        ")",
        (user_id,),
    ).fetchone()[0]

    log.info("trigger_score_for_user: user_id=%s unscored=%s (type=%s)", user_id, unscored, type(unscored).__name__)
    if not unscored:
        return None

    def _score() -> dict:
        from applypilot.pipeline import run_pipeline
        return run_pipeline(stages=["score"], user_id=user_id)

    task_id = _start_task(_score)
    _score_task_by_user[user_id] = task_id
    log.info("Auto-scoring started for user %d (%d unscored jobs) → task %s",
             user_id, unscored, task_id)
    return task_id


# ---------------------------------------------------------------------------
# URL encoding helpers
# ---------------------------------------------------------------------------

def encode_url(url: str) -> str:
    return base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


def decode_url(encoded: str) -> str:
    try:
        padded = encoded + "=" * (4 - len(encoded) % 4)
        return base64.urlsafe_b64decode(padded.encode()).decode()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid encoded URL")


# ---------------------------------------------------------------------------
# DB row formatter
# ---------------------------------------------------------------------------

def row_to_job(row) -> dict:
    d = dict(row)
    for field in ("application_url", "location", "salary"):
        if d.get(field) in ("None", ""):
            d[field] = None
    path = d.get("tailored_resume_path") or ""
    if path:
        p = Path(path)
        d["has_pdf"] = p.with_suffix(".pdf").exists()
    else:
        d["has_pdf"] = False
    cover = d.get("cover_letter_path") or ""
    if cover:
        cp = Path(cover)
        d["has_cover_pdf"] = cp.with_suffix(".pdf").exists()
    else:
        d["has_cover_pdf"] = bool(cover)
    d["url_encoded"] = encode_url(d["url"]) if d.get("url") else ""
    return d
