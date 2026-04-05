"""Jobs routes — list, detail, resume/cover, status mutations."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from applypilot.database import get_connection
from applypilot.web.auth import get_current_user
from applypilot.web.core import _start_task, decode_url, row_to_job

router = APIRouter(dependencies=[Depends(get_current_user)])


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@router.get("/api/stats")
def stats() -> JSONResponse:
    from applypilot.database import get_stats
    s = get_stats()
    conn = get_connection()
    pending = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL "
        "AND (apply_status IS NULL OR apply_status NOT IN ('applied','dismissed'))"
    ).fetchone()[0]
    dismissed = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_status = 'dismissed'"
    ).fetchone()[0]
    sites = conn.execute(
        "SELECT DISTINCT site FROM jobs WHERE tailored_resume_path IS NOT NULL "
        "AND site IS NOT NULL ORDER BY site"
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
    min_score: int = Query(7, ge=1, le=10),
    max_score: int = Query(10, ge=1, le=10),
    site: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    status: str = Query("pending"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> JSONResponse:
    conn = get_connection()

    if status == "untailored":
        clauses = [
            "tailored_resume_path IS NULL",
            "fit_score >= ?",
            "fit_score <= ?",
            "full_description IS NOT NULL",
            "(apply_status IS NULL OR apply_status NOT IN ('dismissed','location_filtered'))",
        ]
    elif status == "ready":
        clauses = [
            "tailored_resume_path IS NOT NULL",
            "fit_score >= ?",
            "fit_score <= ?",
            "(apply_status IS NULL OR apply_status NOT IN "
            "('applied','dismissed','interview','offer','rejected','in_progress','manual','location_filtered'))",
        ]
    else:
        clauses = [
            "tailored_resume_path IS NOT NULL",
            "fit_score >= ?",
            "fit_score <= ?",
        ]

    params: list = [min_score, max_score]

    if status == "pending":
        clauses.append("(apply_status IS NULL OR apply_status NOT IN ('applied','dismissed'))")
    elif status == "applied":
        clauses.append("apply_status IN ('applied','interview','offer','rejected')")
    elif status == "dismissed":
        clauses.append("apply_status = 'dismissed'")

    if site:
        clauses.append("site = ?")
        params.append(site)

    if search:
        clauses.append("(title LIKE ? OR score_reasoning LIKE ? OR location LIKE ?)")
        term = f"%{search}%"
        params.extend([term, term, term])

    where = " AND ".join(clauses)

    total = conn.execute(f"SELECT COUNT(*) FROM jobs WHERE {where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT url, title, company, site, location, salary, fit_score, score_reasoning, "
        f"tailored_resume_path, cover_letter_path, apply_status, applied_at, "
        f"application_url, discovered_at, tailored_at "
        f"FROM jobs WHERE {where} "
        f"ORDER BY fit_score DESC, discovered_at DESC "
        f"LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    return JSONResponse({"jobs": [row_to_job(r) for r in rows], "total": total, "offset": offset, "limit": limit})


# ---------------------------------------------------------------------------
# Job detail
# ---------------------------------------------------------------------------

@router.get("/api/jobs/{encoded_url}")
def get_job(encoded_url: str) -> JSONResponse:
    job_url = decode_url(encoded_url)
    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (job_url,)).fetchone()
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
def serve_resume(encoded_url: str) -> FileResponse:
    job_url = decode_url(encoded_url)
    conn = get_connection()
    row = conn.execute("SELECT tailored_resume_path FROM jobs WHERE url = ?", (job_url,)).fetchone()
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
def serve_cover_letter(encoded_url: str) -> FileResponse:
    job_url = decode_url(encoded_url)
    conn = get_connection()
    row = conn.execute("SELECT cover_letter_path FROM jobs WHERE url = ?", (job_url,)).fetchone()
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
async def save_resume(encoded_url: str, request: Request) -> JSONResponse:
    job_url = decode_url(encoded_url)
    conn = get_connection()
    row = conn.execute("SELECT tailored_resume_path FROM jobs WHERE url = ?", (job_url,)).fetchone()
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
def tailor_job(encoded_url: str, validation_mode: str = Query("normal")) -> JSONResponse:
    job_url = decode_url(encoded_url)
    from applypilot.scoring.tailor import tailor_job_by_url
    task_id = _start_task(tailor_job_by_url, job_url, validation_mode)
    return JSONResponse({"task_id": task_id})


# ---------------------------------------------------------------------------
# Status mutations
# ---------------------------------------------------------------------------

@router.post("/api/jobs/{encoded_url}/mark-applied")
def mark_applied(encoded_url: str) -> JSONResponse:
    job_url = decode_url(encoded_url)
    from applypilot.apply.launcher import mark_job
    mark_job(job_url, "applied")
    return JSONResponse({"ok": True, "status": "applied"})


@router.post("/api/jobs/{encoded_url}/dismiss")
def dismiss_job(encoded_url: str) -> JSONResponse:
    job_url = decode_url(encoded_url)
    from applypilot.apply.launcher import mark_job
    mark_job(job_url, "dismissed")
    return JSONResponse({"ok": True, "status": "dismissed"})


@router.post("/api/jobs/{encoded_url}/restore")
def restore_job(encoded_url: str) -> JSONResponse:
    job_url = decode_url(encoded_url)
    from applypilot.apply.launcher import mark_job
    mark_job(job_url, "restore")
    return JSONResponse({"ok": True, "status": "restored"})


@router.post("/api/jobs/{encoded_url}/mark-status")
async def mark_status(encoded_url: str, request: Request) -> JSONResponse:
    job_url = decode_url(encoded_url)
    body = await request.json()
    new_status = body.get("status", "")
    allowed = {"applied", "interview", "offer", "rejected"}
    if new_status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")
    from applypilot.apply.launcher import mark_job
    mark_job(job_url, new_status)
    return JSONResponse({"ok": True, "status": new_status})


# ---------------------------------------------------------------------------
# Database management
# ---------------------------------------------------------------------------

@router.delete("/api/database")
def purge_database() -> JSONResponse:
    conn = get_connection()
    cursor = conn.execute("DELETE FROM jobs")
    conn.commit()
    return JSONResponse({"deleted": cursor.rowcount})
