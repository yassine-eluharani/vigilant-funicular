"""Shared utilities for ApplyPilot API routers."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
import uuid
from typing import Any

from fastapi import HTTPException

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Background task registry (shared across routers)
# ---------------------------------------------------------------------------

_tasks: dict[str, dict[str, Any]] = {}
_MAX_LOG_LINES = 300


class _TaskLogHandler(logging.Handler):
    """Captures log records, appends to task log_lines, and signals SSE waiters."""

    def __init__(self, lines: list[str], notify_fn=None) -> None:
        super().__init__()
        self._lines = lines
        self._notify = notify_fn  # callable() → signals asyncio.Event from thread-safe context
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
            if self._notify:
                self._notify()
        except Exception:
            pass


def _run_task(task_id: str, fn, *args) -> None:
    log_lines: list[str] = _tasks[task_id]["log_lines"]

    def _signal():
        """Signal the SSE event from the background thread safely."""
        entry = _tasks.get(task_id, {})
        loop = entry.get("_loop")
        event = entry.get("_event")
        if loop and event and not loop.is_closed():
            loop.call_soon_threadsafe(event.set)

    handler = _TaskLogHandler(log_lines, notify_fn=_signal)
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
        _signal()  # ensure SSE generator wakes up to emit the final status


def _start_task(fn, *args) -> str:
    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {
        "status": "pending",
        "result": None,
        "error": None,
        "log_lines": [],
        "_loop": None,   # set by SSE handler when a client connects
        "_event": None,  # asyncio.Event set by _signal() above
    }
    threading.Thread(target=_run_task, args=(task_id, fn, *args), daemon=True).start()
    return task_id


# ---------------------------------------------------------------------------
# Per-user SSE event bus (stats_changed, task_started, etc.)
# ---------------------------------------------------------------------------

# user_id → list of asyncio.Queue objects (one per active SSE connection)
_user_queues: dict[int, list[asyncio.Queue]] = {}
_user_queues_lock = threading.Lock()


def notify_user(user_id: int, event_type: str, data: dict | None = None) -> None:
    """Push an event to all SSE listeners for a user (thread-safe)."""
    with _user_queues_lock:
        queues = list(_user_queues.get(user_id, []))
    payload = json.dumps({"type": event_type, **(data or {})})
    for q in queues:
        try:
            q.put_nowait({"type": event_type, "payload": payload})
        except asyncio.QueueFull:
            pass  # slow consumer — drop the event rather than block


def _register_user_queue(user_id: int, q: asyncio.Queue) -> None:
    with _user_queues_lock:
        _user_queues.setdefault(user_id, []).append(q)


def _unregister_user_queue(user_id: int, q: asyncio.Queue) -> None:
    with _user_queues_lock:
        lst = _user_queues.get(user_id, [])
        try:
            lst.remove(q)
        except ValueError:
            pass


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
    # Text stored in DB — PDF is generated on-the-fly when requested
    d["has_pdf"] = bool(d.get("tailored_resume_text") or d.get("tailored_resume_path"))
    d["has_cover_pdf"] = bool(d.get("cover_letter_text") or d.get("cover_letter_path"))
    d["url_encoded"] = encode_url(d["url"]) if d.get("url") else ""
    return d
