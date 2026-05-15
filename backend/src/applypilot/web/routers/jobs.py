"""Jobs routes — list, detail, resume/cover, status mutations.

BE-002: Async route handlers offload sync DB / liveness work to the FastAPI
threadpool via ``asyncio.to_thread`` so a slow Turso HTTP call or a sluggish
liveness probe can't pin the event loop. Sync route handlers (``def``) are
already dispatched to the threadpool by Starlette and don't need wrapping.
See ``web/auth.py`` for the full rationale.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time as _time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from applypilot.database import (
    get_connection,
    upsert_user_job,
    batch_query,
    mark_job_closed,
    mark_liveness_checked,
)
from applypilot.enrichment.liveness import UnsafeUrlError, verify_job_open
from applypilot.web.auth import get_current_user
from applypilot.web.core import _start_task, decode_url, row_to_job, tailor_limiter, cover_limiter
from applypilot.web.schemas import (
    CoverResponse,
    FavoriteResponse,
    JobItem,
    JobListResponse,
    MarkStatusRequest,
    SaveResumeRequest,
    SaveResumeResponse,
    StatsResponse,
    StatusMutationResponse,
    TailorResponse,
)

log = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])

# Stats cache: user_id → (computed_at, payload_dict)
_stats_cache: dict[int, tuple[float, dict]] = {}
_STATS_TTL = 30.0  # seconds


def _is_job_closed(job_url: str) -> bool:
    """Sync DB lookup: True iff this job already has ``closed_at`` set."""
    conn = get_connection()
    row = conn.execute(
        "SELECT closed_at FROM jobs WHERE url = ?", (job_url,)
    ).fetchone()
    return bool(row and row["closed_at"])


def _mark_closed(job_url: str, reason: str) -> None:
    """Sync DB write: stamp this job as closed."""
    mark_job_closed(get_connection(), job_url, reason=reason)


def _mark_liveness(job_url: str) -> None:
    """Sync DB write: bump liveness_checked_at."""
    mark_liveness_checked(get_connection(), job_url)


async def _ensure_job_open_or_410(job_url: str) -> None:
    """Block tailor / cover-letter when the posting is verified closed.

    Raises HTTP 410 Gone with a clear message so the frontend can show a toast
    and we don't burn an LLM call or the user's monthly tailor count on a
    dead listing. If the job was already marked closed previously, fail fast
    without re-fetching.

    `verify_job_open` is sync httpx; we offload it to a thread so we don't
    block the event loop (TST-021). The DB lookups around it are likewise
    offloaded (BE-002) — they're sync sqlite3 / Turso HTTP under the hood.
    """
    if await asyncio.to_thread(_is_job_closed, job_url):
        raise HTTPException(
            status_code=410,
            detail="This job posting is no longer open. It will be removed shortly.",
        )
    try:
        status = await asyncio.to_thread(verify_job_open, job_url, timeout=5.0)
    except UnsafeUrlError as e:
        # URL fails the SSRF guard (private/loopback/non-http). Treat as closed
        # — we won't fetch it, and we don't want to burn a tailor on it either.
        log.warning("blocked unsafe job url in tailor/cover: %s (%s)", job_url, e)
        await asyncio.to_thread(_mark_closed, job_url, "unsafe_url_blocked")
        raise HTTPException(
            status_code=410,
            detail="This job posting can't be verified and is no longer available.",
        )
    if status == "closed":
        await asyncio.to_thread(_mark_closed, job_url, "verified_closed_pre_tailor")
        raise HTTPException(
            status_code=410,
            detail="This job posting is no longer accepting applications.",
        )
    if status == "open":
        await asyncio.to_thread(_mark_liveness, job_url)
    # status == "unknown" → don't block; preserve user flow on transient errors.


def _invalidate_stats(user_id: int) -> None:
    """Drop the cached stats for a user so the next request recomputes."""
    _stats_cache.pop(user_id, None)
    from applypilot.web.core import notify_user
    notify_user(user_id, "stats_changed")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/api/stats", response_model=StatsResponse)
def stats(user: dict = Depends(get_current_user)) -> dict:
    from applypilot.database import get_stats
    user_id = user["id"]

    cached = _stats_cache.get(user_id)
    if cached and _time.monotonic() - cached[0] < _STATS_TTL:
        return cached[1]

    s = get_stats(user_id=user_id)
    conn = get_connection()

    # Batch the 3 extra queries that the router needs beyond get_stats()
    extra_stmts: list[tuple[str, tuple]] = [
        (
            "SELECT COUNT(*) FROM user_jobs WHERE user_id = ? "
            "AND tailored_resume_path IS NOT NULL "
            "AND (apply_status IS NULL OR apply_status NOT IN ('applied','dismissed'))",
            (user_id,),
        ),
        (
            "SELECT COUNT(*) FROM user_jobs WHERE user_id = ? AND apply_status = 'dismissed'",
            (user_id,),
        ),
        (
            "SELECT DISTINCT j.site FROM jobs j "
            "JOIN user_jobs uj ON uj.job_url = j.url AND uj.user_id = ? "
            "WHERE uj.tailored_resume_path IS NOT NULL AND j.site IS NOT NULL ORDER BY j.site",
            (user_id,),
        ),
    ]
    er = batch_query(conn, extra_stmts)
    pending      = er[0].fetchone()[0]
    dismissed    = er[1].fetchone()[0]
    sites        = er[2].fetchall()

    payload = {
        "tailored": s["tailored"],
        "pending": pending,
        "applied": s["applied"],
        "dismissed": dismissed,
        "untailored": s["untailored_eligible"],
        "location_filtered": s["location_filtered"],
        "ready_to_apply": s["ready_to_apply"],
        "interviews": s["interviews"],
        "offers": s["offers"],
        "rejected": s["rejected"],
        "sites": [r[0] for r in sites],
        "score_distribution": {str(sc): ct for sc, ct in s["score_distribution"]},
        "funnel": {
            "discovered":        s["total"],
            "pending_enrich":    s["pending_enrich"],
            "enriched":          s["with_description"],
            "pending_filter":    s["pending_filter"],
            "location_filtered": s["location_filtered"],
            "scored":            s["scored"],
            "pending_score":     s["unscored"],
            "tailored":          s["tailored"],
            "pending_tailor":    s["untailored_eligible"],
            "cover":             s["with_cover_letter"],
            "pending_cover":     max(0, s["tailored"] - s["with_cover_letter"]),
            "ready_to_apply":    s["ready_to_apply"],
            "applied":           s["applied"],
            "interviews":        s["interviews"],
            "offers":            s["offers"],
            "rejected_count":    s["rejected"],
            "apply_errors":      s["apply_errors"],
        },
    }
    _stats_cache[user_id] = (_time.monotonic(), payload)
    return payload


# ---------------------------------------------------------------------------
# Job listing
# ---------------------------------------------------------------------------

@router.get("/api/jobs", response_model=JobListResponse)
def list_jobs(
    user: dict = Depends(get_current_user),
    min_score: int = Query(7, ge=1, le=10),
    max_score: int = Query(10, ge=1, le=10),
    site: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    status: str = Query("pending"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    conn = get_connection()
    user_id = user["id"]

    # Base: always join jobs with user_jobs for this user.
    # Closed jobs are excluded from every list view (verified dead postings
    # are useless to the user — only kept around for the grace-period cleanup).
    base = (
        "FROM jobs j "
        "LEFT JOIN user_jobs uj ON uj.job_url = j.url AND uj.user_id = ? "
    )
    base_params: list = [user_id]

    # BE-020: build a list of (clause, params) tuples so each filter is a
    # single tuple-append rather than two coordinated list-appends. The clause
    # text and its bound params live together — adding/reordering a filter
    # can no longer drift its parameters out of sync.
    parts: list[tuple[str, list]] = []

    if status == "scored":
        # All scored jobs — no tailoring requirement, respects score range
        parts.extend([
            ("uj.fit_score IS NOT NULL", []),
            ("uj.fit_score >= ?", [min_score]),
            ("uj.fit_score <= ?", [max_score]),
            ("(uj.apply_status IS NULL OR uj.apply_status NOT IN ('dismissed','location_filtered'))", []),
        ])
    elif status == "untailored":
        parts.extend([
            ("uj.tailored_resume_path IS NULL", []),
            ("uj.fit_score >= ?", [min_score]),
            ("uj.fit_score <= ?", [max_score]),
            ("j.full_description IS NOT NULL", []),
            ("(uj.apply_status IS NULL OR uj.apply_status NOT IN ('dismissed','location_filtered'))", []),
        ])
    elif status == "ready":
        parts.extend([
            ("uj.tailored_resume_path IS NOT NULL", []),
            ("uj.fit_score >= ?", [min_score]),
            ("uj.fit_score <= ?", [max_score]),
            (
                "(uj.apply_status IS NULL OR uj.apply_status NOT IN "
                "('applied','dismissed','interview','offer','rejected','in_progress','manual','location_filtered'))",
                [],
            ),
        ])
    elif status == "favorites":
        parts.extend([
            ("COALESCE(uj.favorited, 0) = 1", []),
            ("uj.fit_score >= ?", [min_score]),
            ("uj.fit_score <= ?", [max_score]),
        ])
    else:
        parts.extend([
            ("uj.tailored_resume_path IS NOT NULL", []),
            ("uj.fit_score >= ?", [min_score]),
            ("uj.fit_score <= ?", [max_score]),
        ])

    if status == "pending":
        parts.append(
            ("(uj.apply_status IS NULL OR uj.apply_status NOT IN ('applied','dismissed'))", [])
        )
    elif status == "applied":
        parts.append(
            ("uj.apply_status IN ('applied','interview','offer','rejected')", [])
        )
    elif status == "dismissed":
        parts.append(("uj.apply_status = 'dismissed'", []))

    if site:
        parts.append(("j.site = ?", [site]))

    if search:
        term = f"%{search}%"
        parts.append(
            ("(j.title LIKE ? OR uj.score_reasoning LIKE ? OR j.location LIKE ?)",
             [term, term, term])
        )

    # Always hide jobs we've verified as closed
    parts.append(("j.closed_at IS NULL", []))

    where = " AND ".join(c for c, _ in parts)
    where_params: list = []
    for _, p in parts:
        where_params.extend(p)
    params = base_params + where_params

    total = conn.execute(f"SELECT COUNT(*) {base} WHERE {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT j.url, j.title, j.company, j.site, j.location, j.salary, "
        f"uj.fit_score, uj.score_reasoning, "
        f"uj.tailored_resume_path, uj.cover_letter_path, "
        f"uj.apply_status, uj.applied_at, "
        f"j.application_url, j.discovered_at, uj.tailored_at, COALESCE(uj.favorited, 0) as favorited "
        f"{base} WHERE {where} "
        # Newest first; fit_score only as tiebreaker within the same timestamp.
        f"ORDER BY j.discovered_at DESC, uj.fit_score DESC "
        f"LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    jobs_out = [row_to_job(r) for r in rows]
    return {"jobs": jobs_out, "total": total, "offset": offset, "limit": limit}


# ---------------------------------------------------------------------------
# Job detail
# ---------------------------------------------------------------------------

def _fetch_job_for_user(user_id: int, job_url: str) -> dict | None:
    """Sync helper: load a single job + per-user join data, return row_to_job dict."""
    conn = get_connection()
    row = conn.execute(
        "SELECT j.*, uj.fit_score, uj.score_reasoning, uj.scored_at, "
        "uj.tailored_resume_path, uj.tailored_resume_text, uj.tailored_at, uj.tailor_attempts, "
        "uj.cover_letter_path, uj.cover_letter_text, uj.cover_letter_at, uj.cover_attempts, "
        "uj.apply_status, uj.applied_at, uj.apply_error, "
        "COALESCE(uj.favorited, 0) as favorited "
        "FROM jobs j "
        "LEFT JOIN user_jobs uj ON uj.job_url = j.url AND uj.user_id = ? "
        "WHERE j.url = ?",
        (user_id, job_url),
    ).fetchone()
    if not row:
        return None
    return row_to_job(row)


@router.get("/api/jobs/{encoded_url}", response_model=JobItem)
async def get_job(encoded_url: str, user: dict = Depends(get_current_user)) -> dict:
    job_url = decode_url(encoded_url)
    user_id = user["id"]

    # BE-002: hop the initial JOIN read into the threadpool so a slow Turso
    # round-trip doesn't pin the event loop.
    job = await asyncio.to_thread(_fetch_job_for_user, user_id, job_url)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Lazy liveness check: only when the user actually engages (drawer open),
    # only if not already known to be closed, and only if we haven't checked
    # within the last 24h. Failures are silent — we'd rather show a stale job
    # than block the drawer on network flakiness.
    if not job.get("closed_at"):
        last_checked = job.get("liveness_checked_at")
        is_stale = True
        if last_checked:
            try:
                t = datetime.datetime.fromisoformat(last_checked.replace("Z", "+00:00"))
                if t.tzinfo is None:
                    t = t.replace(tzinfo=datetime.timezone.utc)
                age = datetime.datetime.now(datetime.timezone.utc) - t
                is_stale = age.total_seconds() > 86400
            except Exception:
                is_stale = True
        if is_stale:
            try:
                status = await asyncio.to_thread(verify_job_open, job_url, timeout=5.0)
                if status == "closed":
                    await asyncio.to_thread(_mark_closed, job_url, "verified_closed_on_view")
                    job["closed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    job["closed_reason"] = "verified_closed_on_view"
                elif status == "open":
                    await asyncio.to_thread(_mark_liveness, job_url)
            except UnsafeUrlError as e:
                # URL fails SSRF guard — mark closed so we never try to fetch
                # again. This typically means a malformed/internal URL leaked
                # into the jobs table; treat the row as dead.
                log.warning(
                    "blocked unsafe job url on view: %s (%s)", job_url, e
                )
                await asyncio.to_thread(_mark_closed, job_url, "unsafe_url_blocked")
                job["closed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                job["closed_reason"] = "unsafe_url_blocked"
            except Exception:
                log.exception("liveness check failed on job detail view: %s", job_url)

    job["closed"] = bool(job.get("closed_at"))

    # Resume and cover letter text from DB
    job["resume_text"] = job.get("tailored_resume_text") or ""
    job["cover_letter_text"] = job.get("cover_letter_text") or ""

    return job


# ---------------------------------------------------------------------------
# Resume / cover letter files
# ---------------------------------------------------------------------------

@router.get("/api/resume/{encoded_url}")
def serve_resume(encoded_url: str, user: dict = Depends(get_current_user)) -> Response:
    job_url = decode_url(encoded_url)
    conn = get_connection()
    row = conn.execute(
        "SELECT tailored_resume_text FROM user_jobs WHERE user_id = ? AND job_url = ?",
        (user["id"], job_url),
    ).fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="No tailored resume for this job")
    text = row[0]
    try:
        from applypilot.scoring.pdf import text_to_pdf_bytes
        pdf_bytes = text_to_pdf_bytes(text)
    except Exception:
        # Don't silently return text/plain — the browser saves whatever blob it
        # gets as a .pdf, producing an unopenable file. Surface the failure
        # with a stable user-facing message; log the real reason server-side.
        log.exception("PDF generation failed for resume (job_url=%s)", job_url)
        raise HTTPException(
            status_code=500,
            detail="Could not generate the resume PDF. Please try again.",
        )
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=resume.pdf"})


@router.get("/api/cover-letter/{encoded_url}")
def serve_cover_letter(encoded_url: str, user: dict = Depends(get_current_user)) -> Response:
    job_url = decode_url(encoded_url)
    conn = get_connection()
    row = conn.execute(
        "SELECT cover_letter_text FROM user_jobs WHERE user_id = ? AND job_url = ?",
        (user["id"], job_url),
    ).fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="No cover letter for this job")
    text = row[0]
    try:
        from applypilot.scoring.pdf import text_to_pdf_bytes
        pdf_bytes = text_to_pdf_bytes(text)
    except Exception:
        log.exception("PDF generation failed for cover letter (job_url=%s)", job_url)
        raise HTTPException(
            status_code=500,
            detail="Could not generate the cover letter PDF. Please try again.",
        )
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=cover_letter.pdf"})


# ---------------------------------------------------------------------------
# Resume editing
# ---------------------------------------------------------------------------

def _save_resume_text(user_id: int, job_url: str, text: str) -> None:
    upsert_user_job(get_connection(), user_id, job_url, tailored_resume_text=text)


@router.put("/api/jobs/{encoded_url}/resume", response_model=SaveResumeResponse)
async def save_resume(
    encoded_url: str,
    payload: SaveResumeRequest,
    user: dict = Depends(get_current_user),
) -> SaveResumeResponse:
    job_url = decode_url(encoded_url)
    # BE-002: upsert is sync sqlite3/Turso HTTP — offload to threadpool.
    await asyncio.to_thread(_save_resume_text, user["id"], job_url, payload.text)
    return SaveResumeResponse(ok=True)


@router.post("/api/jobs/{encoded_url}/tailor", response_model=TailorResponse)
async def tailor_job(
    encoded_url: str,
    user: dict = Depends(get_current_user),
    validation_mode: str = Query("normal"),
) -> TailorResponse:
    tailor_limiter.check(user["id"])
    job_url = decode_url(encoded_url)
    await _ensure_job_open_or_410(job_url)
    from applypilot.scoring.tailor import tailor_job_by_url
    task_id = _start_task(tailor_job_by_url, job_url, user["id"], validation_mode)
    return TailorResponse(task_id=task_id)


@router.post("/api/jobs/{encoded_url}/favorite", response_model=FavoriteResponse)
def toggle_favorite(
    encoded_url: str, user: dict = Depends(get_current_user)
) -> FavoriteResponse:
    job_url = decode_url(encoded_url)
    conn = get_connection()
    row = conn.execute(
        "SELECT favorited FROM user_jobs WHERE user_id = ? AND job_url = ?",
        (user["id"], job_url),
    ).fetchone()
    new_val = 0 if (row and row["favorited"]) else 1
    upsert_user_job(conn, user["id"], job_url, favorited=new_val)
    return FavoriteResponse(favorited=bool(new_val))


@router.post("/api/jobs/{encoded_url}/cover", response_model=CoverResponse)
async def cover_job(
    encoded_url: str,
    user: dict = Depends(get_current_user),
    validation_mode: str = Query("normal"),
) -> CoverResponse:
    cover_limiter.check(user["id"])
    job_url = decode_url(encoded_url)
    await _ensure_job_open_or_410(job_url)
    from applypilot.scoring.cover_letter import cover_letter_by_url
    task_id = _start_task(cover_letter_by_url, job_url, user["id"], validation_mode)
    return CoverResponse(task_id=task_id)


# ---------------------------------------------------------------------------
# Status mutations
# ---------------------------------------------------------------------------

def _mark_job(user_id: int, job_url: str, status: str) -> None:
    """Update apply_status for a job in user_jobs."""
    conn = get_connection()
    if status == "restore":
        upsert_user_job(conn, user_id, job_url, apply_status=None, applied_at=None)
    else:
        upsert_user_job(
            conn, user_id, job_url,
            apply_status=status,
            applied_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
    _invalidate_stats(user_id)


@router.post("/api/jobs/{encoded_url}/mark-applied", response_model=StatusMutationResponse)
def mark_applied(
    encoded_url: str, user: dict = Depends(get_current_user)
) -> StatusMutationResponse:
    _mark_job(user["id"], decode_url(encoded_url), "applied")
    return StatusMutationResponse(ok=True, status="applied")


@router.post("/api/jobs/{encoded_url}/dismiss", response_model=StatusMutationResponse)
def dismiss_job(
    encoded_url: str, user: dict = Depends(get_current_user)
) -> StatusMutationResponse:
    _mark_job(user["id"], decode_url(encoded_url), "dismissed")
    return StatusMutationResponse(ok=True, status="dismissed")


@router.post("/api/jobs/{encoded_url}/restore", response_model=StatusMutationResponse)
def restore_job(
    encoded_url: str, user: dict = Depends(get_current_user)
) -> StatusMutationResponse:
    _mark_job(user["id"], decode_url(encoded_url), "restore")
    return StatusMutationResponse(ok=True, status="restored")


@router.post("/api/jobs/{encoded_url}/mark-status", response_model=StatusMutationResponse)
def mark_status(
    encoded_url: str,
    payload: MarkStatusRequest,
    user: dict = Depends(get_current_user),
) -> StatusMutationResponse:
    new_status = payload.status
    allowed = {"applied", "interview", "offer", "rejected"}
    if new_status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")
    _mark_job(user["id"], decode_url(encoded_url), new_status)
    return StatusMutationResponse(ok=True, status=new_status)

