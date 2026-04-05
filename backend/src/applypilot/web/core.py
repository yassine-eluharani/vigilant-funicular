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
