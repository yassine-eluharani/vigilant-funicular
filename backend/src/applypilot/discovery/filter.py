"""Location filter: detect country-restricted remote jobs before scoring.

Scans full_description (and location field) for patterns that indicate
a job is remote only within a specific country the user cannot work in.
Matching jobs are marked apply_status='location_filtered' so they never
reach the scoring, tailoring, or dashboard queues.

Patterns are loaded from searches.yaml under `description_reject_patterns`.
Built-in defaults cover the most common US/Canada/UK restriction phrases.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from applypilot.config import load_search_config
from applypilot.database import get_connection

log = logging.getLogger(__name__)

# Built-in defaults — used when searches.yaml has no description_reject_patterns key.
# These cover the most common "remote but country-specific" phrasings.
DEFAULT_REJECT_PATTERNS: list[str] = [
    # US citizenship / authorization
    "us citizen",
    "u.s. citizen",
    "us citizens only",
    "authorized to work in the united states",
    "authorized to work in the us",
    "eligible to work in the us",
    "eligible to work in the united states",
    "work authorization in the us",
    "right to work in the united states",
    "right to work in the us",
    "must be authorized to work",
    # Must reside / be located in US
    "must be located in the us",
    "must be located in the united states",
    "must reside in the us",
    "must reside in the united states",
    "must be based in the us",
    "must be based in the united states",
    "based in the us",
    "located in the us",
    "located in the united states",
    "residing in the us",
    "candidates must reside",
    "candidates must be located",
    "candidates must be based in the us",
    "candidates based in the united states",
    # Remote US labels
    "remote - us",
    "remote (us)",
    "remote – us",
    "remote us only",
    "remote, us",
    "us remote",
    "remote in the us",
    "remote within the us",
    "us only",
    "usa only",
    "united states only",
    "north america only",
    "americas only",
    # Work permit / USCIS references (strong US-only signal)
    "must have a valid ead",
    "employment authorization document",
    "h-1b transfer",
    "h1b transfer",
    "green card",
    "us work permit",
    "uscis",
    "i-9 eligibility",
    "i9 eligibility",
    # Sponsorship explicitly declined
    "no visa sponsorship",
    "does not offer visa sponsorship",
    "does not sponsor visas",
    "does not provide visa sponsorship",
    "does not sponsor work",
    "unable to sponsor",
    "not able to sponsor",
    "cannot sponsor",
    "will not sponsor",
    "sponsorship not available",
    "sponsorship is not available",
    "no sponsorship available",
    "we do not sponsor",
    "we are unable to offer visa",
    "visa sponsorship is not provided",
    "not in a position to sponsor",
    # Canada/UK/EU/AU only
    "canada only",
    "remote canada",
    "remote - canada",
    "must be eligible to work in canada",
    "right to work in canada",
    "uk only",
    "remote - uk",
    "must have the right to work in the uk",
    "right to work in the uk",
    "eligible to work in the uk",
    "eu only",
    "europe only",
    "must be based in europe",
    "australia only",
    "new zealand only",
    "right to work in australia",
]


def run_location_filter(cfg: dict | None = None) -> dict:
    """Scan enriched jobs for country-restriction patterns.

    For each enriched job with apply_status=NULL (or 'failed'), the combined
    location + full_description text is checked against all patterns.
    A single match is enough to mark the job as location_filtered.

    Args:
        cfg: Optional searches config dict. Loaded from searches.yaml if None.

    Returns:
        {"filtered": int, "checked": int, "patterns": int}
    """
    if cfg is None:
        cfg = load_search_config()

    patterns: list[str] = cfg.get("description_reject_patterns", DEFAULT_REJECT_PATTERNS)
    if not patterns:
        return {"filtered": 0, "checked": 0, "patterns": 0}

    compiled = [
        re.compile(re.escape(p.strip()), re.IGNORECASE)
        for p in patterns
        if p.strip()
    ]

    conn = get_connection()
    rows = conn.execute(
        "SELECT url, location, full_description FROM jobs "
        "WHERE full_description IS NOT NULL "
        "AND filtered_at IS NULL "
        "AND (apply_status IS NULL OR apply_status = 'failed')"
    ).fetchall()

    now = datetime.now(timezone.utc).isoformat()
    filtered = 0
    for url, location, description in rows:
        haystack = f"{location or ''} {description or ''}"
        rejected = False
        for pattern in compiled:
            if pattern.search(haystack):
                conn.execute(
                    "UPDATE jobs SET apply_status = 'location_filtered', "
                    "apply_error = ?, filtered_at = ? WHERE url = ?",
                    (f"filter: {pattern.pattern}", now, url),
                )
                filtered += 1
                rejected = True
                log.info("Location-filtered: %s — pattern '%s'", url[:80], pattern.pattern)
                break
        if not rejected:
            conn.execute(
                "UPDATE jobs SET filtered_at = ? WHERE url = ?",
                (now, url),
            )

    conn.commit()
    log.info(
        "Location filter complete: checked %d jobs, filtered %d out",
        len(rows), filtered,
    )
    return {"filtered": filtered, "checked": len(rows), "patterns": len(compiled)}
