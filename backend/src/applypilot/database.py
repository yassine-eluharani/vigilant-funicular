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

# Once-per-process init guard — prevents re-running schema checks on every request
_db_initialized = False
_db_init_lock = threading.Lock()


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

    def __init__(self, results: list, lastrowid: int | None = None, rowcount: int = -1):
        self._rows = results
        self.lastrowid = lastrowid
        self.rowcount = rowcount
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
                type_ = cell.get("type")
                val = cell.get("value")
                if type_ == "null" or val is None:
                    row[col] = None
                elif type_ == "integer":
                    row[col] = int(val)
                elif type_ == "float":
                    row[col] = float(val)
                else:
                    row[col] = val
            rows.append(row)

        # lastrowid from INSERT
        lastrowid = rows_data.get("last_insert_rowid")
        if lastrowid is not None:
            lastrowid = int(lastrowid)

        # affected_row_count from UPDATE/DELETE/INSERT
        affected = rows_data.get("affected_row_count")
        rowcount = int(affected) if affected is not None else len(rows)

        return _TursoCursor(rows, lastrowid, rowcount)

    def execute(self, sql: str, parameters: tuple = ()) -> _TursoCursor:
        return self._execute_remote(sql, tuple(parameters))

    def execute_batch(self, statements: list[tuple[str, tuple]], chunk_size: int = 100) -> None:
        """Execute multiple write statements in a single HTTP round trip per chunk.

        Args:
            statements: List of (sql, params) tuples to execute sequentially.
            chunk_size: Max statements per HTTP request (default 100).
        """
        if not statements:
            return
        for i in range(0, len(statements), chunk_size):
            chunk = statements[i : i + chunk_size]
            requests = []
            for sql, params in chunk:
                args = [
                    {
                        "type": (
                            "integer" if isinstance(p, int) else
                            "float"   if isinstance(p, float) else
                            "null"    if p is None else "text"
                        ),
                        "value": str(p) if p is not None else None,
                    }
                    for p in params
                ]
                requests.append({"type": "execute", "stmt": {"sql": sql, "args": args}})
            requests.append({"type": "close"})
            resp = self._client.post(self._http_url, json={"requests": requests}, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()
            for result in data["results"][:-1]:  # skip the "close" result
                if result.get("type") == "error":
                    raise sqlite3.OperationalError(result["error"]["message"])

    def execute_pipeline(self, statements: list[tuple[str, tuple]]) -> list["_TursoCursor"]:
        """Execute multiple SQL statements in a single HTTP round trip, returning all results.

        Unlike execute_batch (write-only), this parses and returns a _TursoCursor for each
        statement — suitable for batching SELECT/COUNT queries.
        """
        if not statements:
            return []
        requests = []
        for sql, params in statements:
            args = [
                {
                    "type": (
                        "integer" if isinstance(p, int) else
                        "float"   if isinstance(p, float) else
                        "null"    if p is None else "text"
                    ),
                    "value": str(p) if p is not None else None,
                }
                for p in params
            ]
            requests.append({"type": "execute", "stmt": {"sql": sql, "args": args}})
        requests.append({"type": "close"})
        resp = self._client.post(self._http_url, json={"requests": requests}, headers=self._headers)
        resp.raise_for_status()
        data = resp.json()
        cursors = []
        for result in data["results"][:-1]:  # skip "close"
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
                    type_ = cell.get("type")
                    val = cell.get("value")
                    if type_ == "null" or val is None:
                        row[col] = None
                    elif type_ == "integer":
                        row[col] = int(val)
                    elif type_ == "float":
                        row[col] = float(val)
                    else:
                        row[col] = val
                rows.append(row)
            lastrowid = rows_data.get("last_insert_rowid")
            if lastrowid is not None:
                lastrowid = int(lastrowid)
            affected = rows_data.get("affected_row_count")
            rowcount = int(affected) if affected is not None else len(rows)
            cursors.append(_TursoCursor(rows, lastrowid, rowcount))
        return cursors

    def commit(self) -> None:
        pass  # Turso auto-commits each statement

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False  # never suppress exceptions


def close_connection(db_path: Path | str | None = None) -> None:
    """Close the cached connection for the current thread."""
    path = str(db_path or DB_PATH)
    if hasattr(_local, 'connections'):
        conn = _local.connections.pop(path, None)
        if conn is not None:
            conn.close()


def batch_query(conn: sqlite3.Connection, statements: list[tuple[str, tuple]]) -> list:
    """Execute multiple SELECT/COUNT queries in the fewest possible round trips.

    On Turso: sends all statements in a single HTTP POST via execute_pipeline().
    On local SQLite: executes sequentially (no HTTP overhead).

    Returns a list of cursors in the same order as statements.
    """
    if isinstance(conn, _TursoConnection):
        return conn.execute_pipeline(statements)
    return [conn.execute(sql, params) for sql, params in statements]


def init_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create all tables with full schema. Runs once per process — subsequent calls are no-ops."""
    global _db_initialized
    path = db_path or DB_PATH
    conn = get_connection(path)

    if _db_initialized:
        return conn

    with _db_init_lock:
        if _db_initialized:
            return conn

        # Ensure parent directory exists
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                clerk_id      TEXT UNIQUE,
                email         TEXT UNIQUE NOT NULL,
                full_name     TEXT NOT NULL,
                created_at    TEXT NOT NULL,
                last_login    TEXT,
                tier                 TEXT DEFAULT 'free',
                tailors_used         INTEGER DEFAULT 0,
                covers_used          INTEGER DEFAULT 0,
                usage_reset_at       TEXT,
                searches_json        TEXT,
                profile_json         TEXT,
                resume_text          TEXT,
                email_notifications  INTEGER DEFAULT 0
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
                -- Discovery stage
                url                   TEXT PRIMARY KEY,
                title                 TEXT,
                company               TEXT,
                salary                TEXT,
                description           TEXT,
                location              TEXT,
                site                  TEXT,
                strategy              TEXT,
                discovered_at         TEXT,

                -- Enrichment stage
                full_description      TEXT,
                application_url       TEXT,
                detail_scraped_at     TEXT,
                detail_error          TEXT,

                -- Filter stage (global — location restriction is a fact about the job)
                filtered_at           TEXT,

                -- Phase 3: structured metadata extracted once per job
                job_metadata_json     TEXT,

                -- Legacy per-user columns (kept for backward compat, new writes go to user_jobs)
                fit_score             INTEGER,
                score_reasoning       TEXT,
                scored_at             TEXT,
                tailored_resume_path  TEXT,
                tailored_at           TEXT,
                tailor_attempts       INTEGER DEFAULT 0,
                cover_letter_path     TEXT,
                cover_letter_at       TEXT,
                cover_attempts        INTEGER DEFAULT 0,
                favorited             INTEGER DEFAULT 0,
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

        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_jobs (
                user_id               INTEGER NOT NULL,
                job_url               TEXT NOT NULL,
                fit_score             INTEGER,
                score_reasoning       TEXT,
                scored_at             TEXT,
                tailored_resume_path  TEXT,
                tailored_resume_text  TEXT,
                tailored_at           TEXT,
                tailor_attempts       INTEGER DEFAULT 0,
                cover_letter_path     TEXT,
                cover_letter_text     TEXT,
                cover_letter_at       TEXT,
                cover_attempts        INTEGER DEFAULT 0,
                apply_status          TEXT,
                applied_at            TEXT,
                apply_error           TEXT,
                favorited             INTEGER DEFAULT 0,
                dismissed_at          TEXT,
                notes                 TEXT,
                PRIMARY KEY (user_id, job_url),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (job_url) REFERENCES jobs(url)
            )
        """)
        conn.commit()

        # Run migrations for any columns added after initial schema
        ensure_columns(conn)
        ensure_user_columns(conn)

        _db_initialized = True

    return conn


# Complete column registry for the jobs table.
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
    # Phase 3 metadata
    "job_metadata_json": "TEXT",
    # Legacy per-user (kept for migration)
    "fit_score": "INTEGER",
    "score_reasoning": "TEXT",
    "scored_at": "TEXT",
    "tailored_resume_path": "TEXT",
    "tailored_at": "TEXT",
    "tailor_attempts": "INTEGER DEFAULT 0",
    "cover_letter_path": "TEXT",
    "cover_letter_at": "TEXT",
    "cover_attempts": "INTEGER DEFAULT 0",
    "favorited": "INTEGER DEFAULT 0",
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
    """Add any missing columns to the jobs table (forward migration)."""
    if conn is None:
        conn = get_connection()

    existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    added = []

    for col, dtype in _ALL_COLUMNS.items():
        if col not in existing:
            if "PRIMARY KEY" in dtype:
                continue
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {dtype}")
            added.append(col)

    if added:
        conn.commit()

    return added


_USER_EXTRA_COLUMNS: dict[str, str] = {
    "clerk_id": "TEXT",  # UNIQUE enforced via index
    "tier": "TEXT DEFAULT 'free'",
    "tailors_used": "INTEGER DEFAULT 0",
    "covers_used": "INTEGER DEFAULT 0",
    "usage_reset_at": "TEXT",
    "searches_json": "TEXT",
    "profile_json": "TEXT",
    "resume_text": "TEXT",
    "email_notifications": "INTEGER DEFAULT 0",
}

_USER_JOBS_COLUMNS: dict[str, str] = {
    "fit_score": "INTEGER",
    "score_reasoning": "TEXT",
    "scored_at": "TEXT",
    "tailored_resume_path": "TEXT",
    "tailored_resume_text": "TEXT",
    "tailored_at": "TEXT",
    "tailor_attempts": "INTEGER DEFAULT 0",
    "cover_letter_path": "TEXT",
    "cover_letter_text": "TEXT",
    "cover_letter_at": "TEXT",
    "cover_attempts": "INTEGER DEFAULT 0",
    "apply_status": "TEXT",
    "applied_at": "TEXT",
    "apply_error": "TEXT",
    "favorited": "INTEGER DEFAULT 0",
    "dismissed_at": "TEXT",
    "notes": "TEXT",
}


def ensure_user_columns(conn: sqlite3.Connection | None = None) -> None:
    """Add any missing columns to users and user_jobs tables."""
    if conn is None:
        conn = get_connection()
    existing = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    for col, dtype in _USER_EXTRA_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {dtype}")
    conn.commit()
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_clerk_id ON users(clerk_id)"
    )

    # Ensure user_jobs table exists and has all columns
    try:
        uj_existing = {row[1] for row in conn.execute("PRAGMA table_info(user_jobs)").fetchall()}
        for col, dtype in _USER_JOBS_COLUMNS.items():
            if col not in uj_existing:
                conn.execute(f"ALTER TABLE user_jobs ADD COLUMN {col} {dtype}")
        conn.commit()
    except Exception:
        pass  # Table might not exist yet — init_db() creates it


# ---------------------------------------------------------------------------
# user_jobs helpers
# ---------------------------------------------------------------------------

def get_user_job(conn: sqlite3.Connection, user_id: int, job_url: str) -> dict | None:
    """Fetch a single user_jobs row as a dict, or None if not found."""
    row = conn.execute(
        "SELECT * FROM user_jobs WHERE user_id = ? AND job_url = ?",
        (user_id, job_url),
    ).fetchone()
    return dict(row) if row else None


def upsert_user_job(conn: sqlite3.Connection, user_id: int, job_url: str, **fields) -> None:
    """Insert or update a user_jobs row with the given fields."""
    if not fields:
        # Ensure the row exists with defaults
        conn.execute(
            "INSERT OR IGNORE INTO user_jobs (user_id, job_url) VALUES (?, ?)",
            (user_id, job_url),
        )
        conn.commit()
        return

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values())

    conn.execute(
        "INSERT OR IGNORE INTO user_jobs (user_id, job_url) VALUES (?, ?)",
        (user_id, job_url),
    )
    conn.execute(
        f"UPDATE user_jobs SET {set_clause} WHERE user_id = ? AND job_url = ?",
        values + [user_id, job_url],
    )
    conn.commit()


def batch_upsert_scores(
    conn: sqlite3.Connection,
    user_id: int,
    results: list[dict],
    now: str,
) -> None:
    """Write fit scores for multiple jobs efficiently.

    On Turso: all upserts are sent in chunked batch HTTP calls.
    On local SQLite: falls back to sequential upsert (no HTTP overhead anyway).

    Args:
        conn: Active DB connection.
        user_id: The user these scores belong to.
        results: List of dicts with keys: url, score, keywords, reasoning.
        now: ISO timestamp string for scored_at.
    """
    if isinstance(conn, _TursoConnection):
        stmts: list[tuple[str, tuple]] = []
        for r in results:
            stmts.append((
                "INSERT OR IGNORE INTO user_jobs (user_id, job_url) VALUES (?, ?)",
                (user_id, r["url"]),
            ))
            stmts.append((
                "UPDATE user_jobs SET fit_score = ?, score_reasoning = ?, scored_at = ? "
                "WHERE user_id = ? AND job_url = ?",
                (r["score"], f"{r['keywords']}\n{r['reasoning']}", now, user_id, r["url"]),
            ))
        conn.execute_batch(stmts)
    else:
        for r in results:
            upsert_user_job(
                conn, user_id, r["url"],
                fit_score=r["score"],
                score_reasoning=f"{r['keywords']}\n{r['reasoning']}",
                scored_at=now,
            )


def migrate_to_user_jobs(conn: sqlite3.Connection | None = None, user_id: int = 1) -> int:
    """One-time migration: copy per-user columns from jobs → user_jobs for a given user.

    Safe to run multiple times — uses INSERT OR IGNORE so existing rows are preserved.
    Returns the number of rows migrated.
    """
    if conn is None:
        conn = get_connection()

    rows = conn.execute("""
        SELECT url, fit_score, score_reasoning, scored_at,
               tailored_resume_path, tailored_at, tailor_attempts,
               cover_letter_path, cover_letter_at, cover_attempts,
               apply_status, applied_at, apply_error,
               COALESCE(favorited, 0) as favorited
        FROM jobs
        WHERE fit_score IS NOT NULL
           OR tailored_resume_path IS NOT NULL
           OR cover_letter_path IS NOT NULL
           OR apply_status IS NOT NULL
    """).fetchall()

    migrated = 0
    for row in rows:
        conn.execute(
            "INSERT OR IGNORE INTO user_jobs "
            "(user_id, job_url, fit_score, score_reasoning, scored_at, "
            " tailored_resume_path, tailored_at, tailor_attempts, "
            " cover_letter_path, cover_letter_at, cover_attempts, "
            " apply_status, applied_at, apply_error, favorited) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, row[0], row[1], row[2], row[3],
             row[4], row[5], row[6], row[7], row[8], row[9],
             row[10], row[11], row[12], row[13]),
        )
        migrated += 1
    conn.commit()
    return migrated


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_stats(conn: sqlite3.Connection | None = None, user_id: int | None = None) -> dict:
    """Return job counts by pipeline stage.

    All queries are sent to Turso in a single HTTP call via batch_query().

    Args:
        conn: Database connection. Uses get_connection() if None.
        user_id: When provided, user-specific stats are scoped via user_jobs.
                 When None, falls back to the legacy jobs-table columns.
    """
    if conn is None:
        conn = get_connection()

    if user_id is not None:
        u = user_id
        uj = "FROM user_jobs WHERE user_id = ?"
        statements: list[tuple[str, tuple]] = [
            # 0: total
            ("SELECT COUNT(*) FROM jobs", ()),
            # 1: by_site
            ("SELECT site, COUNT(*) as cnt FROM jobs GROUP BY site ORDER BY cnt DESC", ()),
            # 2: pending_enrich
            ("SELECT COUNT(*) FROM jobs WHERE detail_scraped_at IS NULL", ()),
            # 3: with_description
            ("SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL", ()),
            # 4: detail_errors
            ("SELECT COUNT(*) FROM jobs WHERE detail_error IS NOT NULL", ()),
            # 5: pending_filter
            (
                "SELECT COUNT(*) FROM jobs j "
                "WHERE j.full_description IS NOT NULL AND j.filtered_at IS NULL "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM user_jobs uj WHERE uj.job_url = j.url AND uj.user_id = ? "
                "  AND uj.apply_status = 'location_filtered')",
                (u,),
            ),
            # 6: location_filtered
            (f"SELECT COUNT(*) {uj} AND apply_status = 'location_filtered'", (u,)),
            # 7: scored
            (f"SELECT COUNT(*) {uj} AND fit_score IS NOT NULL", (u,)),
            # 8: unscored
            (
                "SELECT COUNT(*) FROM jobs j "
                "WHERE j.full_description IS NOT NULL AND j.filtered_at IS NOT NULL "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM user_jobs uj WHERE uj.job_url = j.url AND uj.user_id = ? AND uj.fit_score IS NOT NULL) "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM user_jobs uj WHERE uj.job_url = j.url AND uj.user_id = ? AND uj.apply_status = 'location_filtered')",
                (u, u),
            ),
            # 9: score_distribution
            (
                f"SELECT fit_score, COUNT(*) as cnt {uj} AND fit_score IS NOT NULL "
                "GROUP BY fit_score ORDER BY fit_score DESC",
                (u,),
            ),
            # 10: tailored
            (f"SELECT COUNT(*) {uj} AND tailored_resume_path IS NOT NULL", (u,)),
            # 11: untailored_eligible
            (
                "SELECT COUNT(*) FROM jobs j "
                "JOIN user_jobs uj ON uj.job_url = j.url AND uj.user_id = ? "
                "WHERE uj.fit_score >= 7 AND j.full_description IS NOT NULL "
                "AND uj.tailored_resume_path IS NULL "
                "AND COALESCE(uj.tailor_attempts, 0) < 5 "
                "AND (uj.apply_status IS NULL OR uj.apply_status NOT IN ('dismissed','location_filtered'))",
                (u,),
            ),
            # 12: tailor_exhausted
            (
                f"SELECT COUNT(*) {uj} AND COALESCE(tailor_attempts, 0) >= 5 AND tailored_resume_path IS NULL",
                (u,),
            ),
            # 13: with_cover_letter
            (f"SELECT COUNT(*) {uj} AND cover_letter_path IS NOT NULL", (u,)),
            # 14: cover_exhausted
            (
                f"SELECT COUNT(*) {uj} AND COALESCE(cover_attempts, 0) >= 5 "
                "AND (cover_letter_path IS NULL OR cover_letter_path = '')",
                (u,),
            ),
            # 15: applied
            (f"SELECT COUNT(*) {uj} AND applied_at IS NOT NULL", (u,)),
            # 16: apply_errors
            (f"SELECT COUNT(*) {uj} AND apply_error IS NOT NULL", (u,)),
            # 17: interviews
            (f"SELECT COUNT(*) {uj} AND apply_status = 'interview'", (u,)),
            # 18: offers
            (f"SELECT COUNT(*) {uj} AND apply_status = 'offer'", (u,)),
            # 19: rejected
            (f"SELECT COUNT(*) {uj} AND apply_status = 'rejected'", (u,)),
            # 20: ready_to_apply
            (
                f"SELECT COUNT(*) {uj} AND tailored_resume_path IS NOT NULL "
                "AND (apply_status IS NULL OR apply_status NOT IN "
                "('applied','dismissed','interview','offer','rejected','in_progress','manual','location_filtered'))",
                (u,),
            ),
        ]
        r = batch_query(conn, statements)
        stats: dict = {
            "total":               r[0].fetchone()[0],
            "by_site":             [(row[0], row[1]) for row in r[1].fetchall()],
            "pending_enrich":      r[2].fetchone()[0],
            "with_description":    r[3].fetchone()[0],
            "detail_errors":       r[4].fetchone()[0],
            "pending_filter":      r[5].fetchone()[0],
            "location_filtered":   r[6].fetchone()[0],
            "scored":              r[7].fetchone()[0],
            "unscored":            r[8].fetchone()[0],
            "score_distribution":  [(row[0], row[1]) for row in r[9].fetchall()],
            "tailored":            r[10].fetchone()[0],
            "untailored_eligible": r[11].fetchone()[0],
            "tailor_exhausted":    r[12].fetchone()[0],
            "with_cover_letter":   r[13].fetchone()[0],
            "cover_exhausted":     r[14].fetchone()[0],
            "applied":             r[15].fetchone()[0],
            "apply_errors":        r[16].fetchone()[0],
            "interviews":          r[17].fetchone()[0],
            "offers":              r[18].fetchone()[0],
            "rejected":            r[19].fetchone()[0],
            "ready_to_apply":      r[20].fetchone()[0],
        }
        stats["pending_detail"] = stats["pending_enrich"]
        return stats

    # Legacy: no user context — read from jobs table directly
    statements_legacy: list[tuple[str, tuple]] = [
        ("SELECT COUNT(*) FROM jobs", ()),
        ("SELECT site, COUNT(*) as cnt FROM jobs GROUP BY site ORDER BY cnt DESC", ()),
        ("SELECT COUNT(*) FROM jobs WHERE detail_scraped_at IS NULL", ()),
        ("SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL", ()),
        ("SELECT COUNT(*) FROM jobs WHERE detail_error IS NOT NULL", ()),
        (
            "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL "
            "AND filtered_at IS NULL AND (apply_status IS NULL OR apply_status = 'failed')",
            (),
        ),
        ("SELECT COUNT(*) FROM jobs WHERE apply_status = 'location_filtered'", ()),
        ("SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL", ()),
        (
            "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL "
            "AND filtered_at IS NOT NULL AND fit_score IS NULL "
            "AND apply_status != 'location_filtered'",
            (),
        ),
        (
            "SELECT fit_score, COUNT(*) as cnt FROM jobs WHERE fit_score IS NOT NULL "
            "GROUP BY fit_score ORDER BY fit_score DESC",
            (),
        ),
        ("SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL", ()),
        (
            "SELECT COUNT(*) FROM jobs WHERE fit_score >= 7 AND full_description IS NOT NULL "
            "AND tailored_resume_path IS NULL AND COALESCE(tailor_attempts, 0) < 5 "
            "AND (apply_status IS NULL OR apply_status NOT IN ('dismissed','location_filtered'))",
            (),
        ),
        (
            "SELECT COUNT(*) FROM jobs WHERE COALESCE(tailor_attempts, 0) >= 5 "
            "AND tailored_resume_path IS NULL",
            (),
        ),
        ("SELECT COUNT(*) FROM jobs WHERE cover_letter_path IS NOT NULL", ()),
        (
            "SELECT COUNT(*) FROM jobs WHERE COALESCE(cover_attempts, 0) >= 5 "
            "AND (cover_letter_path IS NULL OR cover_letter_path = '')",
            (),
        ),
        ("SELECT COUNT(*) FROM jobs WHERE applied_at IS NOT NULL", ()),
        ("SELECT COUNT(*) FROM jobs WHERE apply_error IS NOT NULL", ()),
        ("SELECT COUNT(*) FROM jobs WHERE apply_status = 'interview'", ()),
        ("SELECT COUNT(*) FROM jobs WHERE apply_status = 'offer'", ()),
        ("SELECT COUNT(*) FROM jobs WHERE apply_status = 'rejected'", ()),
        (
            "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL "
            "AND (apply_status IS NULL OR apply_status NOT IN "
            "('applied','dismissed','interview','offer','rejected','in_progress','manual','location_filtered'))",
            (),
        ),
    ]
    r = batch_query(conn, statements_legacy)
    stats = {
        "total":               r[0].fetchone()[0],
        "by_site":             [(row[0], row[1]) for row in r[1].fetchall()],
        "pending_enrich":      r[2].fetchone()[0],
        "with_description":    r[3].fetchone()[0],
        "detail_errors":       r[4].fetchone()[0],
        "pending_filter":      r[5].fetchone()[0],
        "location_filtered":   r[6].fetchone()[0],
        "scored":              r[7].fetchone()[0],
        "unscored":            r[8].fetchone()[0],
        "score_distribution":  [(row[0], row[1]) for row in r[9].fetchall()],
        "tailored":            r[10].fetchone()[0],
        "untailored_eligible": r[11].fetchone()[0],
        "tailor_exhausted":    r[12].fetchone()[0],
        "with_cover_letter":   r[13].fetchone()[0],
        "cover_exhausted":     r[14].fetchone()[0],
        "applied":             r[15].fetchone()[0],
        "apply_errors":        r[16].fetchone()[0],
        "interviews":          r[17].fetchone()[0],
        "offers":              r[18].fetchone()[0],
        "rejected":            r[19].fetchone()[0],
        "ready_to_apply":      r[20].fetchone()[0],
    }
    stats["pending_detail"] = stats["pending_enrich"]
    return stats


def cleanup_old_jobs(days: int = 60, conn: sqlite3.Connection | None = None) -> int:
    """Delete jobs older than `days` days that no user has scored, tailored, or applied to.

    Jobs with any meaningful user_jobs record are preserved regardless of age.
    Returns the number of rows deleted.
    """
    if conn is None:
        conn = get_connection()
    cursor = conn.execute(
        """
        DELETE FROM jobs
        WHERE discovered_at < datetime('now', ?)
        AND url NOT IN (
            SELECT DISTINCT job_url FROM user_jobs
            WHERE fit_score IS NOT NULL
               OR tailored_resume_path IS NOT NULL
               OR cover_letter_path IS NOT NULL
               OR applied_at IS NOT NULL
        )
        """,
        (f"-{days} days",),
    )
    deleted = cursor.rowcount
    conn.commit()
    if deleted:
        import logging as _logging
        _logging.getLogger(__name__).info("Cleanup: deleted %d jobs older than %d days", deleted, days)
    return deleted


def is_duplicate(conn: sqlite3.Connection, title: str | None,
                  company: str | None) -> bool:
    """Check if a job with the same normalized (title, company) already exists."""
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
    """Store discovered jobs, skipping duplicates by URL or (title, company)."""
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
                      limit: int = 100,
                      user_id: int | None = None) -> list[dict]:
    """Fetch jobs filtered by pipeline stage.

    When user_id is provided, score/tailor/cover conditions are evaluated
    against user_jobs. When None, falls back to the jobs table columns.
    """
    if conn is None:
        conn = get_connection()

    if user_id is not None:
        # User-scoped queries join user_jobs
        conditions = {
            "discovered": "1=1",
            "pending_detail": "j.detail_scraped_at IS NULL",
            "enriched": "j.full_description IS NOT NULL",
            "pending_score": (
                "j.full_description IS NOT NULL "
                "AND (uj.fit_score IS NULL OR uj.user_id IS NULL)"
            ),
            "scored": "uj.fit_score IS NOT NULL",
            "pending_tailor": (
                "uj.fit_score >= ? AND j.full_description IS NOT NULL "
                "AND uj.tailored_resume_path IS NULL AND COALESCE(uj.tailor_attempts, 0) < 5"
            ),
            "tailored": "uj.tailored_resume_path IS NOT NULL",
            "pending_apply": (
                "uj.tailored_resume_path IS NOT NULL AND uj.applied_at IS NULL "
                "AND j.application_url IS NOT NULL"
            ),
            "applied": "uj.applied_at IS NOT NULL",
        }
        where = conditions.get(stage, "1=1")
        params: list = [user_id]
        if "?" in where and min_score is not None:
            params.insert(0, min_score)
        elif "?" in where:
            params.insert(0, 7)

        query = (
            f"SELECT j.*, uj.fit_score, uj.score_reasoning, uj.scored_at, "
            f"uj.tailored_resume_path, uj.tailored_at, uj.tailor_attempts, "
            f"uj.cover_letter_path, uj.cover_letter_at, uj.cover_attempts, "
            f"uj.apply_status, uj.applied_at, uj.apply_error, uj.favorited "
            f"FROM jobs j "
            f"LEFT JOIN user_jobs uj ON uj.job_url = j.url AND uj.user_id = ? "
            f"WHERE {where} ORDER BY uj.fit_score DESC NULLS LAST, j.discovered_at DESC"
        )
        if limit > 0:
            query += " LIMIT ?"
            params.append(limit)
    else:
        # Legacy: no user context
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
        params = []
        if "?" in where and min_score is not None:
            params.append(min_score)
        elif "?" in where:
            params.append(7)

        if min_score is not None and "fit_score" not in where and stage in ("scored", "tailored", "applied"):
            where += " AND fit_score >= ?"
            params.append(min_score)

        query = f"SELECT * FROM jobs WHERE {where} ORDER BY fit_score DESC NULLS LAST, discovered_at DESC"
        if limit > 0:
            query += " LIMIT ?"
            params.append(limit)

    rows = conn.execute(query, params).fetchall()

    if rows:
        columns = rows[0].keys()
        return [dict(zip(columns, row)) for row in rows]
    return []
