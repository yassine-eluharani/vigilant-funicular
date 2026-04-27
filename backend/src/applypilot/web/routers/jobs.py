"""Jobs routes — list, detail, resume/cover, status mutations."""

from __future__ import annotations

import datetime
import time as _time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from applypilot.database import (
    get_connection,
    upsert_user_job,
    batch_query,
    mark_job_closed,
    mark_liveness_checked,
)
from applypilot.enrichment.liveness import verify_job_open
from applypilot.web.auth import (
    get_current_user,
    get_user_record,
    check_and_increment_usage,
    BLUR_SCORE_THRESHOLD,
)
from applypilot.web.core import _start_task, decode_url, row_to_job, tailor_limiter, cover_limiter

router = APIRouter(dependencies=[Depends(get_current_user)])

# Stats cache: user_id → (computed_at, payload_dict)
_stats_cache: dict[int, tuple[float, dict]] = {}
_STATS_TTL = 30.0  # seconds


def _ensure_job_open_or_410(job_url: str) -> None:
    """Block tailor / cover-letter when the posting is verified closed.

    Raises HTTP 410 Gone with a clear message so the frontend can show a toast
    and we don't burn an LLM call or the user's monthly tailor count on a
    dead listing. If the job was already marked closed previously, fail fast
    without re-fetching.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT closed_at FROM jobs WHERE url = ?", (job_url,)
    ).fetchone()
    if row and row["closed_at"]:
        raise HTTPException(
            status_code=410,
            detail="This job posting is no longer open. It will be removed shortly.",
        )
    status = verify_job_open(job_url, timeout=5.0)
    if status == "closed":
        mark_job_closed(conn, job_url, reason="verified_closed_pre_tailor")
        raise HTTPException(
            status_code=410,
            detail="This job posting is no longer accepting applications.",
        )
    if status == "open":
        mark_liveness_checked(conn, job_url)
    # status == "unknown" → don't block; preserve user flow on transient errors.


def _invalidate_stats(user_id: int) -> None:
    """Drop the cached stats for a user so the next request recomputes."""
    _stats_cache.pop(user_id, None)
    from applypilot.web.core import notify_user
    notify_user(user_id, "stats_changed")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/api/stats")
def stats(user: dict = Depends(get_current_user)) -> JSONResponse:
    from applypilot.database import get_stats
    user_id = user["id"]

    cached = _stats_cache.get(user_id)
    if cached and _time.monotonic() - cached[0] < _STATS_TTL:
        return JSONResponse(cached[1])

    s = get_stats(user_id=user_id)
    conn = get_connection()
    is_free = user["tier"] == "free"

    # Batch the 4 extra queries that the router needs beyond get_stats()
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
        (
            "SELECT COUNT(*) FROM user_jobs WHERE user_id = ? AND fit_score >= ? "
            "AND (apply_status IS NULL OR apply_status NOT IN ('dismissed','location_filtered'))",
            (user_id, BLUR_SCORE_THRESHOLD) if is_free else (user_id, 999),
        ),
    ]
    er = batch_query(conn, extra_stmts)
    pending      = er[0].fetchone()[0]
    dismissed    = er[1].fetchone()[0]
    sites        = er[2].fetchall()
    locked_count = er[3].fetchone()[0] if is_free else 0

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
        "locked_count": locked_count,
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
    return JSONResponse(payload)


# ---------------------------------------------------------------------------
# Job listing
# ---------------------------------------------------------------------------

@router.get("/api/jobs")
def list_jobs(
    user: dict = Depends(get_current_user),
    min_score: int = Query(7, ge=1, le=10),
    max_score: int = Query(10, ge=1, le=10),
    site: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    status: str = Query("pending"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> JSONResponse:
    conn = get_connection()
    user_id = user["id"]

    # Base: always join jobs with user_jobs for this user.
    # Closed jobs are excluded from every list view (verified dead postings
    # are useless to the user — only kept around for the grace-period cleanup).
    base = (
        "FROM jobs j "
        "LEFT JOIN user_jobs uj ON uj.job_url = j.url AND uj.user_id = ? "
    )
    params: list = [user_id]

    if status == "scored":
        # All scored jobs — no tailoring requirement, respects score range
        clauses = [
            "uj.fit_score IS NOT NULL",
            "uj.fit_score >= ?",
            "uj.fit_score <= ?",
            "(uj.apply_status IS NULL OR uj.apply_status NOT IN ('dismissed','location_filtered'))",
        ]
    elif status == "untailored":
        clauses = [
            "uj.tailored_resume_path IS NULL",
            "uj.fit_score >= ?",
            "uj.fit_score <= ?",
            "j.full_description IS NOT NULL",
            "(uj.apply_status IS NULL OR uj.apply_status NOT IN ('dismissed','location_filtered'))",
        ]
    elif status == "ready":
        clauses = [
            "uj.tailored_resume_path IS NOT NULL",
            "uj.fit_score >= ?",
            "uj.fit_score <= ?",
            "(uj.apply_status IS NULL OR uj.apply_status NOT IN "
            "('applied','dismissed','interview','offer','rejected','in_progress','manual','location_filtered'))",
        ]
    elif status == "favorites":
        clauses = [
            "COALESCE(uj.favorited, 0) = 1",
            "uj.fit_score >= ?",
            "uj.fit_score <= ?",
        ]
    else:
        clauses = [
            "uj.tailored_resume_path IS NOT NULL",
            "uj.fit_score >= ?",
            "uj.fit_score <= ?",
        ]

    params.extend([min_score, max_score])

    if status == "pending":
        clauses.append("(uj.apply_status IS NULL OR uj.apply_status NOT IN ('applied','dismissed'))")
    elif status == "applied":
        clauses.append("uj.apply_status IN ('applied','interview','offer','rejected')")
    elif status == "dismissed":
        clauses.append("uj.apply_status = 'dismissed'")

    if site:
        clauses.append("j.site = ?")
        params.append(site)

    if search:
        clauses.append("(j.title LIKE ? OR uj.score_reasoning LIKE ? OR j.location LIKE ?)")
        term = f"%{search}%"
        params.extend([term, term, term])

    # Always hide jobs we've verified as closed
    clauses.append("j.closed_at IS NULL")

    where = " AND ".join(clauses)

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

    # Apply free-tier blur
    is_free = user["tier"] == "free"

    jobs_out = []
    for r in rows:
        job = row_to_job(r)
        if is_free and (job.get("fit_score") or 0) >= BLUR_SCORE_THRESHOLD:
            job["locked"] = True
            job["company"] = None
            job["score_reasoning"] = None
            job["application_url"] = None
            job["has_pdf"] = False
            job["has_cover_pdf"] = False
        else:
            job["locked"] = False
        jobs_out.append(job)

    return JSONResponse({"jobs": jobs_out, "total": total, "offset": offset, "limit": limit})


# ---------------------------------------------------------------------------
# Job detail
# ---------------------------------------------------------------------------

@router.get("/api/jobs/{encoded_url}")
def get_job(encoded_url: str, user: dict = Depends(get_current_user)) -> JSONResponse:
    job_url = decode_url(encoded_url)
    conn = get_connection()
    user_id = user["id"]

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
        raise HTTPException(status_code=404, detail="Job not found")
    job = row_to_job(row)

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
                status = verify_job_open(job_url, timeout=5.0)
                if status == "closed":
                    mark_job_closed(conn, job_url, reason="verified_closed_on_view")
                    job["closed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    job["closed_reason"] = "verified_closed_on_view"
                elif status == "open":
                    mark_liveness_checked(conn, job_url)
            except Exception:
                pass

    job["closed"] = bool(job.get("closed_at"))

    # Resume and cover letter text from DB
    job["resume_text"] = job.get("tailored_resume_text") or ""
    job["cover_letter_text"] = job.get("cover_letter_text") or ""

    return JSONResponse(job)


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
    except Exception as e:
        # Don't silently return text/plain — the browser saves whatever blob it
        # gets as a .pdf, producing an unopenable file. Surface the failure.
        log = __import__("logging").getLogger(__name__)
        log.exception("PDF generation failed for resume: %s", e)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
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
    except Exception as e:
        log = __import__("logging").getLogger(__name__)
        log.exception("PDF generation failed for cover letter: %s", e)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=cover_letter.pdf"})


# ---------------------------------------------------------------------------
# Resume editing
# ---------------------------------------------------------------------------

@router.put("/api/jobs/{encoded_url}/resume")
async def save_resume(encoded_url: str, request: Request, user: dict = Depends(get_current_user)) -> JSONResponse:
    job_url = decode_url(encoded_url)
    conn = get_connection()
    body = await request.json()
    text = body.get("text", "")
    upsert_user_job(conn, user["id"], job_url, tailored_resume_text=text)
    return JSONResponse({"ok": True})


@router.post("/api/jobs/{encoded_url}/tailor")
def tailor_job(
    encoded_url: str,
    user: dict = Depends(get_current_user),
    validation_mode: str = Query("normal"),
) -> JSONResponse:
    tailor_limiter.check(user["id"])
    job_url = decode_url(encoded_url)
    _ensure_job_open_or_410(job_url)
    # Only count usage after we've confirmed the posting is still open.
    check_and_increment_usage(user["id"], "tailor")
    from applypilot.scoring.tailor import tailor_job_by_url
    task_id = _start_task(tailor_job_by_url, job_url, user["id"], validation_mode)
    return JSONResponse({"task_id": task_id})


@router.post("/api/jobs/{encoded_url}/favorite")
def toggle_favorite(encoded_url: str, user: dict = Depends(get_current_user)) -> JSONResponse:
    job_url = decode_url(encoded_url)
    conn = get_connection()
    row = conn.execute(
        "SELECT favorited FROM user_jobs WHERE user_id = ? AND job_url = ?",
        (user["id"], job_url),
    ).fetchone()
    new_val = 0 if (row and row["favorited"]) else 1
    upsert_user_job(conn, user["id"], job_url, favorited=new_val)
    return JSONResponse({"favorited": bool(new_val)})


@router.post("/api/jobs/{encoded_url}/cover")
def cover_job(
    encoded_url: str,
    user: dict = Depends(get_current_user),
    validation_mode: str = Query("normal"),
) -> JSONResponse:
    cover_limiter.check(user["id"])
    job_url = decode_url(encoded_url)
    _ensure_job_open_or_410(job_url)
    check_and_increment_usage(user["id"], "cover")
    from applypilot.scoring.cover_letter import cover_letter_by_url
    task_id = _start_task(cover_letter_by_url, job_url, user["id"], validation_mode)
    return JSONResponse({"task_id": task_id})


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


@router.post("/api/jobs/{encoded_url}/mark-applied")
def mark_applied(encoded_url: str, user: dict = Depends(get_current_user)) -> JSONResponse:
    _mark_job(user["id"], decode_url(encoded_url), "applied")
    return JSONResponse({"ok": True, "status": "applied"})


@router.post("/api/jobs/{encoded_url}/dismiss")
def dismiss_job(encoded_url: str, user: dict = Depends(get_current_user)) -> JSONResponse:
    _mark_job(user["id"], decode_url(encoded_url), "dismissed")
    return JSONResponse({"ok": True, "status": "dismissed"})


@router.post("/api/jobs/{encoded_url}/restore")
def restore_job(encoded_url: str, user: dict = Depends(get_current_user)) -> JSONResponse:
    _mark_job(user["id"], decode_url(encoded_url), "restore")
    return JSONResponse({"ok": True, "status": "restored"})


@router.post("/api/jobs/{encoded_url}/mark-status")
async def mark_status(encoded_url: str, request: Request, user: dict = Depends(get_current_user)) -> JSONResponse:
    body = await request.json()
    new_status = body.get("status", "")
    allowed = {"applied", "interview", "offer", "rejected"}
    if new_status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")
    _mark_job(user["id"], decode_url(encoded_url), new_status)
    return JSONResponse({"ok": True, "status": new_status})

