"""Lightweight job-posting liveness check.

Used before tailor / cover_letter to avoid wasting LLM calls and the user's
monthly quota on dead postings, and on detail-drawer open to surface stale
listings before the user sinks effort into them.

Intentionally cheap: one httpx GET, regex on the response body. We don't spin
up Chromium — for the common boards (LinkedIn, Indeed, Workday, Greenhouse,
Lever, etc.) the closure marker is in the initial HTML or comes back as a 4xx.
"""

from __future__ import annotations

import logging
from typing import Literal

import httpx

log = logging.getLogger(__name__)

LivenessStatus = Literal["open", "closed", "unknown"]


# Substrings that strongly indicate the posting is closed. Lowercased; we match
# against a lowercased response body. Keep these specific — we'd rather return
# "unknown" and preserve a job than false-positive on unrelated text.
_CLOSED_PHRASES: tuple[str, ...] = (
    "no longer accepting applications",
    "this job is no longer accepting",
    "this job has expired",
    "this job is no longer available",
    "this job has been removed",
    "this position is no longer available",
    "this position has been filled",
    "the role has been filled",
    "this opportunity has closed",
    "this job is no longer open",
    "applications are now closed",
    "this listing has expired",
    "we are no longer accepting applications",
    "the job you are looking for is not available",
)

_DEAD_HTTP_STATUSES: frozenset[int] = frozenset({404, 410})

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def verify_job_open(url: str, *, timeout: float = 6.0) -> LivenessStatus:
    """Single-shot liveness check.

    Returns:
        "closed"  — strong signal the posting is gone (404/410 or known phrase).
        "open"    — fetched 2xx, no closure marker found.
        "unknown" — transient error, 5xx, anti-bot block, or non-2xx redirect.
                    Caller should treat this as "probably still open" and not
                    block the user.
    """
    if not url:
        return "unknown"

    headers = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
            resp = client.get(url)
    except Exception as e:
        log.info("liveness fetch error for %s: %s", url, e)
        return "unknown"

    if resp.status_code in _DEAD_HTTP_STATUSES:
        return "closed"
    if resp.status_code != 200:
        # 5xx, 403 anti-bot, 3xx loops — preserve the job.
        return "unknown"

    body_lower = resp.text.lower()
    for phrase in _CLOSED_PHRASES:
        if phrase in body_lower:
            return "closed"

    return "open"
