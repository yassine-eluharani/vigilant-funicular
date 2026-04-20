"""Background discovery scheduler.

Runs a continuous loop (every REFRESH_INTERVAL_HOURS) that:
  1. Reads all users' search configs from the DB (searches_json column)
  2. Deduplicates query × location × boards combos across users
  3. For each combo not in discovery_runs within the last STALE_AFTER_HOURS hours,
     runs a real scrape and records it in discovery_runs

This means that when a user triggers the discover stage manually, most combos
already have fresh results — _full_crawl skips them and completes in seconds.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

REFRESH_INTERVAL_HOURS: float = 2.0
STALE_AFTER_HOURS: float = 2.0

# --------------------------------------------------------------------------- #
# Freshness helpers (also used by jobspy._full_crawl)                         #
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Config aggregation                                                           #
# --------------------------------------------------------------------------- #

def _all_user_configs() -> list[dict]:
    """Return search configs for all users who have one stored in the DB."""
    from applypilot.database import get_connection
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, searches_json FROM users WHERE searches_json IS NOT NULL"
    ).fetchall()
    configs = []
    for row in rows:
        try:
            cfg = json.loads(row["searches_json"])
            configs.append({"user_id": row["id"], "config": cfg})
        except Exception:
            pass
    return configs


def _unique_combos(configs: list[dict]) -> list[dict]:
    """Deduplicate query × location × boards across all user configs."""
    seen: set[tuple] = set()
    combos: list[dict] = []
    for entry in configs:
        cfg = entry["config"]
        queries = cfg.get("queries", [])
        locations = cfg.get("locations", [])
        boards = sorted(cfg.get("boards", ["indeed", "linkedin"]))
        defaults = cfg.get("defaults", {})

        for q in queries:
            query_str = q["query"] if isinstance(q, dict) else str(q)
            for loc in locations:
                loc_str = loc["location"] if isinstance(loc, dict) else str(loc)
                remote = loc.get("remote", False) if isinstance(loc, dict) else False
                key = (query_str.lower(), loc_str.lower(), tuple(boards))
                if key not in seen:
                    seen.add(key)
                    combos.append({
                        "query": query_str,
                        "location": loc_str,
                        "remote": remote,
                        "boards": boards,
                        "defaults": defaults,
                        "config": cfg,
                    })
    return combos


# --------------------------------------------------------------------------- #
# Discovery execution                                                          #
# --------------------------------------------------------------------------- #

def _discover_combo(combo: dict) -> None:
    """Run discovery for one (query, location, boards) combo and record it."""
    from applypilot.discovery.jobspy import _run_one_search, _load_location_config

    query = combo["query"]
    location = combo["location"]
    boards = combo["boards"]
    cfg = combo["config"]
    defaults = combo.get("defaults", {})

    run_id = record_run_start(query, location, boards)
    try:
        accept_locs, reject_locs = _load_location_config(cfg)
        result = _run_one_search(
            search={"query": query, "location": location, "remote": combo.get("remote", False), "tier": 0},
            sites=boards,
            results_per_site=defaults.get("results_per_site", 100),
            hours_old=defaults.get("hours_old", 72),
            proxy_config=None,
            defaults=defaults,
            max_retries=2,
            accept_locs=accept_locs,
            reject_locs=reject_locs,
            include_titles=cfg.get("include_title_any", []),
            exclude_titles=cfg.get("exclude_titles", []),
            glassdoor_map=cfg.get("glassdoor_location_map", {}),
        )
        new_jobs = result.get("new", 0)
        log.info("[scheduler] '%s' @ %s → %d new", query, location, new_jobs)
        record_run_done(run_id, new_jobs, "done")
    except Exception as e:
        log.error("[scheduler] '%s' @ %s failed: %s", query, location, e)
        record_run_done(run_id, 0, "error")


def run_cycle() -> None:
    """One full scheduler cycle: discover all stale combos across all users."""
    from applypilot.config import load_env, load_search_config
    from applypilot.database import init_db

    load_env()
    init_db()

    configs = _all_user_configs()

    # Fall back to shared searches.yaml if no per-user configs exist yet
    if not configs:
        shared = load_search_config()
        if shared:
            configs = [{"user_id": None, "config": shared}]

    if not configs:
        log.info("[scheduler] No search configs — skipping cycle")
        return

    combos = _unique_combos(configs)
    stale = [c for c in combos if is_stale(c["query"], c["location"], c["boards"])]

    log.info("[scheduler] %d unique combos, %d stale", len(combos), len(stale))

    for combo in stale:
        _discover_combo(combo)

    log.info("[scheduler] Cycle complete")


# --------------------------------------------------------------------------- #
# Scheduler thread                                                             #
# --------------------------------------------------------------------------- #

_scheduler_thread: threading.Thread | None = None


def start_scheduler(interval_hours: float = REFRESH_INTERVAL_HOURS) -> None:
    """Start the background discovery scheduler as a daemon thread."""
    global _scheduler_thread

    if _scheduler_thread and _scheduler_thread.is_alive():
        log.warning("[scheduler] Already running — skipping start")
        return

    def _loop() -> None:
        # Short startup delay so the server is fully up before first run
        time.sleep(15)
        while True:
            try:
                run_cycle()
            except Exception as e:
                log.error("[scheduler] Unhandled error in cycle: %s", e)
            time.sleep(interval_hours * 3600)

    _scheduler_thread = threading.Thread(target=_loop, daemon=True, name="discovery-scheduler")
    _scheduler_thread.start()
    log.info("[scheduler] Started — cycle every %.1fh", interval_hours)
