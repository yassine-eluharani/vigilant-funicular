"""Jobs routes — list, detail, resume/cover, status mutations."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from applypilot.database import get_connection, upsert_user_job
from applypilot.web.auth import (
    get_current_user,
    get_user_record,
    check_and_increment_usage,
    BLUR_SCORE_THRESHOLD,
)
from applypilot.web.core import _start_task, decode_url, row_to_job

router = APIRouter(dependencies=[Depends(get_current_user)])


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/api/stats")
def stats(user: dict = Depends(get_current_user)) -> JSONResponse:
    from applypilot.database import get_stats
    user_id = user["id"]
    s = get_stats(user_id=user_id)
    conn = get_connection()
    pending = conn.execute(
        "SELECT COUNT(*) FROM user_jobs WHERE user_id = ? "
        "AND tailored_resume_path IS NOT NULL "
        "AND (apply_status IS NULL OR apply_status NOT IN ('applied','dismissed'))",
        (user_id,),
    ).fetchone()[0]
    dismissed = conn.execute(
        "SELECT COUNT(*) FROM user_jobs WHERE user_id = ? AND apply_status = 'dismissed'",
        (user_id,),
    ).fetchone()[0]
    sites = conn.execute(
        "SELECT DISTINCT j.site FROM jobs j "
        "JOIN user_jobs uj ON uj.job_url = j.url AND uj.user_id = ? "
        "WHERE uj.tailored_resume_path IS NOT NULL AND j.site IS NOT NULL ORDER BY j.site",
        (user_id,),
    ).fetchall()
    return JSONResponse({
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
    })


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

    # Base: always join jobs with user_jobs for this user
    base = (
        "FROM jobs j "
        "LEFT JOIN user_jobs uj ON uj.job_url = j.url AND uj.user_id = ? "
    )
    params: list = [user_id]

    if status == "untailored":
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

    where = " AND ".join(clauses)

    total = conn.execute(f"SELECT COUNT(*) {base} WHERE {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT j.url, j.title, j.company, j.site, j.location, j.salary, "
        f"uj.fit_score, uj.score_reasoning, "
        f"uj.tailored_resume_path, uj.cover_letter_path, uj.apply_status, uj.applied_at, "
        f"j.application_url, j.discovered_at, uj.tailored_at, COALESCE(uj.favorited, 0) as favorited "
        f"{base} WHERE {where} "
        f"ORDER BY uj.fit_score DESC, j.discovered_at DESC "
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
        "uj.tailored_resume_path, uj.tailored_at, uj.tailor_attempts, "
        "uj.cover_letter_path, uj.cover_letter_at, uj.cover_attempts, "
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

    resume_path = job.get("tailored_resume_path") or ""
    job["resume_text"] = Path(resume_path).read_text(encoding="utf-8") if resume_path and Path(resume_path).exists() else ""

    cover_path = job.get("cover_letter_path") or ""
    job["cover_letter_text"] = Path(cover_path).read_text(encoding="utf-8") if cover_path and Path(cover_path).exists() else ""

    return JSONResponse(job)


# ---------------------------------------------------------------------------
# Resume / cover letter files
# ---------------------------------------------------------------------------

@router.get("/api/resume/{encoded_url}")
def serve_resume(encoded_url: str, user: dict = Depends(get_current_user)) -> FileResponse:
    job_url = decode_url(encoded_url)
    conn = get_connection()
    row = conn.execute(
        "SELECT tailored_resume_path FROM user_jobs WHERE user_id = ? AND job_url = ?",
        (user["id"], job_url),
    ).fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="No tailored resume for this job")
    txt_path = Path(row[0])
    pdf_path = txt_path.with_suffix(".pdf")
    if pdf_path.exists():
        return FileResponse(path=str(pdf_path), media_type="application/pdf", filename=pdf_path.name)
    elif txt_path.exists():
        return FileResponse(path=str(txt_path), media_type="text/plain", filename=txt_path.name)
    raise HTTPException(status_code=404, detail="Resume file not found on disk")


@router.get("/api/cover-letter/{encoded_url}")
def serve_cover_letter(encoded_url: str, user: dict = Depends(get_current_user)) -> FileResponse:
    job_url = decode_url(encoded_url)
    conn = get_connection()
    row = conn.execute(
        "SELECT cover_letter_path FROM user_jobs WHERE user_id = ? AND job_url = ?",
        (user["id"], job_url),
    ).fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="No cover letter for this job")
    txt_path = Path(row[0])
    pdf_path = txt_path.with_suffix(".pdf")
    if pdf_path.exists():
        return FileResponse(path=str(pdf_path), media_type="application/pdf", filename=pdf_path.name)
    elif txt_path.exists():
        return FileResponse(path=str(txt_path), media_type="text/plain", filename=txt_path.name)
    raise HTTPException(status_code=404, detail="Cover letter file not found on disk")


# ---------------------------------------------------------------------------
# Resume editing
# ---------------------------------------------------------------------------

@router.put("/api/jobs/{encoded_url}/resume")
async def save_resume(encoded_url: str, request: Request, user: dict = Depends(get_current_user)) -> JSONResponse:
    job_url = decode_url(encoded_url)
    conn = get_connection()
    row = conn.execute(
        "SELECT tailored_resume_path FROM user_jobs WHERE user_id = ? AND job_url = ?",
        (user["id"], job_url),
    ).fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="No tailored resume path for this job")
    body = await request.json()
    txt_path = Path(row[0])
    txt_path.write_text(body.get("text", ""), encoding="utf-8")

    def _regen():
        try:
            from applypilot.scoring.pdf import convert_to_pdf
            convert_to_pdf(txt_path)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("PDF regen failed: %s", e)

    task_id = _start_task(_regen)
    return JSONResponse({"ok": True, "task_id": task_id})


@router.post("/api/jobs/{encoded_url}/tailor")
def tailor_job(
    encoded_url: str,
    user: dict = Depends(get_current_user),
    validation_mode: str = Query("normal"),
) -> JSONResponse:
    check_and_increment_usage(user["id"], "tailor")
    job_url = decode_url(encoded_url)
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
    check_and_increment_usage(user["id"], "cover")
    job_url = decode_url(encoded_url)
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
            applied_at=datetime.datetime.utcnow().isoformat(),
        )


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


# ---------------------------------------------------------------------------
# Database management
# ---------------------------------------------------------------------------

@router.delete("/api/database")
def purge_database() -> JSONResponse:
    conn = get_connection()
    cursor = conn.execute("DELETE FROM jobs")
    conn.execute("DELETE FROM user_jobs")
    conn.commit()
    return JSONResponse({"deleted": cursor.rowcount})
