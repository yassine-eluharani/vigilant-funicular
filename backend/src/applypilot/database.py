"""ApplyPilot database layer: schema, migrations, stats, and connection helpers.

Single source of truth for the jobs table schema. All columns from every
pipeline stage are created up front so any stage can run independently
without migration ordering issues.
"""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from applypilot.config import DB_PATH

# Thread-local connection storage — each thread gets its own connection
# (required for SQLite thread safety with parallel workers)
_local = threading.local()


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Get a thread-local cached DB connection.

    Supports:
      - Local SQLite (default, or DATABASE_URL is a file path)
      - Turso / libSQL  (DATABASE_URL=libsql://... + DATABASE_TOKEN=...)

    Args:
        db_path: Override the default DB_PATH. Useful for testing.
                 Ignored when DATABASE_URL points to a remote DB.

    Returns:
        Connection configured with WAL mode and row factory.
    """
    import os
    database_url = os.environ.get("DATABASE_URL", "")

    if database_url.startswith("libsql://") or database_url.startswith("wss://"):
        return _turso_connection(database_url, os.environ.get("DATABASE_TOKEN", ""))

    # Local SQLite
    path = str(db_path or DB_PATH)

    if not hasattr(_local, 'connections'):
        _local.connections = {}

    conn = _local.connections.get(path)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.ProgrammingError:
            pass

    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.row_factory = sqlite3.Row
    _local.connections[path] = conn
    return conn


def _turso_connection(url: str, token: str) -> sqlite3.Connection:
    """Return an HTTP-based Turso connection with sqlite3-compatible interface."""
    if not hasattr(_local, "turso_conn"):
        _local.turso_conn = _TursoConnection(url, token)
    return _local.turso_conn


class _TursoCursor:
    """Minimal sqlite3.Cursor-compatible wrapper over Turso HTTP responses."""

    def __init__(self, results: list, lastrowid: int | None = None):
        self._rows = results
        self.lastrowid = lastrowid
        self.description = None
        if results:
            # Build description from first row keys so sqlite3.Row-like access works
            first = results[0]
            if isinstance(first, dict):
                self.description = [(k, None, None, None, None, None, None) for k in first]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _TursoRow(dict):
    """dict subclass that supports both row["col"] and row[0] index access."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

    def keys(self):
        return super().keys()


class _TursoConnection:
    """sqlite3.Connection-compatible wrapper that talks to Turso over HTTPS."""

    def __init__(self, url: str, token: str):
        import httpx
        # Convert libsql:// → https://
        self._http_url = url.replace("libsql://", "https://") + "/v2/pipeline"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._client = httpx.Client(timeout=30)
        self.row_factory = None  # accepted but unused — rows always behave like sqlite3.Row

    def _execute_remote(self, sql: str, parameters: tuple = ()) -> _TursoCursor:
        args = [{"type": "integer" if isinstance(p, int) else
                          "float"   if isinstance(p, float) else
                          "null"    if p is None else "text",
                 "value": str(p) if p is not None else None}
                for p in parameters]

        payload = {
            "requests": [
                {"type": "execute", "stmt": {"sql": sql, "args": args}},
                {"type": "close"},
            ]
        }
        resp = self._client.post(self._http_url, json=payload, headers=self._headers)
        resp.raise_for_status()
        data = resp.json()

        result = data["results"][0]
        if result.get("type") == "error":
            raise sqlite3.OperationalError(result["error"]["message"])

        response = result.get("response", {})
        rows_data = response.get("result", {})
        cols = [c["name"] for c in rows_data.get("cols", [])]
        raw_rows = rows_data.get("rows", [])

        rows = []
        for raw in raw_rows:
            row = _TursoRow()
            for col, cell in zip(cols, raw):
                row[col] = cell.get("value") if cell.get("type") != "null" else None
            rows.append(row)

        # lastrowid from INSERT
        lastrowid = rows_data.get("last_insert_rowid")
        if lastrowid is not None:
            lastrowid = int(lastrowid)

        return _TursoCursor(rows, lastrowid)

    def execute(self, sql: str, parameters: tuple = ()) -> _TursoCursor:
        return self._execute_remote(sql, tuple(parameters))

    def commit(self) -> None:
        pass  # Turso auto-commits each statement

    def close(self) -> None:
        self._client.close()


def close_connection(db_path: Path | str | None = None) -> None:
    """Close the cached connection for the current thread."""
    path = str(db_path or DB_PATH)
    if hasattr(_local, 'connections'):
        conn = _local.connections.pop(path, None)
        if conn is not None:
            conn.close()


def init_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create the full jobs table with all columns from every pipeline stage.

    This is idempotent -- safe to call on every startup. Uses CREATE TABLE IF NOT EXISTS
    so it won't destroy existing data.

    Schema columns by stage:
      - Discovery:  url, title, salary, description, location, site, strategy, discovered_at
      - Enrichment: full_description, application_url, detail_scraped_at, detail_error
      - Scoring:    fit_score, score_reasoning, scored_at
      - Tailoring:  tailored_resume_path, tailored_at, tailor_attempts
      - Cover:      cover_letter_path, cover_letter_at, cover_attempts
      - Apply:      applied_at, apply_status, apply_error, apply_attempts,
                   agent_id, last_attempted_at, apply_duration_ms, apply_task_id,
                   verification_confidence

    Args:
        db_path: Override the default DB_PATH.

    Returns:
        sqlite3.Connection with the schema initialized.
    """
    path = db_path or DB_PATH

    # Ensure parent directory exists
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name     TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            last_login    TEXT,
            tier          TEXT DEFAULT 'free',
            tailors_used  INTEGER DEFAULT 0,
            covers_used   INTEGER DEFAULT 0,
            usage_reset_at TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS discovery_runs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            query        TEXT NOT NULL,
            location     TEXT NOT NULL,
            boards_json  TEXT NOT NULL,
            started_at   TEXT,
            completed_at TEXT,
            status       TEXT DEFAULT 'pending',
            jobs_found   INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            -- Discovery stage (smart_extract / job_search)
            url                   TEXT PRIMARY KEY,
            title                 TEXT,
            company               TEXT,
            salary                TEXT,
            description           TEXT,
            location              TEXT,
            site                  TEXT,
            strategy              TEXT,
            discovered_at         TEXT,

            -- Enrichment stage (detail_scraper)
            full_description      TEXT,
            application_url       TEXT,
            detail_scraped_at     TEXT,
            detail_error          TEXT,

            -- Filter stage (location filter)
            filtered_at           TEXT,

            -- Scoring stage (job_scorer)
            fit_score             INTEGER,
            score_reasoning       TEXT,
            scored_at             TEXT,

            -- Tailoring stage (resume tailor)
            tailored_resume_path  TEXT,
            tailored_at           TEXT,
            tailor_attempts       INTEGER DEFAULT 0,

            -- Cover letter stage
            cover_letter_path     TEXT,
            cover_letter_at       TEXT,
            cover_attempts        INTEGER DEFAULT 0,

            -- Application stage
            applied_at            TEXT,
            apply_status          TEXT,
            apply_error           TEXT,
            apply_attempts        INTEGER DEFAULT 0,
            agent_id              TEXT,
            last_attempted_at     TEXT,
            apply_duration_ms     INTEGER,
            apply_task_id         TEXT,
            verification_confidence TEXT
        )
    """)
    conn.commit()

    # Run migrations for any columns added after initial schema
    ensure_columns(conn)
    ensure_user_columns(conn)

    return conn


# Complete column registry: column_name -> SQL type with optional default.
# This is the single source of truth. Adding a column here is all that's needed
# for it to appear in both new databases and migrated ones.
_ALL_COLUMNS: dict[str, str] = {
    # Discovery
    "url": "TEXT PRIMARY KEY",
    "title": "TEXT",
    "company": "TEXT",
    "salary": "TEXT",
    "description": "TEXT",
    "location": "TEXT",
    "site": "TEXT",
    "strategy": "TEXT",
    "discovered_at": "TEXT",
    # Enrichment
    "full_description": "TEXT",
    "application_url": "TEXT",
    "detail_scraped_at": "TEXT",
    "detail_error": "TEXT",
    # Filter
    "filtered_at": "TEXT",
    # Scoring
    "fit_score": "INTEGER",
    "score_reasoning": "TEXT",
    "scored_at": "TEXT",
    # Tailoring
    "tailored_resume_path": "TEXT",
    "tailored_at": "TEXT",
    "tailor_attempts": "INTEGER DEFAULT 0",
    # Cover letter
    "cover_letter_path": "TEXT",
    "cover_letter_at": "TEXT",
    "cover_attempts": "INTEGER DEFAULT 0",
    # Application
    "applied_at": "TEXT",
    "apply_status": "TEXT",
    "apply_error": "TEXT",
    "apply_attempts": "INTEGER DEFAULT 0",
    "agent_id": "TEXT",
    "last_attempted_at": "TEXT",
    "apply_duration_ms": "INTEGER",
    "apply_task_id": "TEXT",
    "verification_confidence": "TEXT",
}


def ensure_columns(conn: sqlite3.Connection | None = None) -> list[str]:
    """Add any missing columns to the jobs table (forward migration).

    Reads the current table schema via PRAGMA table_info and compares against
    the full column registry. Any missing columns are added with ALTER TABLE.

    This makes it safe to upgrade the database from any previous version --
    columns are only added, never removed or renamed.

    Args:
        conn: Database connection. Uses get_connection() if None.

    Returns:
        List of column names that were added (empty if schema was already current).
    """
    if conn is None:
        conn = get_connection()

    existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    added = []

    for col, dtype in _ALL_COLUMNS.items():
        if col not in existing:
            # PRIMARY KEY columns can't be added via ALTER TABLE, but url
            # is always created with the table itself so this is safe
            if "PRIMARY KEY" in dtype:
                continue
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {dtype}")
            added.append(col)

    if added:
        conn.commit()

    return added


_USER_EXTRA_COLUMNS: dict[str, str] = {
    "tier": "TEXT DEFAULT 'free'",
    "tailors_used": "INTEGER DEFAULT 0",
    "covers_used": "INTEGER DEFAULT 0",
    "usage_reset_at": "TEXT",
    "searches_json": "TEXT",  # per-user search config (JSON), used by background scheduler
}


def ensure_user_columns(conn: sqlite3.Connection | None = None) -> None:
    """Add any missing tier/usage columns to the users table."""
    if conn is None:
        conn = get_connection()
    existing = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    for col, dtype in _USER_EXTRA_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {dtype}")
    conn.commit()


def get_stats(conn: sqlite3.Connection | None = None) -> dict:
    """Return job counts by pipeline stage.

    Provides a snapshot of how many jobs are at each stage, useful for
    dashboard display and pipeline progress tracking.

    Args:
        conn: Database connection. Uses get_connection() if None.

    Returns:
        Dictionary with keys:
            total, by_site, pending_detail, with_description,
            scored, unscored, tailored, untailored_eligible,
            with_cover_letter, applied, score_distribution
    """
    if conn is None:
        conn = get_connection()

    stats: dict = {}

    # Total jobs
    stats["total"] = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    # By site breakdown
    rows = conn.execute(
        "SELECT site, COUNT(*) as cnt FROM jobs GROUP BY site ORDER BY cnt DESC"
    ).fetchall()
    stats["by_site"] = [(row[0], row[1]) for row in rows]

    # Enrichment stage
    stats["pending_enrich"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE detail_scraped_at IS NULL"
    ).fetchone()[0]
    # keep old key for backwards compat
    stats["pending_detail"] = stats["pending_enrich"]

    stats["with_description"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL"
    ).fetchone()[0]

    stats["detail_errors"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE detail_error IS NOT NULL"
    ).fetchone()[0]

    # Filter stage
    stats["pending_filter"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE full_description IS NOT NULL "
        "AND filtered_at IS NULL "
        "AND (apply_status IS NULL OR apply_status = 'failed')"
    ).fetchone()[0]

    stats["location_filtered"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_status = 'location_filtered'"
    ).fetchone()[0]

    # Scoring stage
    stats["scored"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL"
    ).fetchone()[0]

    stats["unscored"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE full_description IS NOT NULL "
        "AND filtered_at IS NOT NULL "
        "AND fit_score IS NULL "
        "AND apply_status != 'location_filtered'"
    ).fetchone()[0]

    # Score distribution
    dist_rows = conn.execute(
        "SELECT fit_score, COUNT(*) as cnt FROM jobs "
        "WHERE fit_score IS NOT NULL "
        "GROUP BY fit_score ORDER BY fit_score DESC"
    ).fetchall()
    stats["score_distribution"] = [(row[0], row[1]) for row in dist_rows]

    # Tailoring stage
    stats["tailored"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL"
    ).fetchone()[0]

    stats["untailored_eligible"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE fit_score >= 7 AND full_description IS NOT NULL "
        "AND tailored_resume_path IS NULL "
        "AND (apply_status IS NULL OR apply_status NOT IN ('dismissed','location_filtered'))"
    ).fetchone()[0]

    stats["tailor_exhausted"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE COALESCE(tailor_attempts, 0) >= 5 "
        "AND tailored_resume_path IS NULL"
    ).fetchone()[0]

    # Cover letter stage
    stats["with_cover_letter"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE cover_letter_path IS NOT NULL"
    ).fetchone()[0]

    stats["cover_exhausted"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE COALESCE(cover_attempts, 0) >= 5 "
        "AND (cover_letter_path IS NULL OR cover_letter_path = '')"
    ).fetchone()[0]

    # Application stage
    stats["applied"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE applied_at IS NOT NULL"
    ).fetchone()[0]

    stats["apply_errors"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_error IS NOT NULL"
    ).fetchone()[0]

    stats["interviews"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_status = 'interview'"
    ).fetchone()[0]

    stats["offers"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_status = 'offer'"
    ).fetchone()[0]

    stats["rejected"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_status = 'rejected'"
    ).fetchone()[0]

    stats["ready_to_apply"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE tailored_resume_path IS NOT NULL "
        "AND (apply_status IS NULL OR apply_status NOT IN "
        "('applied','dismissed','interview','offer','rejected','in_progress','manual','location_filtered'))"
    ).fetchone()[0]

    return stats


def is_duplicate(conn: sqlite3.Connection, title: str | None,
                  company: str | None) -> bool:
    """Check if a job with the same normalized (title, company) already exists.

    Used to deduplicate the same role posted across multiple job boards.
    Only applies when both title and company are non-empty.
    """
    if not title or not company:
        return False
    row = conn.execute(
        "SELECT 1 FROM jobs WHERE LOWER(TRIM(title)) = LOWER(TRIM(?)) "
        "AND LOWER(TRIM(COALESCE(company, site))) = LOWER(TRIM(?)) LIMIT 1",
        (title, company),
    ).fetchone()
    return row is not None


def store_jobs(conn: sqlite3.Connection, jobs: list[dict],
               site: str, strategy: str) -> tuple[int, int]:
    """Store discovered jobs, skipping duplicates by URL or (title, company).

    Args:
        conn: Database connection.
        jobs: List of job dicts with keys: url, title, company, salary, description, location.
        site: Source site name (e.g. "RemoteOK", "Dice").
        strategy: Extraction strategy used (e.g. "json_ld", "api_response", "css_selectors").

    Returns:
        Tuple of (new_count, duplicate_count).
    """
    now = datetime.now(timezone.utc).isoformat()
    new = 0
    existing = 0

    for job in jobs:
        url = job.get("url")
        if not url:
            continue
        company = job.get("company") or site
        if is_duplicate(conn, job.get("title"), company):
            existing += 1
            continue
        try:
            conn.execute(
                "INSERT INTO jobs (url, title, company, salary, description, location, site, strategy, discovered_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (url, job.get("title"), company, job.get("salary"), job.get("description"),
                 job.get("location"), site, strategy, now),
            )
            new += 1
        except sqlite3.IntegrityError:
            existing += 1

    conn.commit()
    return new, existing


def get_jobs_by_stage(conn: sqlite3.Connection | None = None,
                      stage: str = "discovered",
                      min_score: int | None = None,
                      limit: int = 100) -> list[dict]:
    """Fetch jobs filtered by pipeline stage.

    Args:
        conn: Database connection. Uses get_connection() if None.
        stage: One of "discovered", "enriched", "scored", "tailored", "applied".
        min_score: Minimum fit_score filter (only relevant for scored+ stages).
        limit: Maximum number of rows to return.

    Returns:
        List of job dicts.
    """
    if conn is None:
        conn = get_connection()

    conditions = {
        "discovered": "1=1",
        "pending_detail": "detail_scraped_at IS NULL",
        "enriched": "full_description IS NOT NULL",
        "pending_score": "full_description IS NOT NULL AND fit_score IS NULL",
        "scored": "fit_score IS NOT NULL",
        "pending_tailor": (
            "fit_score >= ? AND full_description IS NOT NULL "
            "AND tailored_resume_path IS NULL AND COALESCE(tailor_attempts, 0) < 5"
        ),
        "tailored": "tailored_resume_path IS NOT NULL",
        "pending_apply": (
            "tailored_resume_path IS NOT NULL AND applied_at IS NULL "
            "AND application_url IS NOT NULL"
        ),
        "applied": "applied_at IS NOT NULL",
    }

    where = conditions.get(stage, "1=1")
    params: list = []

    if "?" in where and min_score is not None:
        params.append(min_score)
    elif "?" in where:
        params.append(7)  # default min_score

    if min_score is not None and "fit_score" not in where and stage in ("scored", "tailored", "applied"):
        where += " AND fit_score >= ?"
        params.append(min_score)

    query = f"SELECT * FROM jobs WHERE {where} ORDER BY fit_score DESC NULLS LAST, discovered_at DESC"
    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()

    # Convert sqlite3.Row objects to dicts
    if rows:
        columns = rows[0].keys()
        return [dict(zip(columns, row)) for row in rows]
    return []
