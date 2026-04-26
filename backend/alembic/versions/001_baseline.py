"""Baseline — existing schema, no DDL changes.

This revision marks the current Turso / SQLite schema as the starting point
for Alembic tracking. Apply it with:

    cd backend && alembic stamp head

This writes the revision ID into alembic_version without running any SQL.
Future schema changes (ADD COLUMN, DROP COLUMN, etc.) should be new revisions
generated via:

    alembic revision --autogenerate -m "describe change"

Revision ID: 001_baseline
Revises:
Create Date: 2026-04-25
"""
from typing import Sequence, Union

revision: str = "001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass  # existing DB already has the full schema


def downgrade() -> None:
    pass
