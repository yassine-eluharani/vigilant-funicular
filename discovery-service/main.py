#!/usr/bin/env python3
"""ApplyPilot Discovery Service — standalone homelab worker.

Runs the discovery scheduler loop: reads all user search configs + the
built-in popular_searches.yaml, deduplicates combos, and scrapes stale ones.

Environment variables:
  DATABASE_URL       SQLite path, libsql://your-db.turso.io, or postgresql://...
  DATABASE_TOKEN     Auth token for Turso (libSQL) connections
  APPLYPILOT_DIR     Directory for local SQLite if DATABASE_URL not set
  INTERVAL_HOURS     How often to run a cycle (default: 2)
  STALE_AFTER_HOURS  How old a combo must be to re-scrape (default: 2)
  LOG_LEVEL          Logging level (default: INFO)
"""

import logging
import os
import sys
import time
from pathlib import Path

# Allow importing from main backend if running inside the monorepo
_repo_backend = Path(__file__).resolve().parents[1] / "backend" / "src"
if _repo_backend.exists():
    sys.path.insert(0, str(_repo_backend))

# Load .env from service directory or parent
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("discovery-service")

INTERVAL_HOURS = float(os.environ.get("INTERVAL_HOURS", "2"))


def main() -> None:
    from worker import run_cycle

    log.info("ApplyPilot Discovery Service starting")
    log.info("Cycle interval: %.1fh | Stale threshold: %sh",
             INTERVAL_HOURS, os.environ.get("STALE_AFTER_HOURS", "2"))

    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        log.info("DB: %s", db_url.split("?")[0])  # hide query params / tokens
    else:
        from pathlib import Path as P
        app_dir = os.environ.get("APPLYPILOT_DIR", str(P.home() / ".applypilot"))
        log.info("DB: SQLite @ %s/applypilot.db", app_dir)

    while True:
        try:
            log.info("── Starting discovery cycle ──")
            run_cycle()
        except Exception as e:
            log.error("Cycle failed: %s", e, exc_info=True)

        log.info("Sleeping %.1fh until next cycle…", INTERVAL_HOURS)
        time.sleep(INTERVAL_HOURS * 3600)


if __name__ == "__main__":
    main()
