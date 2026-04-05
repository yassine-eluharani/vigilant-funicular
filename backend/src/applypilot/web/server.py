"""ApplyPilot Web API — FastAPI backend."""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from applypilot.config import PROFILE_PATH, SEARCH_CONFIG_PATH, CONFIG_DIR

EMPLOYERS_PATH = CONFIG_DIR / "employers.yaml"
from applypilot.database import get_connection

log = logging.getLogger(__name__)

app = FastAPI(title="ApplyPilot API", docs_url="/api/docs", redoc_url=None)

_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Background task registry
# ---------------------------------------------------------------------------

_tasks: dict[str, dict[str, Any]] = {}
_MAX_LOG_LINES = 300


class _TaskLogHandler(logging.Handler):
    """Captures log records and appends them to a task's log_lines list."""

    def __init__(self, lines: list[str]) -> None:
        super().__init__()
        self._lines = lines
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._lines.append(self.format(record))
            if len(self._lines) > _MAX_LOG_LINES:
                self._lines.pop(0)
        except Exception:
            pass


def _run_task(task_id: str, fn, *args) -> None:
    log_lines: list[str] = _tasks[task_id]["log_lines"]
    handler = _TaskLogHandler(log_lines)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        _tasks[task_id]["status"] = "running"
        result = fn(*args)
        _tasks[task_id].update({"status": "done", "result": result})
    except Exception as exc:
        _tasks[task_id].update({"status": "error", "error": str(exc)})
    finally:
        root.removeHandler(handler)


def _start_task(fn, *args) -> str:
    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {"status": "pending", "result": None, "error": None, "log_lines": []}
    threading.Thread(target=_run_task, args=(task_id, fn, *args), daemon=True).start()
    return task_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode_url(url: str) -> str:
    return base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


def _decode_url(encoded: str) -> str:
    try:
        padded = encoded + "=" * (4 - len(encoded) % 4)
        return base64.urlsafe_b64decode(padded.encode()).decode()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid encoded URL")


def _row_to_job(row) -> dict:
    d = dict(row)
    # Sanitize fields that may be stored as the Python string "None"
    for field in ("application_url", "location", "salary"):
        if d.get(field) in ("None", ""):
            d[field] = None
    path = d.get("tailored_resume_path") or ""
    if path:
        p = Path(path)
        d["has_pdf"] = p.with_suffix(".pdf").exists()
    else:
        d["has_pdf"] = False
    cover = d.get("cover_letter_path") or ""
    if cover:
        cp = Path(cover)
        d["has_cover_pdf"] = cp.with_suffix(".pdf").exists()
    else:
        d["has_cover_pdf"] = bool(cover)
    d["url_encoded"] = _encode_url(d["url"]) if d.get("url") else ""
    return d


# ---------------------------------------------------------------------------
# Routes — Stats
# ---------------------------------------------------------------------------

@app.get("/api/stats")
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
        # header counts (kept for backwards compat)
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
        # full funnel
        "funnel": {
            "discovered":       s["total"],
            "pending_enrich":   s["pending_enrich"],
            "enriched":         s["with_description"],
            "pending_filter":   s["pending_filter"],
            "location_filtered": s["location_filtered"],
            "scored":           s["scored"],
            "pending_score":    s["unscored"],
            "tailored":         s["tailored"],
            "pending_tailor":   s["untailored_eligible"],
            "cover":            s["with_cover_letter"],
            "pending_cover":    max(0, s["tailored"] - s["with_cover_letter"]),
            "ready_to_apply":   s["ready_to_apply"],
            "applied":          s["applied"],
            "interviews":       s["interviews"],
            "offers":           s["offers"],
            "rejected_count":   s["rejected"],
            "apply_errors":     s["apply_errors"],
        },
    })


# ---------------------------------------------------------------------------
# Routes — Jobs
# ---------------------------------------------------------------------------

@app.get("/api/jobs")
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
        clauses.append(
            "(apply_status IS NULL OR apply_status NOT IN ('applied','dismissed'))"
        )
    elif status == "applied":
        clauses.append(
            "apply_status IN ('applied','interview','offer','rejected')"
        )
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

    total = conn.execute(
        f"SELECT COUNT(*) FROM jobs WHERE {where}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"SELECT url, title, company, site, location, salary, fit_score, score_reasoning, "
        f"tailored_resume_path, cover_letter_path, apply_status, applied_at, "
        f"application_url, discovered_at, tailored_at "
        f"FROM jobs WHERE {where} "
        f"ORDER BY fit_score DESC, discovered_at DESC "
        f"LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    return JSONResponse({
        "jobs": [_row_to_job(r) for r in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    })


@app.get("/api/resume/{encoded_url}")
def serve_resume(encoded_url: str) -> FileResponse:
    job_url = _decode_url(encoded_url)
    conn = get_connection()
    row = conn.execute(
        "SELECT tailored_resume_path FROM jobs WHERE url = ?", (job_url,)
    ).fetchone()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="No tailored resume for this job")

    txt_path = Path(row[0])
    pdf_path = txt_path.with_suffix(".pdf")

    if pdf_path.exists():
        return FileResponse(path=str(pdf_path), media_type="application/pdf", filename=pdf_path.name)
    elif txt_path.exists():
        return FileResponse(path=str(txt_path), media_type="text/plain", filename=txt_path.name)
    else:
        raise HTTPException(status_code=404, detail="Resume file not found on disk")


@app.post("/api/jobs/{encoded_url}/mark-applied")
def mark_applied(encoded_url: str) -> JSONResponse:
    job_url = _decode_url(encoded_url)
    from applypilot.apply.launcher import mark_job
    mark_job(job_url, "applied")
    return JSONResponse({"ok": True, "status": "applied"})


@app.post("/api/jobs/{encoded_url}/dismiss")
def dismiss_job(encoded_url: str) -> JSONResponse:
    job_url = _decode_url(encoded_url)
    from applypilot.apply.launcher import mark_job
    mark_job(job_url, "dismissed")
    return JSONResponse({"ok": True, "status": "dismissed"})


@app.get("/api/cover-letter/{encoded_url}")
def serve_cover_letter(encoded_url: str) -> FileResponse:
    job_url = _decode_url(encoded_url)
    conn = get_connection()
    row = conn.execute(
        "SELECT cover_letter_path FROM jobs WHERE url = ?", (job_url,)
    ).fetchone()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="No cover letter for this job")

    txt_path = Path(row[0])
    pdf_path = txt_path.with_suffix(".pdf")

    if pdf_path.exists():
        return FileResponse(path=str(pdf_path), media_type="application/pdf", filename=pdf_path.name)
    elif txt_path.exists():
        return FileResponse(path=str(txt_path), media_type="text/plain", filename=txt_path.name)
    else:
        raise HTTPException(status_code=404, detail="Cover letter file not found on disk")


@app.post("/api/jobs/{encoded_url}/mark-status")
async def mark_status(encoded_url: str, request: Request) -> JSONResponse:
    job_url = _decode_url(encoded_url)
    body = await request.json()
    new_status = body.get("status", "")
    allowed = {"applied", "interview", "offer", "rejected"}
    if new_status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")
    from applypilot.apply.launcher import mark_job
    mark_job(job_url, new_status)
    return JSONResponse({"ok": True, "status": new_status})


@app.post("/api/jobs/{encoded_url}/restore")
def restore_job(encoded_url: str) -> JSONResponse:
    job_url = _decode_url(encoded_url)
    from applypilot.apply.launcher import mark_job
    mark_job(job_url, "restore")
    return JSONResponse({"ok": True, "status": "restored"})


@app.get("/api/jobs/{encoded_url}")
def get_job(encoded_url: str) -> JSONResponse:
    job_url = _decode_url(encoded_url)
    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (job_url,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _row_to_job(row)

    # Read resume text
    resume_path = job.get("tailored_resume_path") or ""
    if resume_path:
        txt = Path(resume_path)
        job["resume_text"] = txt.read_text(encoding="utf-8") if txt.exists() else ""
    else:
        job["resume_text"] = ""

    # Read cover letter text
    cover_path = job.get("cover_letter_path") or ""
    if cover_path:
        ctxt = Path(cover_path)
        job["cover_letter_text"] = ctxt.read_text(encoding="utf-8") if ctxt.exists() else ""
    else:
        job["cover_letter_text"] = ""

    return JSONResponse(job)


@app.put("/api/jobs/{encoded_url}/resume")
async def save_resume(encoded_url: str, request: Request) -> JSONResponse:
    job_url = _decode_url(encoded_url)
    conn = get_connection()
    row = conn.execute("SELECT tailored_resume_path FROM jobs WHERE url = ?", (job_url,)).fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="No tailored resume path for this job")
    body = await request.json()
    text = body.get("text", "")
    txt_path = Path(row[0])
    txt_path.write_text(text, encoding="utf-8")
    # Regenerate PDF in background
    def _regen():
        try:
            from applypilot.scoring.pdf import convert_to_pdf
            convert_to_pdf(txt_path)
        except Exception as e:
            log.warning("PDF regen failed: %s", e)
    task_id = _start_task(_regen)
    return JSONResponse({"ok": True, "task_id": task_id})


@app.post("/api/jobs/{encoded_url}/tailor")
def tailor_job(encoded_url: str, validation_mode: str = Query("normal")) -> JSONResponse:
    job_url = _decode_url(encoded_url)
    from applypilot.scoring.tailor import tailor_job_by_url
    task_id = _start_task(tailor_job_by_url, job_url, validation_mode)
    return JSONResponse({"task_id": task_id})


# ---------------------------------------------------------------------------
# Routes — Profile
# ---------------------------------------------------------------------------

@app.get("/api/profile")
def get_profile() -> JSONResponse:
    if not PROFILE_PATH.exists():
        raise HTTPException(status_code=404, detail="Profile not found. Run 'applypilot init' first.")
    data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    return JSONResponse(data)


@app.put("/api/profile")
async def update_profile(request: Request) -> JSONResponse:
    data = await request.json()
    PROFILE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Routes — Searches config
# ---------------------------------------------------------------------------

@app.get("/api/config/searches")
def get_searches() -> JSONResponse:
    if not SEARCH_CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="searches.yaml not found.")
    data = yaml.safe_load(SEARCH_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    # Inject defaults for description_reject_patterns if not set in the file
    if "description_reject_patterns" not in data:
        from applypilot.discovery.filter import DEFAULT_REJECT_PATTERNS
        data["description_reject_patterns"] = DEFAULT_REJECT_PATTERNS
    return JSONResponse(data)


@app.put("/api/config/searches")
async def update_searches(request: Request) -> JSONResponse:
    data = await request.json()
    SEARCH_CONFIG_PATH.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Routes — Employers (Workday registry)
# ---------------------------------------------------------------------------

@app.get("/api/config/employers")
def get_employers() -> JSONResponse:
    if not EMPLOYERS_PATH.exists():
        return JSONResponse({})
    data = yaml.safe_load(EMPLOYERS_PATH.read_text(encoding="utf-8")) or {}
    return JSONResponse(data.get("employers", {}))


@app.put("/api/config/employers")
async def update_employers(request: Request) -> JSONResponse:
    employers = await request.json()
    existing = {}
    if EMPLOYERS_PATH.exists():
        existing = yaml.safe_load(EMPLOYERS_PATH.read_text(encoding="utf-8")) or {}
    existing["employers"] = employers
    EMPLOYERS_PATH.write_text(
        yaml.dump(existing, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Routes — Pipeline
# ---------------------------------------------------------------------------

def _do_run_pipeline(stages: list[str], min_score: int, workers: int,
                     validation: str, stream: bool) -> dict:
    from applypilot.pipeline import run_pipeline
    return run_pipeline(
        stages=stages,
        min_score=min_score,
        workers=workers,
        validation_mode=validation,
        stream=stream,
    )


@app.post("/api/pipeline/run")
async def pipeline_run(request: Request) -> JSONResponse:
    body = await request.json()
    stages = body.get("stages", ["discover", "enrich", "score"])
    min_score = int(body.get("min_score", 7))
    workers = int(body.get("workers", 1))
    validation = body.get("validation", "normal")
    stream = bool(body.get("stream", False))
    task_id = _start_task(_do_run_pipeline, stages, min_score, workers, validation, stream)
    return JSONResponse({"task_id": task_id})


# ---------------------------------------------------------------------------
# Routes — Tasks
# ---------------------------------------------------------------------------

@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, since: int = Query(0, ge=0)) -> JSONResponse:
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    all_lines = task.get("log_lines", [])
    new_lines = all_lines[since:]
    return JSONResponse({
        "status": task["status"],
        "result": task.get("result"),
        "error": task.get("error"),
        "log_lines": new_lines,
        "log_total": len(all_lines),
    })


# ---------------------------------------------------------------------------
# Routes — Database
# ---------------------------------------------------------------------------

@app.delete("/api/database")
def purge_database() -> JSONResponse:
    conn = get_connection()
    cursor = conn.execute("DELETE FROM jobs")
    conn.commit()
    return JSONResponse({"deleted": cursor.rowcount})



# ---------------------------------------------------------------------------
# Routes — SSE streaming
# ---------------------------------------------------------------------------

import asyncio
import time as _time
from fastapi.responses import StreamingResponse


@app.get("/api/stream/task/{task_id}")
async def stream_task_logs(task_id: str):
    """Server-Sent Events: stream log lines for a background task until done."""

    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    async def _generate():
        sent = 0
        while True:
            task = _tasks.get(task_id)
            if not task:
                break
            lines = task.get("log_lines", [])
            new_lines = lines[sent:]
            for line in new_lines:
                # Escape SSE-special characters in log lines
                safe = line.replace("\n", " ").replace("\r", "")
                yield f"data: {safe}\n\n"
                sent += 1
            status = task.get("status", "pending")
            if status in ("done", "error"):
                yield f"event: status\ndata: {status}\n\n"
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@app.get("/api/stream/apply")
async def stream_apply_status():
    """Server-Sent Events: stream apply worker states every 500ms."""

    async def _generate():
        import dataclasses
        from applypilot.apply import dashboard as _dash

        while True:
            with _dash._lock:
                workers = [
                    dataclasses.asdict(s) for s in _dash._worker_states.values()
                ]
                events = list(_dash._events)
            totals = _dash.get_totals()

            # Strip Rich markup from event strings
            import re
            clean_events = [re.sub(r"\[.*?\]", "", e) for e in events]

            payload = json.dumps({
                "workers": workers,
                "events": clean_events,
                "totals": totals,
            })
            yield f"data: {payload}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Routes — Apply workers
# ---------------------------------------------------------------------------

# Module-level flag file path for stop signalling (process-safe)
import multiprocessing as _mp

_apply_process: Optional[_mp.Process] = None
_apply_stop_flag: _mp.Value = _mp.Value("b", 0)


@app.get("/api/apply/status")
def apply_status() -> JSONResponse:
    """Current snapshot of all apply worker states."""
    import dataclasses
    from applypilot.apply import dashboard as _dash

    with _dash._lock:
        workers = [dataclasses.asdict(s) for s in _dash._worker_states.values()]
        events_raw = list(_dash._events)

    import re
    clean_events = [re.sub(r"\[.*?\]", "", e) for e in events_raw]

    return JSONResponse({
        "running": _apply_process is not None and _apply_process.is_alive(),
        "workers": workers,
        "events": clean_events,
        "totals": _dash.get_totals(),
    })


def _run_apply_workers(workers: int, limit: int, min_score: int,
                       headless: bool, continuous: bool, model: str) -> None:
    """Target for the apply subprocess. Runs in an isolated process."""
    from applypilot.config import load_env, ensure_dirs
    from applypilot.database import init_db
    load_env()
    ensure_dirs()
    init_db()
    from applypilot.apply.launcher import apply_jobs
    apply_jobs(
        workers=workers,
        continuous=continuous,
        headless=headless,
        limit=limit if limit > 0 else None,
        min_score=min_score,
        model=model or None,
    )


@app.post("/api/apply/start")
async def start_apply(request: Request) -> JSONResponse:
    """Start apply workers in a background process."""
    global _apply_process, _apply_stop_flag

    if _apply_process is not None and _apply_process.is_alive():
        return JSONResponse({"ok": False, "error": "Apply workers already running"}, status_code=409)

    body = await request.json()
    workers = int(body.get("workers", 1))
    limit = int(body.get("limit", 0))
    min_score = int(body.get("min_score", 7))
    headless = bool(body.get("headless", True))
    continuous = bool(body.get("continuous", False))
    model = str(body.get("model", ""))

    _apply_stop_flag.value = 0
    _apply_process = _mp.Process(
        target=_run_apply_workers,
        args=(workers, limit, min_score, headless, continuous, model),
        daemon=True,
    )
    _apply_process.start()
    return JSONResponse({"ok": True, "pid": _apply_process.pid})


@app.post("/api/apply/stop")
def stop_apply() -> JSONResponse:
    """Signal apply workers to stop gracefully."""
    global _apply_process, _apply_stop_flag

    if _apply_process is None or not _apply_process.is_alive():
        return JSONResponse({"ok": False, "error": "No apply workers running"}, status_code=409)

    _apply_stop_flag.value = 1
    # Give workers 5s to stop gracefully then terminate
    _apply_process.join(timeout=5)
    if _apply_process.is_alive():
        _apply_process.terminate()
    _apply_process = None
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Routes — Config (env keys, resume)
# ---------------------------------------------------------------------------

from applypilot.config import APP_DIR


@app.get("/api/config/env")
def get_env_config() -> JSONResponse:
    """Read .env keys with values masked."""
    env_path = APP_DIR / ".env"
    keys = {
        "GEMINI_API_KEY": None,
        "OPENAI_API_KEY": None,
        "LLM_URL": None,
        "LLM_MODEL": None,
        "CAPSOLVER_API_KEY": None,
    }
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k in keys:
                    # Return actual value for non-secret keys; mask secrets
                    if k in ("LLM_URL", "LLM_MODEL"):
                        keys[k] = v or None
                    else:
                        keys[k] = "***" if v else None
    return JSONResponse(keys)


@app.put("/api/config/env")
async def update_env_config(request: Request) -> JSONResponse:
    """Write/update API key values in .env."""
    data = await request.json()
    env_path = APP_DIR / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing lines
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()

    # Merge updates (empty string = delete key)
    for k, v in data.items():
        if v == "" or v is None:
            existing.pop(k, None)
        else:
            existing[k] = v

    # Write back
    env_path.write_text(
        "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n",
        encoding="utf-8",
    )
    return JSONResponse({"ok": True})


@app.get("/api/config/resume")
def get_resume_text() -> JSONResponse:
    """Read master resume.txt content."""
    from applypilot.config import RESUME_PATH
    if not RESUME_PATH.exists():
        return JSONResponse({"text": "", "exists": False})
    return JSONResponse({"text": RESUME_PATH.read_text(encoding="utf-8"), "exists": True})


@app.put("/api/config/resume")
async def update_resume_text(request: Request) -> JSONResponse:
    """Write master resume.txt content."""
    from applypilot.config import RESUME_PATH
    body = await request.json()
    RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESUME_PATH.write_text(body.get("text", ""), encoding="utf-8")
    return JSONResponse({"ok": True})


@app.post("/api/config/resume/upload")
async def upload_resume_pdf(request: Request) -> JSONResponse:
    """Upload resume.pdf (multipart/form-data)."""
    from fastapi import UploadFile, File
    from applypilot.config import APP_DIR

    # Parse multipart manually via starlette
    form = await request.form()
    file: UploadFile = form.get("file")  # type: ignore
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    dest = APP_DIR / "resume.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    dest.write_bytes(content)

    # Extract text in background
    task_id = _start_task(_extract_resume_text, dest)
    return JSONResponse({"ok": True, "size": len(content), "task_id": task_id})


def _extract_resume_text(pdf_path: Path) -> dict:
    """Extract text from uploaded resume PDF → save as resume.txt."""
    from applypilot.config import RESUME_PATH
    try:
        import subprocess
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            RESUME_PATH.write_text(result.stdout, encoding="utf-8")
            return {"extracted": True, "chars": len(result.stdout)}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return {"extracted": False}


# ---------------------------------------------------------------------------
# Routes — System status
# ---------------------------------------------------------------------------

@app.get("/api/system/status")
def system_status() -> JSONResponse:
    """Return current tier, LLM provider, and available capabilities."""
    import shutil
    from applypilot.config import get_tier
    from applypilot.llm import _detect_provider

    tier = get_tier()
    tier_labels = {
        1: "Discovery Only",
        2: "AI Scoring & Tailoring",
        3: "Full Auto-Apply",
    }

    provider, model, _api_key = _detect_provider()

    has_chrome = bool(shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser"))
    has_claude_cli = bool(shutil.which("claude"))

    return JSONResponse({
        "tier": tier,
        "tier_label": tier_labels.get(tier, "Unknown"),
        "llm_provider": provider,
        "llm_model": model,
        "has_chrome": has_chrome,
        "has_claude_cli": has_claude_cli,
    })
