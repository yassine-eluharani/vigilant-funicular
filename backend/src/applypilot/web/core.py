"""Shared utilities for ApplyPilot API routers."""

from __future__ import annotations

import asyncio
import base64
import collections as _collections
import json
import logging
import threading
import time as _time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from cachetools import TTLCache
from fastapi import HTTPException

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Background task registry (shared across routers)
# ---------------------------------------------------------------------------
#
# BE-008 / TST-019: previously a plain dict that grew unbounded. Replaced with
# a TTLCache so completed task records age out automatically. SSE generator in
# routers/stream.py still accesses entries via `_tasks.get(task_id)` and `[]`
# — TTLCache supports both. If an entry expires mid-stream the generator's
# `task = _tasks.get(task_id); if not task: break` branch handles it gracefully
# (the loop exits after sending the final status, which it always does before
# the entry is eligible for eviction since the TTL is 1 day).

_tasks: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=1000, ttl=86400)
_tasks_lock = threading.Lock()

_MAX_LOG_LINES = 300

# BE-012: bound concurrent background tasks. ThreadPoolExecutor with 8 workers
# is plenty for tailor/cover/score jobs which are mostly I/O-bound on LLM
# round-trips. Submitted callables run on the executor's threads (non-daemon
# by default — they exit on interpreter shutdown via atexit).
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="task-")


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
    entry = _tasks.get(task_id)
    if entry is None:
        return  # entry was evicted before we even started — nothing to do
    log_lines: list[str] = entry["log_lines"]

    def _signal():
        """Signal the SSE event from the background thread safely."""
        entry = _tasks.get(task_id, {}) or {}
        loop = entry.get("_loop")
        event = entry.get("_event")
        if loop and event and not loop.is_closed():
            loop.call_soon_threadsafe(event.set)

    handler = _TaskLogHandler(log_lines, notify_fn=_signal)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        e = _tasks.get(task_id)
        if e is not None:
            e["status"] = "running"
        result = fn(*args)
        e = _tasks.get(task_id)
        if e is not None:
            e.update({"status": "done", "result": result})
    except Exception as exc:
        e = _tasks.get(task_id)
        if e is not None:
            e.update({"status": "error", "error": str(exc)})
    finally:
        root.removeHandler(handler)
        _signal()  # ensure SSE generator wakes up to emit the final status


def _start_task(fn, *args) -> str:
    task_id = str(uuid.uuid4())[:8]
    with _tasks_lock:
        _tasks[task_id] = {
            "status": "pending",
            "result": None,
            "error": None,
            "log_lines": [],
            "_loop": None,   # set by SSE handler when a client connects
            "_event": None,  # asyncio.Event set by _signal() above
        }
    # BE-012: submit to bounded pool instead of spawning unbounded threads.
    _executor.submit(_run_task, task_id, fn, *args)
    return task_id


# ---------------------------------------------------------------------------
# In-flight de-dup for keyed tasks (auto-tailor + manual click race)
# ---------------------------------------------------------------------------
#
# Modeled on `_score_task_by_user` below. Keyed lookup by tuple
# (kind, user_id, job_url) — if a task with that key is already pending or
# running, return its existing task_id instead of submitting a duplicate.
# Closes the race where the post-score auto-tailor enqueues a job at the same
# time the user clicks "Tailor" manually for the same job.

_inflight_task_by_key: TTLCache[tuple, str] = TTLCache(maxsize=10_000, ttl=3600)
_inflight_lock = threading.Lock()


def _start_task_unique(key: tuple, fn, *args) -> str:
    """Like `_start_task`, but de-dup by `key` so concurrent callers share one task.

    If a task with this key is currently pending or running, returns its
    existing task_id without dispatching a second LLM call. Otherwise starts
    a new task and records its id under the key.
    """
    with _inflight_lock:
        existing_id = _inflight_task_by_key.get(key)
        if existing_id:
            existing = _tasks.get(existing_id)
            if existing and existing.get("status") in ("pending", "running"):
                return existing_id
        task_id = _start_task(fn, *args)
        _inflight_task_by_key[key] = task_id
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
        now = _time.monotonic()
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
# Parse-CV is heavier than a tailor (large free-form text + JSON-mode LLM
# call), so use a tighter sliding window: 3 parses per 5 minutes per user.
parse_limiter  = RateLimiter(max_calls=3, window_seconds=300)


# ---------------------------------------------------------------------------
# Auto-scoring helper
# ---------------------------------------------------------------------------
#
# BE-008: per-user score-task pointer was a plain dict; replaced with a TTLCache
# that bounds memory and naturally forgets stale pointers after an hour.
# BE-006: existing-task lookup + _start_task + assignment now happens under a
# single lock so two concurrent /api/pipeline/maybe-score calls can't both
# pass the existence check and start duplicate jobs.

_score_task_by_user: TTLCache[int, str] = TTLCache(maxsize=10_000, ttl=3600)
_score_task_lock = threading.Lock()


def trigger_score_for_user(user_id: int) -> str | None:
    """Start a background scoring task for this user if one isn't already running.

    Returns the task_id if started (or already running), None if no unscored
    jobs exist for this user.
    """
    # BE-006: hold the lock across the existence check + _start_task + dict
    # assignment so concurrent callers see a consistent view.
    with _score_task_lock:
        existing_id = _score_task_by_user.get(user_id)
        if existing_id:
            existing = _tasks.get(existing_id)
            if existing and existing.get("status") in ("pending", "running"):
                return existing_id

        # Check if the user has unscored jobs (filtered but not yet scored for them).
        # DB read is inside the lock — that's a brief synchronous query, and
        # serializing it across concurrent maybe-score calls for the same user
        # is the whole point of BE-006.
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

        log.info("trigger_score_for_user: user_id=%s unscored=%s (type=%s)",
                 user_id, unscored, type(unscored).__name__)
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
# Startup hook for orphan task cleanup (TST-015)
# ---------------------------------------------------------------------------


def mark_orphan_tasks_on_startup() -> None:
    """Mark any in-flight tasks orphaned by a server restart as errored.

    TST-015: when the backend restarts, the in-memory `_tasks` registry is
    wiped. Any tailor/cover/score that was running at the time is lost — but
    the user's monthly counter has already been debited, leaving them with no
    artifact to show for it.

    This hook runs at app startup. Right now tasks aren't persisted to the DB,
    so there's nothing to mark — this is a no-op. The hook exists so a future
    change can plug in real persistence (e.g. a `tasks` table with a
    `status='running'` row per in-flight job) without needing to rewire the
    lifespan handler.

    TODO(TST-015): persist tasks to a DB table so this method can flip orphans
    to `error: "Server restarted before task completed; please retry"` and
    optionally credit the user's counter back. The frontend already handles
    "task gone, please retry" gracefully (404 from /api/stream/task/{id}).
    """
    # No-op for now — see docstring.
    log.debug("mark_orphan_tasks_on_startup: no persisted tasks (in-memory only)")


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
