"""Discovery run tracking helpers.

The discovery cycle (discover → enrich → filter → index) runs in the
separate applypilot-discovery worker. These helpers read/write the
shared discovery_runs table so the main platform can show sync status
and jobspy can track freshness.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

STALE_AFTER_HOURS: float = 2.0


def is_stale(query: str, location: str, boards: list[str]) -> bool:
    """Return True if this combo needs re-discovery."""
    from applypilot.database import get_connection
    conn = get_connection()
    boards_json = json.dumps(sorted(boards))
    row = conn.execute(
        "SELECT completed_at FROM discovery_runs "
        "WHERE query = ? AND location = ? AND boards_json = ? AND status = 'done' "
        "ORDER BY completed_at DESC LIMIT 1",
        (query, location, boards_json),
    ).fetchone()
    if not row or not row["completed_at"]:
        return True
    completed = datetime.fromisoformat(row["completed_at"])
    if completed.tzinfo is None:
        completed = completed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - completed > timedelta(hours=STALE_AFTER_HOURS)


def record_run_start(query: str, location: str, boards: list[str]) -> int:
    """Insert a discovery_runs row, return its id."""
    from applypilot.database import get_connection
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO discovery_runs (query, location, boards_json, started_at, status) "
        "VALUES (?, ?, ?, ?, 'running')",
        (query, location, json.dumps(sorted(boards)), now),
    )
    conn.commit()
    return cur.lastrowid


def record_run_done(run_id: int, jobs_found: int, status: str = "done") -> None:
    from applypilot.database import get_connection
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE discovery_runs SET completed_at = ?, status = ?, jobs_found = ? WHERE id = ?",
        (now, status, jobs_found, run_id),
    )
    conn.commit()


def last_sync_info() -> dict:
    """Return info about the most recent completed discovery run."""
    from applypilot.database import get_connection
    conn = get_connection()
    row = conn.execute(
        "SELECT completed_at, SUM(jobs_found) as total_found, COUNT(*) as combos "
        "FROM discovery_runs WHERE status = 'done' AND completed_at IS NOT NULL "
        "ORDER BY completed_at DESC LIMIT 1"
    ).fetchone()
    if not row or not row["completed_at"]:
        return {"last_sync": None, "jobs_found": 0}
    return {
        "last_sync": row["completed_at"],
        "jobs_found": row["total_found"] or 0,
    }
