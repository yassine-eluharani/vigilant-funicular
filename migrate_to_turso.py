#!/usr/bin/env python3
"""Migrate local SQLite DB → Turso (libSQL)."""
import sqlite3
import os
import sys

SQLITE_PATH = os.path.expanduser("~/.applypilot/applypilot.db")
DATABASE_URL = "libsql://applypilot-film-wata2i9i.aws-eu-west-1.turso.io"
DATABASE_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJpYXQiOjE3NzY3MDMyNDQsImlkIjoiMDE5ZGFiYzMtMTkwMS03NjdjLWE3NTgtNmY3Y2JhODZjYjY1IiwicmlkIjoiYTNiYmZmMTUtYjYzNC00OTVhLThhYWItNzRiMzg4MTNjMDdkIn0.Dm_weNsQrmHOxFhsWT4hJ0_XRpgfmBuOS41xfAWRBHdBKWTAnQHpPt6zHpwqSZox9MIbK34ZFU9xVSqSph02AA"

import libsql_experimental as libsql

print(f"Connecting to local SQLite: {SQLITE_PATH}")
local = sqlite3.connect(SQLITE_PATH)
local.row_factory = sqlite3.Row

print(f"Connecting to Turso: {DATABASE_URL}")
remote = libsql.connect(database=DATABASE_URL, auth_token=DATABASE_TOKEN)

# ── Get all tables from local DB ──────────────────────────────────────────────
tables = [r[0] for r in local.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
).fetchall()]
print(f"Tables found: {tables}")

for table in tables:
    print(f"\n── Migrating table: {table} ──")

    # Get CREATE statement
    create_sql = local.execute(
        f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()[0]

    # Create table in Turso (ignore if exists)
    try:
        remote.execute(create_sql)
        remote.commit()
        print(f"  Created table {table} in Turso")
    except Exception as e:
        print(f"  Table {table} already exists (or error): {e}")

    # Get rows from local
    rows = local.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        print(f"  No rows to migrate")
        continue

    cols = rows[0].keys()
    placeholders = ", ".join(["?" for _ in cols])
    col_names = ", ".join(cols)
    insert_sql = f"INSERT OR IGNORE INTO {table} ({col_names}) VALUES ({placeholders})"

    batch_size = 50
    inserted = 0
    skipped = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        for row in batch:
            try:
                remote.execute(insert_sql, tuple(row))
                inserted += 1
            except Exception as e:
                skipped += 1
        remote.commit()
        print(f"  Progress: {min(i+batch_size, len(rows))}/{len(rows)} rows...", end="\r")

    print(f"  Done: {inserted} inserted, {skipped} skipped (duplicates/errors)    ")

local.close()
print("\nMigration complete.")
