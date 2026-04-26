"""Alembic migration environment.

To stamp the existing Turso DB as baseline (no DDL, first run):
    cd backend
    alembic stamp head

To generate a new migration after model changes:
    alembic revision --autogenerate -m "describe change"

To apply pending migrations:
    alembic upgrade head
"""
import os
import sys
from pathlib import Path
from logging.config import fileConfig

from alembic import context

# Make the applypilot package importable from backend/alembic/env.py
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlmodel import SQLModel
import applypilot.db.models  # noqa: F401 — registers all table metadata
from applypilot.db.engine import engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _get_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    token = os.environ.get("DATABASE_TOKEN", "")
    if url.startswith("libsql://") or url.startswith("wss://"):
        host = url.replace("libsql://", "").replace("wss://", "")
        return f"sqlite+libsql://{host}/?authToken={token}&secure=true"
    if url:
        return f"sqlite:///{url}"
    from applypilot.config import DB_PATH
    return f"sqlite:///{DB_PATH}"


def run_migrations_offline() -> None:
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
