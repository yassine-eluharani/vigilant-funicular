"""Database connection abstraction for the discovery service.

Supports:
  - Local SQLite (default, same as main app)
  - Turso / libSQL  (set DATABASE_URL=libsql://your-db.turso.io, DATABASE_TOKEN=...)
  - PostgreSQL      (set DATABASE_URL=postgresql://user:pass@host/db)

The connection object returned always has the sqlite3.Connection interface
so the rest of the code stays unchanged.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

_local = threading.local()

DATABASE_URL = os.environ.get("DATABASE_URL", "")
DATABASE_TOKEN = os.environ.get("DATABASE_TOKEN", "")


def get_connection() -> sqlite3.Connection:
    """Return a thread-local DB connection based on DATABASE_URL."""
    url = DATABASE_URL

    if url.startswith("libsql://") or url.startswith("wss://") or url.startswith("https://"):
        return _turso_connection()
    elif url.startswith("postgresql://") or url.startswith("postgres://"):
        raise RuntimeError(
            "PostgreSQL support requires a schema migration. "
            "Use Turso (libsql://) for a drop-in SQLite replacement."
        )
    else:
        # Default: local SQLite file
        return _sqlite_connection(url or _default_sqlite_path())


def _default_sqlite_path() -> str:
    app_dir = os.environ.get("APPLYPILOT_DIR", str(Path.home() / ".applypilot"))
    return str(Path(app_dir) / "applypilot.db")


def _sqlite_connection(path: str) -> sqlite3.Connection:
    if not hasattr(_local, "sqlite_conns"):
        _local.sqlite_conns = {}
    conn = _local.sqlite_conns.get(path)
    if conn:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.ProgrammingError:
            pass
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.row_factory = sqlite3.Row
    _local.sqlite_conns[path] = conn
    return conn


def _turso_connection():
    """Return a libsql connection that looks like sqlite3.Connection."""
    try:
        import libsql_experimental as libsql  # pip install libsql-experimental
    except ImportError:
        raise RuntimeError(
            "Install libsql-experimental for Turso support: "
            "pip install libsql-experimental"
        )

    if not hasattr(_local, "turso_conn"):
        _local.turso_conn = libsql.connect(
            database=DATABASE_URL,
            auth_token=DATABASE_TOKEN,
        )
    return _local.turso_conn


def init_db() -> None:
    """Create required tables if they don't exist."""
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            email          TEXT UNIQUE NOT NULL,
            password_hash  TEXT NOT NULL,
            full_name      TEXT NOT NULL,
            created_at     TEXT NOT NULL,
            last_login     TEXT,
            tier           TEXT DEFAULT 'free',
            tailors_used   INTEGER DEFAULT 0,
            covers_used    INTEGER DEFAULT 0,
            usage_reset_at TEXT,
            searches_json  TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            url                   TEXT PRIMARY KEY,
            title                 TEXT,
            company               TEXT,
            salary                TEXT,
            description           TEXT,
            location              TEXT,
            site                  TEXT,
            strategy              TEXT,
            discovered_at         TEXT,
            full_description      TEXT,
            application_url       TEXT,
            detail_scraped_at     TEXT,
            detail_error          TEXT,
            filtered_at           TEXT,
            fit_score             INTEGER,
            score_reasoning       TEXT,
            scored_at             TEXT,
            tailored_resume_path  TEXT,
            tailored_at           TEXT,
            tailor_attempts       INTEGER DEFAULT 0,
            cover_letter_path     TEXT,
            cover_letter_at       TEXT,
            cover_attempts        INTEGER DEFAULT 0,
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
    conn.commit()
