#!/usr/bin/env bash
# sync-shared-modules.sh — Push shared modules from this repo → applypilot-discovery.
#
# Usage:
#   ./sync-shared-modules.sh [--check]
#
# Without flags: copies llm.py (the only 1:1 shared module) and reports drift
# on the others that have been adapted for the discovery worker.
#
# With --check: dry-run, shows what would change without writing anything.

set -euo pipefail

DISCOVERY_DIR="${DISCOVERY_DIR:-../applypilot-discovery}"
CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

if [[ ! -d "$DISCOVERY_DIR" ]]; then
  echo "Error: discovery worker not found at $DISCOVERY_DIR"
  echo "Set DISCOVERY_DIR=/path/to/applypilot-discovery or check out the repo there."
  exit 1
fi

BACKEND="backend/src/applypilot"

# ── 1. llm.py — 1:1 copy, keep in sync ──────────────────────────────────────

SRC="$BACKEND/llm.py"
DST="$DISCOVERY_DIR/llm.py"

if diff -q "$SRC" "$DST" > /dev/null 2>&1; then
  echo "[llm.py]       up to date"
else
  if [[ $CHECK_ONLY -eq 1 ]]; then
    echo "[llm.py]       DIFF (would overwrite)"
    diff "$SRC" "$DST" || true
  else
    cp "$SRC" "$DST"
    echo "[llm.py]       synced ✓"
  fi
fi

# ── 2. Adapted modules — report drift, no auto-copy ─────────────────────────
#
# These modules exist in both repos but have been adapted for the discovery
# worker (different import paths, extra parameters, standalone structure).
# Auto-copying would break the discovery worker. Review manually when changing
# the corresponding main-repo files.
#
# Main repo                         Discovery worker       Notes
# --------------------------------- ---------------------- -----------------
# discovery/filter.py               filter.py              extra_patterns param added
# scoring/indexer.py                indexer.py             inline imports, adapted
# discovery/{jobspy,workday,...}.py  discovery.py           merged into one file
# enrichment/detail.py              enrichment.py          standalone version
# database.py                       turso.py               Turso HTTP client variant

echo ""
echo "── Adapted modules (manual review when main repo changes) ──────────────"

check_drift() {
  local label="$1"
  local main_src="$2"
  local worker_dst="$DISCOVERY_DIR/$3"

  if [[ ! -f "$main_src" ]]; then
    echo "[$label]  main-repo file missing: $main_src"
    return
  fi
  if [[ ! -f "$worker_dst" ]]; then
    echo "[$label]  worker file missing: $worker_dst"
    return
  fi

  # Count changed lines (excluding blank/comment-only lines for noise reduction)
  local changed
  changed=$(diff "$main_src" "$worker_dst" | grep -c '^[<>]' || true)
  if [[ $changed -eq 0 ]]; then
    echo "[$label]  identical"
  else
    echo "[$label]  ~$changed changed lines — review if you edited the main-repo version"
  fi
}

check_drift "filter.py  " "$BACKEND/discovery/filter.py"   "filter.py"
check_drift "indexer.py " "$BACKEND/scoring/indexer.py"     "indexer.py"
check_drift "turso.py   " "$BACKEND/database.py"            "turso.py"

echo ""
if [[ $CHECK_ONLY -eq 1 ]]; then
  echo "Dry-run complete. Run without --check to apply changes."
else
  echo "Sync complete."
fi
