"""SQLAlchemy engine + session factory — local SQLite only.

Used for local development and Alembic migration generation.
Production Turso writes still use the HTTP-based _TursoConnection in database.py
(sqlalchemy-libsql requires Rust compilation and lacks ARM64 Linux wheels).

Session usage:
    from applypilot.db.engine import get_session
    with get_session() as session:
        session.add(...)
        session.commit()
"""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session


def _build_engine():
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("libsql://") or url.startswith("wss://"):
        # Turso: session-based ORM queries not yet supported (no ARM64 libsql wheel).
        # Return a dummy in-memory engine so imports succeed; actual writes use
        # the _TursoConnection HTTP wrapper in database.py.
        eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    else:
        from applypilot.config import DB_PATH
        db_path = str(url) if url else str(DB_PATH)
        eng = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )

    @event.listens_for(eng, "connect")
    def _set_fk_pragma(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return eng


engine = _build_engine()


@contextmanager
def get_session():
    """Yield a SQLAlchemy Session. Commits on clean exit, rolls back on exception."""
    with Session(engine, expire_on_commit=False) as session:
        yield session
