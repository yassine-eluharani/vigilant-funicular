"""ApplyPilot Live Web Dashboard — FastAPI server + React SPA."""

from __future__ import annotations

import base64
import json
import logging
import threading
import uuid
import webbrowser
from pathlib import Path
from threading import Timer
from typing import Any, Optional

import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from applypilot.config import PROFILE_PATH, SEARCH_CONFIG_PATH, CONFIG_DIR

EMPLOYERS_PATH = CONFIG_DIR / "employers.yaml"
from applypilot.database import get_connection

log = logging.getLogger(__name__)

app = FastAPI(title="ApplyPilot Dashboard", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
# Routes — SPA
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    return HTMLResponse(content=_DASHBOARD_HTML)


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
# Server startup
# ---------------------------------------------------------------------------

def start_server(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """Start the uvicorn server and optionally open the browser."""
    import uvicorn

    if open_browser:
        Timer(1.2, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    log.info("Starting ApplyPilot dashboard at http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port, log_level="warning")


# ---------------------------------------------------------------------------
# React SPA (inline, no build step — React 18 + Tailwind via CDN)
# ---------------------------------------------------------------------------

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>ApplyPilot Dashboard</title>
  <script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    /* ── Base (dark) ── */
    :root { --ap-bg: #0f172a; }
    body { background-color: var(--ap-bg); color: #f1f5f9; font-family: system-ui, sans-serif; }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #1e293b; }
    ::-webkit-scrollbar-thumb { background: #475569; border-radius: 3px; }
    input[type=range] { accent-color: #3b82f6; }
    .card-enter { animation: fadeIn 0.2s ease-out; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
    .skeleton { animation: shimmer 1.5s ease-in-out infinite; background: linear-gradient(90deg, #1e293b 25%, #273549 50%, #1e293b 75%); background-size: 200% 100%; }
    @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
    .spin { animation: spin 1s linear infinite; display: inline-block; }
    @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

    /* ── Light mode overrides ── */
    :root.light { --ap-bg: #f1f5f9; }
    .light body { background-color: #f1f5f9; color: #0f172a; }
    .light ::-webkit-scrollbar-track { background: #e2e8f0; }
    .light ::-webkit-scrollbar-thumb { background: #94a3b8; }
    .light .skeleton { background: linear-gradient(90deg, #e2e8f0 25%, #f8fafc 50%, #e2e8f0 75%); }

    /* backgrounds */
    .light .bg-slate-900  { background-color: #f1f5f9 !important; }
    .light .bg-slate-800  { background-color: #ffffff !important; }
    .light .bg-slate-700  { background-color: #e2e8f0 !important; }
    .light .bg-slate-600  { background-color: #cbd5e1 !important; }
    .light .bg-slate-800\/50 { background-color: rgba(255,255,255,0.6) !important; }

    /* text */
    .light .text-slate-100 { color: #0f172a !important; }
    .light .text-slate-200 { color: #1e293b !important; }
    .light .text-slate-300 { color: #334155 !important; }
    .light .text-slate-400 { color: #475569 !important; }
    .light .text-slate-500 { color: #64748b !important; }
    .light .text-slate-600 { color: #94a3b8 !important; }

    /* borders */
    .light .border-slate-900 { border-color: #e2e8f0 !important; }
    .light .border-slate-800 { border-color: #e2e8f0 !important; }
    .light .border-slate-700 { border-color: #cbd5e1 !important; }
    .light .border-slate-600 { border-color: #94a3b8 !important; }

    /* hover states */
    .light .hover\:bg-slate-700:hover  { background-color: #e2e8f0 !important; }
    .light .hover\:bg-slate-800:hover  { background-color: #f1f5f9 !important; }
    .light .hover\:border-slate-500:hover { border-color: #94a3b8 !important; }
    .light .hover\:text-slate-200:hover   { color: #1e293b !important; }

    /* form elements */
    .light input, .light textarea, .light select {
      color: #0f172a !important;
      background-color: #ffffff !important;
      border-color: #cbd5e1 !important;
    }
    .light input::placeholder, .light textarea::placeholder { color: #94a3b8 !important; }
    .light option { background-color: #ffffff; color: #0f172a; }

    /* divide */
    .light .divide-slate-700 > * + * { border-color: #e2e8f0 !important; }
  </style>
</head>
<body>
<div id="root"></div>

<script type="text/babel">
const { useState, useEffect, useCallback, useRef } = React;

// ── Shared UI ─────────────────────────────────────────────────────────────

function ScoreBadge({ score }) {
  const c = score >= 9 ? 'bg-emerald-500' : score === 8 ? 'bg-teal-500' : score === 7 ? 'bg-blue-500' : score >= 5 ? 'bg-amber-500' : 'bg-slate-600';
  return <span className={`inline-flex items-center justify-center w-8 h-8 rounded-full text-sm font-bold text-white shrink-0 ${c}`}>{score}</span>;
}

function SkeletonCard() {
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 flex flex-col gap-3">
      <div className="skeleton h-5 w-3/4 rounded" />
      <div className="skeleton h-4 w-1/2 rounded" />
      <div className="skeleton h-4 w-full rounded" />
      <div className="flex gap-2 mt-2">
        <div className="skeleton h-8 w-20 rounded-lg" />
        <div className="skeleton h-8 w-20 rounded-lg" />
        <div className="skeleton h-8 w-24 rounded-lg ml-auto" />
      </div>
    </div>
  );
}

function Toast({ msg, onClose }) {
  useEffect(() => { const t = setTimeout(onClose, 3000); return () => clearTimeout(t); }, [onClose]);
  if (!msg) return null;
  return (
    <div className={`fixed bottom-4 right-4 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-medium ${msg.ok ? 'bg-emerald-600 text-white' : 'bg-red-600 text-white'}`}>
      {msg.text}
    </div>
  );
}

function SectionCard({ title, children }) {
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
      {title && <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide mb-4">{title}</h3>}
      {children}
    </div>
  );
}

function InfoTip({ text }) {
  const [show, setShow] = useState(false);
  return (
    <span className="relative inline-flex items-center ml-1" style={{ verticalAlign: 'middle' }}>
      <button
        onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}
        onFocus={() => setShow(true)} onBlur={() => setShow(false)}
        className="w-4 h-4 rounded-full border border-slate-500 text-slate-500 hover:border-blue-400 hover:text-blue-400 text-xs font-bold leading-none flex items-center justify-center transition-colors focus:outline-none"
        tabIndex={-1} type="button">i</button>
      {show && (
        <span className="absolute z-50 left-6 top-1/2 -translate-y-1/2 w-60 p-2.5 text-xs bg-slate-900 border border-slate-600 rounded-xl text-slate-300 shadow-2xl pointer-events-none whitespace-normal leading-relaxed">
          {text}
        </span>
      )}
    </span>
  );
}

function InputField({ label, value, onChange, type = 'text', placeholder = '' }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-slate-400">{label}</label>
      <input
        type={type}
        value={value || ''}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="bg-slate-900 border border-slate-600 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500 placeholder-slate-600"
      />
    </div>
  );
}

function Toggle({ label, checked, onChange }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-slate-300">{label}</span>
      <button
        onClick={() => onChange(!checked)}
        className={`relative w-11 h-6 rounded-full transition-colors ${checked ? 'bg-blue-600' : 'bg-slate-600'}`}
      >
        <span className={`absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${checked ? 'left-5' : 'left-0.5'}`} />
      </button>
    </div>
  );
}

function TagChipEditor({ label, values = [], onChange }) {
  const [input, setInput] = useState('');
  const addTag = () => {
    const v = input.trim();
    if (v && !values.includes(v)) { onChange([...values, v]); setInput(''); }
  };
  return (
    <div className="flex flex-col gap-2">
      <label className="text-xs text-slate-400">{label}</label>
      <div className="flex flex-wrap gap-1.5 min-h-[2rem] bg-slate-900 border border-slate-600 rounded-lg p-2">
        {values.map(v => (
          <span key={v} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-900/60 text-blue-200 text-xs">
            {v}
            <button onClick={() => onChange(values.filter(x => x !== v))} className="text-blue-300 hover:text-red-400 ml-0.5">×</button>
          </span>
        ))}
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); addTag(); } }}
          placeholder="Add, press Enter"
          className="bg-transparent text-sm text-slate-200 outline-none placeholder-slate-600 min-w-[100px] flex-1"
        />
      </div>
    </div>
  );
}

// ── Nav + Header ──────────────────────────────────────────────────────────

const NAV_TABS = [
  { key: 'apply',      label: 'Ready to Apply' },
  { key: 'jobs',       label: 'Jobs' },
  { key: 'untailored', label: 'Untailored' },
  { key: 'pipeline',   label: 'Pipeline' },
  { key: 'profile',    label: 'Profile' },
  { key: 'config',     label: 'Config' },
];

function Header({ stats, activeTab, setActiveTab, theme, toggleTheme }) {
  return (
    <header className="sticky top-0 z-10 border-b border-slate-800" style={{ backgroundColor: 'var(--ap-bg)' }}>
      <div className="max-w-7xl mx-auto px-4 pt-3 pb-2 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold text-slate-100">ApplyPilot</span>
          <span className="text-slate-500 text-sm">Mission Control</span>
        </div>
        <div className="flex items-center gap-2 ml-auto flex-wrap">
          {[
            { label: 'Ready',      val: stats?.ready_to_apply,    color: 'text-blue-400' },
            { label: 'Untailored', val: stats?.untailored,        color: 'text-amber-400' },
            { label: 'Applied',    val: stats?.applied,           color: 'text-emerald-400' },
            { label: 'Interviews', val: stats?.interviews,        color: 'text-purple-400' },
            { label: 'Offers',     val: stats?.offers,            color: 'text-emerald-300' },
            { label: 'Total CVs',  val: stats?.tailored,          color: 'text-slate-200' },
          ].map(({ label, val, color }) => (
            <div key={label} className="flex flex-col items-center bg-slate-800 rounded-lg px-3 py-1.5 border border-slate-700">
              <span className={`text-lg font-bold leading-tight ${color}`}>{val ?? '—'}</span>
              <span className="text-xs text-slate-500">{label}</span>
            </div>
          ))}
          <button onClick={toggleTheme}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            className="p-2 rounded-lg border border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-500 transition-colors text-base leading-none">
            {theme === 'dark' ? '☀' : '🌙'}
          </button>
        </div>
      </div>
      <div className="max-w-7xl mx-auto px-4 pb-0">
        <div className="flex items-center gap-1">
          {NAV_TABS.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-blue-500 text-blue-400'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              {tab.label}
              {tab.key === 'apply' && stats?.ready_to_apply > 0 && (
                <span className="ml-1.5 px-1.5 py-0.5 text-xs bg-blue-500/20 text-blue-400 rounded-full">{stats.ready_to_apply}</span>
              )}
              {tab.key === 'untailored' && stats?.untailored > 0 && (
                <span className="ml-1.5 px-1.5 py-0.5 text-xs bg-amber-500/20 text-amber-400 rounded-full">{stats.untailored}</span>
              )}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}

// ── Job Detail Modal ──────────────────────────────────────────────────────

function JobDetailModal({ urlEncoded, onClose }) {
  const [job, setJob] = useState(null);
  const [activePane, setActivePane] = useState('resume');
  const [resumeText, setResumeText] = useState('');
  const [saveState, setSaveState] = useState(null); // null | 'saving' | 'saved' | 'error'
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    fetch(`/api/jobs/${urlEncoded}`)
      .then(r => r.json())
      .then(d => {
        setJob(d);
        setResumeText(d.resume_text || '');
      });
  }, [urlEncoded]);

  // Close on Escape
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);

  const saveResume = async () => {
    setSaveState('saving');
    setDirty(false);
    const res = await fetch(`/api/jobs/${urlEncoded}/resume`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: resumeText }),
    });
    setSaveState(res.ok ? 'saved' : 'error');
    setTimeout(() => setSaveState(null), 2500);
  };

  if (!job) return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="text-slate-400 text-sm animate-pulse">Loading…</div>
    </div>
  );

  const jobUrl = job.application_url || job.url;

  return (
    <div className="fixed inset-0 z-50 flex flex-col" style={{ backgroundColor: 'var(--ap-bg)' }} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-slate-700 bg-slate-800 shrink-0">
        <ScoreBadge score={job.fit_score} />
        <div className="flex-1 min-w-0">
          <h2 className="font-semibold text-slate-100 truncate">{job.title}</h2>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-slate-400">
            <span>{job.company || job.site}</span>
            {job.company && job.company !== job.site && <span className="text-slate-600">via {job.site}</span>}
            {job.location && <span>{job.location}</span>}
            {job.salary && <span className="text-emerald-400">{job.salary}</span>}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <a href={jobUrl} target="_blank" rel="noopener noreferrer"
            className="px-3 py-1.5 rounded-lg text-xs border border-slate-600 text-slate-300 hover:bg-slate-700 transition-colors">
            Job ↗
          </a>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-700 transition-colors text-lg leading-none">✕</button>
        </div>
      </div>

      {/* Body — two panels */}
      <div className="flex flex-1 min-h-0 divide-x divide-slate-700">

        {/* Left — job description */}
        <div className="flex-1 min-w-0 overflow-y-auto p-6">
          <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Job Description</h3>
          {job.score_reasoning && (
            <div className="mb-4 p-3 rounded-lg bg-slate-800 border border-slate-700 text-sm text-slate-300 leading-relaxed">
              <span className="text-xs text-slate-500 font-medium block mb-1">Why it scored {job.fit_score}/10</span>
              {job.score_reasoning}
            </div>
          )}
          <pre className="whitespace-pre-wrap text-sm text-slate-400 leading-relaxed font-sans">
            {job.full_description || job.description || 'No description available.'}
          </pre>
        </div>

        {/* Right — resume / cover letter editor */}
        <div className="flex-1 min-w-0 flex flex-col min-h-0">
          {/* Pane tabs */}
          <div className="flex items-center gap-1 px-4 pt-3 pb-0 border-b border-slate-700 shrink-0">
            {[
              { key: 'resume', label: 'Tailored CV' },
              ...(job.cover_letter_text ? [{ key: 'cover', label: 'Cover Letter' }] : []),
            ].map(p => (
              <button key={p.key} onClick={() => setActivePane(p.key)}
                className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
                  activePane === p.key ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-400 hover:text-slate-200'
                }`}>
                {p.label}
              </button>
            ))}
            <div className="flex-1" />
            {activePane === 'resume' && job.tailored_resume_path && (
              <a href={`/api/resume/${urlEncoded}`} target="_blank" rel="noopener noreferrer"
                className="mb-1 px-2.5 py-1 text-xs rounded-lg border border-slate-600 text-slate-400 hover:text-slate-200 hover:border-slate-500 transition-colors">
                {job.has_pdf ? '⬇ PDF' : '⬇ TXT'}
              </a>
            )}
            {activePane === 'cover' && job.cover_letter_path && (
              <a href={`/api/cover-letter/${urlEncoded}`} target="_blank" rel="noopener noreferrer"
                className="mb-1 px-2.5 py-1 text-xs rounded-lg border border-slate-600 text-slate-400 hover:text-slate-200 hover:border-slate-500 transition-colors">
                {job.has_cover_pdf ? '⬇ PDF' : '⬇ TXT'}
              </a>
            )}
          </div>

          {/* Editor / preview */}
          {activePane === 'resume' && (
            <div className="flex flex-col flex-1 min-h-0 p-4 gap-3">
              {!job.tailored_resume_path ? (
                <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">No tailored resume yet</div>
              ) : (
                <>
                  <textarea
                    className="flex-1 min-h-0 w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 text-sm text-slate-200 font-mono leading-relaxed resize-none focus:outline-none focus:border-blue-500"
                    value={resumeText}
                    onChange={e => { setResumeText(e.target.value); setDirty(true); setSaveState(null); }}
                    spellCheck={false}
                  />
                  <div className="flex items-center gap-3 shrink-0">
                    <button onClick={saveResume} disabled={!dirty || saveState === 'saving'}
                      className="px-4 py-1.5 rounded-lg text-sm font-medium bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-40">
                      {saveState === 'saving' ? 'Saving…' : 'Save & Regenerate PDF'}
                    </button>
                    {saveState === 'saved' && <span className="text-xs text-emerald-400">✓ Saved — PDF regenerating</span>}
                    {saveState === 'error'  && <span className="text-xs text-red-400">Save failed</span>}
                    {dirty && !saveState   && <span className="text-xs text-amber-400">Unsaved changes</span>}
                  </div>
                </>
              )}
            </div>
          )}
          {activePane === 'cover' && (
            <div className="flex-1 min-h-0 overflow-y-auto p-4">
              <pre className="whitespace-pre-wrap text-sm text-slate-300 leading-relaxed font-sans">{job.cover_letter_text}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Ready to Apply Tab ────────────────────────────────────────────────────

function ReadyCard({ job, onApplied, onSkip }) {
  const [acting, setActing] = useState(null);
  const [showDetail, setShowDetail] = useState(false);
  const jobUrl = job.application_url || job.url;
  const reasoning = job.score_reasoning || '';
  const short = reasoning.length > 140 ? reasoning.slice(0, 140) + '…' : reasoning;

  return (
    <>
    {showDetail && <JobDetailModal urlEncoded={job.url_encoded} onClose={() => setShowDetail(false)} />}
    <div className="card-enter bg-slate-800 rounded-xl border border-slate-700 hover:border-slate-500 transition-colors p-4 flex flex-col gap-3">
      <div className="flex items-start gap-3">
        <ScoreBadge score={job.fit_score} />
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-slate-100 leading-snug truncate cursor-pointer hover:text-blue-300 transition-colors" title={job.title} onClick={() => setShowDetail(true)}>{job.title}</h3>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1">
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">{job.company || job.site}</span>
            {job.company && job.company !== job.site && <span className="text-xs text-slate-600">via {job.site}</span>}
            {job.location && <span className="text-xs text-slate-400 truncate">{job.location}</span>}
            {job.salary && <span className="text-xs text-emerald-400 font-medium">{job.salary}</span>}
          </div>
        </div>
      </div>
      {reasoning && <div className="text-sm text-slate-400 leading-relaxed">{short}</div>}
      <div className="flex flex-wrap gap-2">
        <a href={`/api/resume/${job.url_encoded}`} target="_blank" rel="noopener noreferrer"
          className="px-3 py-1.5 rounded-lg text-xs font-medium border border-blue-500 text-blue-400 hover:bg-blue-500 hover:text-white transition-colors">
          {job.has_pdf ? '📄 CV (PDF)' : '📝 CV (TXT)'}
        </a>
        {job.cover_letter_path && (
          <a href={`/api/cover-letter/${job.url_encoded}`} target="_blank" rel="noopener noreferrer"
            className="px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-600 text-slate-300 hover:bg-slate-700 transition-colors">
            {job.has_cover_pdf ? '📄 Cover Letter' : '📝 Cover Letter'}
          </a>
        )}
        <a href={jobUrl} target="_blank" rel="noopener noreferrer"
          className="px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white transition-colors">
          Apply ↗
        </a>
      </div>
      <div className="flex items-center gap-2 mt-auto pt-1">
        <button onClick={() => setShowDetail(true)}
          className="px-3 py-1.5 rounded-lg text-xs border border-slate-600 text-slate-400 hover:text-slate-200 hover:border-slate-500 transition-colors">
          Details
        </button>
        <button onClick={async () => { setActing('a'); await fetch(`/api/jobs/${job.url_encoded}/mark-applied`, { method: 'POST' }); setActing(null); onApplied(job); }}
          disabled={!!acting}
          className="flex-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white transition-colors disabled:opacity-50">
          {acting==='a'?'…':'✓ Mark Applied'}
        </button>
        <button onClick={async () => { setActing('s'); await fetch(`/api/jobs/${job.url_encoded}/dismiss`, { method: 'POST' }); setActing(null); onSkip(job); }}
          disabled={!!acting}
          className="px-3 py-1.5 rounded-lg text-xs text-red-400 hover:bg-red-900/40 hover:text-red-300 transition-colors disabled:opacity-50" title="Skip">
          {acting==='s'?'…':'Skip'}
        </button>
      </div>
    </div>
    </>
  );
}

function ReadyToApplyTab({ onStatsUpdate }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState({ offset: 0, limit: 30, total: 0 });

  const fetchJobs = useCallback(async (p) => {
    setLoading(true);
    const params = new URLSearchParams({ status: 'ready', min_score: 1, max_score: 10, offset: p.offset, limit: p.limit });
    const res = await fetch(`/api/jobs?${params}`);
    const data = await res.json();
    setJobs(data.jobs);
    setPage(prev => ({ ...prev, total: data.total }));
    setLoading(false);
  }, []);

  useEffect(() => { fetchJobs(page); }, []);

  return (
    <div className="max-w-7xl mx-auto px-4 py-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-200">Ready to Apply</h2>
        <button onClick={() => fetchJobs(page)} className="px-3 py-1.5 text-xs rounded-lg border border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-500 transition-colors">↻ Refresh</button>
      </div>
      {loading && <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"><SkeletonCard /><SkeletonCard /><SkeletonCard /></div>}
      {!loading && jobs.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-slate-500">
          <div className="text-4xl">📋</div>
          <div className="text-lg font-medium">No jobs ready</div>
          <div className="text-sm">Run Tailor in the Pipeline tab to prepare your CVs</div>
        </div>
      )}
      {!loading && jobs.length > 0 && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {jobs.map(job => (
              <ReadyCard key={job.url} job={job}
                onApplied={(j) => { setJobs(p => p.filter(x => x.url !== j.url)); onStatsUpdate(); }}
                onSkip={(j) => { setJobs(p => p.filter(x => x.url !== j.url)); onStatsUpdate(); }}
              />
            ))}
          </div>
          <div className="flex items-center justify-between mt-8 text-sm text-slate-400">
            <span>Showing {page.total === 0 ? 0 : page.offset + 1}–{Math.min(page.offset + page.limit, page.total)} of {page.total}</span>
            <div className="flex gap-2">
              <button onClick={() => { const np = { ...page, offset: Math.max(0, page.offset - page.limit) }; setPage(np); fetchJobs(np); window.scrollTo({ top: 0, behavior: 'smooth' }); }} disabled={page.offset === 0}
                className="px-4 py-2 rounded-lg border border-slate-700 hover:border-slate-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">← Prev</button>
              <button onClick={() => { const np = { ...page, offset: page.offset + page.limit }; setPage(np); fetchJobs(np); window.scrollTo({ top: 0, behavior: 'smooth' }); }} disabled={page.offset + page.limit >= page.total}
                className="px-4 py-2 rounded-lg border border-slate-700 hover:border-slate-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">Next →</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── Jobs Tab ──────────────────────────────────────────────────────────────

const STATUS_LABELS = { applied: 'Applied', interview: 'Interviewed', offer: 'Offer', rejected: 'Rejected' };
const STATUS_COLORS = { applied: 'text-emerald-400', interview: 'text-purple-400', offer: 'text-emerald-300', rejected: 'text-red-400' };

function JobCard({ job, onMarkApplied, onDismiss, onRestore, onMarkStatus }) {
  const [expanded, setExpanded] = useState(false);
  const [acting, setActing] = useState(null);
  const [localStatus, setLocalStatus] = useState(job.apply_status);
  const [showDetail, setShowDetail] = useState(false);
  const jobUrl = job.application_url || job.url;
  const reasoning = job.score_reasoning || '';
  const short = reasoning.length > 160 ? reasoning.slice(0, 160) + '…' : reasoning;
  const isTracked = ['applied','interview','offer','rejected'].includes(localStatus);

  const doMarkStatus = async (s) => {
    setActing(s);
    await fetch(`/api/jobs/${job.url_encoded}/mark-status`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: s }) });
    setLocalStatus(s);
    setActing(null);
    if (onMarkStatus) onMarkStatus(job, s);
  };

  return (
    <>
    {showDetail && <JobDetailModal urlEncoded={job.url_encoded} onClose={() => setShowDetail(false)} />}
    <div className="card-enter bg-slate-800 rounded-xl border border-slate-700 hover:border-slate-500 transition-colors p-4 flex flex-col gap-3">
      <div className="flex items-start gap-3">
        <ScoreBadge score={job.fit_score} />
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-slate-100 leading-snug truncate cursor-pointer hover:text-blue-300 transition-colors" title={job.title} onClick={() => setShowDetail(true)}>{job.title}</h3>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1">
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">{job.company || job.site}</span>
            {job.company && job.company !== job.site && <span className="text-xs text-slate-600">via {job.site}</span>}
            {job.location && <span className="text-xs text-slate-400 truncate">{job.location}</span>}
            {job.salary && <span className="text-xs text-emerald-400 font-medium">{job.salary}</span>}
          </div>
        </div>
      </div>
      {reasoning && (
        <div className="text-sm text-slate-400 leading-relaxed">
          {expanded ? reasoning : short}
          {reasoning.length > 160 && (
            <button onClick={() => setExpanded(e => !e)} className="ml-1 text-blue-400 hover:text-blue-300 text-xs">
              {expanded ? 'less' : 'more'}
            </button>
          )}
        </div>
      )}
      {isTracked && (
        <div className="flex flex-col gap-1.5">
          <div className={`text-xs font-semibold ${STATUS_COLORS[localStatus] || 'text-slate-400'}`}>
            ● {STATUS_LABELS[localStatus] || localStatus}
            {localStatus === 'applied' && job.applied_at && <span className="text-slate-500 font-normal ml-1">{new Date(job.applied_at).toLocaleDateString()}</span>}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {localStatus !== 'interview' && <button onClick={() => doMarkStatus('interview')} disabled={!!acting} className="px-2 py-1 text-xs rounded-lg border border-purple-700 text-purple-400 hover:bg-purple-900/40 disabled:opacity-50 transition-colors">{acting==='interview'?'…':'Interviewed'}</button>}
            {localStatus !== 'offer'     && <button onClick={() => doMarkStatus('offer')}     disabled={!!acting} className="px-2 py-1 text-xs rounded-lg border border-emerald-700 text-emerald-400 hover:bg-emerald-900/40 disabled:opacity-50 transition-colors">{acting==='offer'?'…':'Got Offer'}</button>}
            {localStatus !== 'rejected'  && <button onClick={() => doMarkStatus('rejected')}  disabled={!!acting} className="px-2 py-1 text-xs rounded-lg border border-red-800 text-red-400 hover:bg-red-900/40 disabled:opacity-50 transition-colors">{acting==='rejected'?'…':'Rejected'}</button>}
          </div>
        </div>
      )}
      {localStatus === 'dismissed' && onRestore && (
        <button onClick={async () => { setActing('r'); await fetch(`/api/jobs/${job.url_encoded}/restore`, { method: 'POST' }); setActing(null); onRestore(job); }}
          disabled={!!acting}
          className="text-xs px-3 py-1.5 rounded-lg border border-slate-600 text-slate-400 hover:text-slate-200 hover:border-slate-400 transition-colors disabled:opacity-50 self-start">
          {acting==='r'?'…':'↩ Restore'}
        </button>
      )}
      <div className="flex flex-wrap items-center gap-2 mt-auto pt-1">
        <a href={`/api/resume/${job.url_encoded}`} target="_blank" rel="noopener noreferrer"
          className="px-3 py-1.5 rounded-lg text-xs font-medium border border-blue-500 text-blue-400 hover:bg-blue-500 hover:text-white transition-colors">
          {job.has_pdf ? '📄 CV' : '📝 CV'}
        </a>
        <a href={jobUrl} target="_blank" rel="noopener noreferrer"
          className="px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-600 text-slate-300 hover:bg-slate-700 transition-colors">
          Job ↗
        </a>
        <div className="flex-1" />
        <button onClick={() => setShowDetail(true)}
          className="px-2 py-1.5 rounded-lg text-xs border border-slate-600 text-slate-400 hover:text-slate-200 hover:border-slate-500 transition-colors">
          ⬡
        </button>
        {!isTracked && localStatus !== 'dismissed' && (
          <button onClick={async () => { setActing('a'); await onMarkApplied(job); setActing(null); }} disabled={!!acting}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white transition-colors disabled:opacity-50">
            {acting === 'a' ? '…' : '✓ Applied'}
          </button>
        )}
        {localStatus !== 'dismissed' && !isTracked && (
          <button onClick={async () => { setActing('d'); await onDismiss(job); setActing(null); }} disabled={!!acting}
            className="px-2 py-1.5 rounded-lg text-xs text-red-400 hover:bg-red-900/40 hover:text-red-300 transition-colors disabled:opacity-50" title="Dismiss">
            {acting === 'd' ? '…' : '✕'}
          </button>
        )}
      </div>
    </div>
    </>
  );
}

function JobsTab({ onStatsUpdate }) {
  const [jobs, setJobs] = useState([]);
  const [filters, setFilters] = useState({ minScore: 7, maxScore: 10, site: '', search: '', status: 'pending' });
  const [page, setPage] = useState({ offset: 0, limit: 50, total: 0 });
  const [loading, setLoading] = useState(false);
  const [sites, setSites] = useState([]);
  const searchTimer = useRef(null);
  const [searchInput, setSearchInput] = useState('');

  const fetchJobs = useCallback(async (f, p) => {
    setLoading(true);
    const params = new URLSearchParams({ min_score: f.minScore, max_score: f.maxScore, status: f.status, offset: p.offset, limit: p.limit });
    if (f.site) params.set('site', f.site);
    if (f.search) params.set('search', f.search);
    const res = await fetch(`/api/jobs?${params}`);
    const data = await res.json();
    setJobs(data.jobs);
    setPage(prev => ({ ...prev, total: data.total }));
    setLoading(false);
  }, []);

  const fetchSites = useCallback(async () => {
    const res = await fetch('/api/stats');
    const data = await res.json();
    setSites(data.sites || []);
  }, []);

  useEffect(() => { fetchJobs(filters, page); fetchSites(); }, []);

  const applyFilters = (nf) => { setFilters(nf); const np = { offset: 0, limit: 50, total: 0 }; setPage(np); fetchJobs(nf, np); };

  const STATUS_TABS = ['pending','applied','dismissed','all'];

  return (
    <div className="max-w-7xl mx-auto px-4 py-4">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3 mb-6 p-3 bg-slate-800/50 rounded-xl border border-slate-700">
        <div className="flex items-center gap-1 bg-slate-800 rounded-lg p-1">
          {STATUS_TABS.map(s => (
            <button key={s} onClick={() => applyFilters({ ...filters, status: s })}
              className={`px-3 py-1 rounded-md text-sm font-medium transition-colors capitalize ${filters.status === s ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}>
              {s}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 bg-slate-800 rounded-lg px-3 py-1.5">
          <span className="text-xs text-slate-400">Score</span>
          <input type="range" min="1" max="10" value={filters.minScore} onChange={e => applyFilters({ ...filters, minScore: Number(e.target.value) })} className="w-14" />
          <span className="text-xs text-slate-300 w-3">{filters.minScore}</span>
          <span className="text-slate-600">–</span>
          <input type="range" min="1" max="10" value={filters.maxScore} onChange={e => applyFilters({ ...filters, maxScore: Number(e.target.value) })} className="w-14" />
          <span className="text-xs text-slate-300 w-3">{filters.maxScore}</span>
        </div>
        <select value={filters.site} onChange={e => applyFilters({ ...filters, site: e.target.value })}
          className="bg-slate-800 border border-slate-700 text-slate-300 text-sm rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-500">
          <option value="">All Sites</option>
          {sites.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <input type="text" placeholder="Search…" value={searchInput}
          onChange={e => { setSearchInput(e.target.value); clearTimeout(searchTimer.current); searchTimer.current = setTimeout(() => applyFilters({ ...filters, search: e.target.value }), 300); }}
          className="flex-1 min-w-[160px] bg-slate-800 border border-slate-700 text-slate-300 text-sm rounded-lg px-3 py-1.5 placeholder-slate-500 focus:outline-none focus:border-blue-500" />
      </div>

      {loading && <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"><SkeletonCard /><SkeletonCard /><SkeletonCard /></div>}
      {!loading && jobs.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-slate-500">
          <div className="text-4xl">🔍</div>
          <div className="text-lg font-medium">No jobs match your filters</div>
        </div>
      )}
      {!loading && jobs.length > 0 && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {jobs.map(job => (
              <JobCard key={job.url} job={job}
                onMarkApplied={async (j) => { await fetch(`/api/jobs/${j.url_encoded}/mark-applied`, { method: 'POST' }); setJobs(p => p.filter(x => x.url !== j.url)); onStatsUpdate(); }}
                onDismiss={async (j) => { await fetch(`/api/jobs/${j.url_encoded}/dismiss`, { method: 'POST' }); setJobs(p => p.filter(x => x.url !== j.url)); onStatsUpdate(); }}
                onRestore={(j) => { setJobs(p => p.filter(x => x.url !== j.url)); onStatsUpdate(); }}
                onMarkStatus={(_j, _s) => { onStatsUpdate(); }}
              />
            ))}
          </div>
          <div className="flex items-center justify-between mt-8 text-sm text-slate-400">
            <span>Showing {page.total === 0 ? 0 : page.offset + 1}–{Math.min(page.offset + page.limit, page.total)} of {page.total}</span>
            <div className="flex gap-2">
              <button onClick={() => { const np = { ...page, offset: Math.max(0, page.offset - page.limit) }; setPage(np); fetchJobs(filters, np); window.scrollTo({ top: 0, behavior: 'smooth' }); }} disabled={page.offset === 0}
                className="px-4 py-2 rounded-lg border border-slate-700 hover:border-slate-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">← Prev</button>
              <button onClick={() => { const np = { ...page, offset: page.offset + page.limit }; setPage(np); fetchJobs(filters, np); window.scrollTo({ top: 0, behavior: 'smooth' }); }} disabled={page.offset + page.limit >= page.total}
                className="px-4 py-2 rounded-lg border border-slate-700 hover:border-slate-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">Next →</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── Untailored Tab ────────────────────────────────────────────────────────

function UntailoredCard({ job, onTailored, onDismiss }) {
  const [state, setState] = useState(null); // null | 'running' | 'done' | 'error' | 'dismissing'
  const [errMsg, setErrMsg] = useState('');
  const reasoning = job.score_reasoning || '';
  const short = reasoning.length > 120 ? reasoning.slice(0, 120) + '…' : reasoning;

  const handleTailor = async () => {
    setState('running');
    const res = await fetch(`/api/jobs/${job.url_encoded}/tailor`, { method: 'POST' });
    const { task_id } = await res.json();
    const poll = setInterval(async () => {
      const tr = await fetch(`/api/tasks/${task_id}`);
      const task = await tr.json();
      if (task.status === 'done') {
        clearInterval(poll);
        if (task.result?.status === 'error') {
          setState('error'); setErrMsg(task.result.error || 'Unknown error');
        } else {
          setState('done');
          onTailored(job.url);
        }
      } else if (task.status === 'error') {
        clearInterval(poll); setState('error'); setErrMsg(task.error || 'Task failed');
      }
    }, 2000);
  };

  const handleDismiss = async () => {
    setState('dismissing');
    await fetch(`/api/jobs/${job.url_encoded}/dismiss`, { method: 'POST' });
    onDismiss(job.url);
  };

  return (
    <div className="card-enter bg-slate-800 rounded-xl border border-slate-700 hover:border-slate-500 transition-colors p-4 flex flex-col gap-3">
      <div className="flex items-start gap-3">
        <ScoreBadge score={job.fit_score} />
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-slate-100 leading-snug truncate" title={job.title}>{job.title}</h3>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1">
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">{job.site}</span>
            {job.location && <span className="text-xs text-slate-400 truncate">{job.location}</span>}
          </div>
        </div>
      </div>
      {reasoning && <div className="text-sm text-slate-400 leading-relaxed">{short}</div>}
      <div className="flex items-center gap-2 mt-auto pt-1">
        <a href={job.application_url || job.url} target="_blank" rel="noopener noreferrer"
          className="px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-600 text-slate-300 hover:bg-slate-700 transition-colors"
          onClick={e => { if (!job.application_url && !job.url) e.preventDefault(); }}>
          Job ↗
        </a>
        <button onClick={handleDismiss} disabled={state === 'dismissing' || state === 'running'}
          className="px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-600 text-slate-400 hover:border-red-500 hover:text-red-400 transition-colors disabled:opacity-40">
          ✕
        </button>
        <div className="flex-1" />
        {state === 'done' && <span className="text-xs text-emerald-400 font-medium">✓ Tailored</span>}
        {state === 'error' && <span className="text-xs text-red-400 font-medium" title={errMsg}>✗ Failed</span>}
        {state !== 'done' && (
          <button onClick={handleTailor} disabled={state === 'running' || state === 'dismissing'}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors disabled:opacity-60 ${state === 'running' ? 'bg-blue-700 text-white' : 'bg-blue-600 hover:bg-blue-500 text-white'}`}>
            {state === 'running' ? <><span className="spin">⟳</span> Tailoring…</> : '✦ Tailor'}
          </button>
        )}
      </div>
    </div>
  );
}

function UntailoredTab({ onStatsUpdate }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState({ offset: 0, limit: 50, total: 0 });
  const [minScore, setMinScore] = useState(7);
  const [tailorAllTask, setTailorAllTask] = useState(null); // null | {task_id, status}
  const tailorPollRef = useRef(null);

  const fetchJobs = useCallback(async (score, p) => {
    setLoading(true);
    const res = await fetch(`/api/jobs?status=untailored&min_score=${score}&offset=${p.offset}&limit=${p.limit}`);
    const data = await res.json();
    setJobs(data.jobs);
    setPage(prev => ({ ...prev, total: data.total }));
    setLoading(false);
  }, []);

  const handleTailorAll = async () => {
    const res = await fetch('/api/pipeline/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stages: ['tailor'], min_score: minScore, workers: 1, validation: 'normal', stream: false }),
    });
    const { task_id } = await res.json();
    setTailorAllTask({ task_id, status: 'running' });
    tailorPollRef.current = setInterval(async () => {
      const tr = await fetch(`/api/tasks/${task_id}`);
      const t = await tr.json();
      setTailorAllTask({ task_id, status: t.status });
      if (t.status === 'done' || t.status === 'error') {
        clearInterval(tailorPollRef.current);
        if (t.status === 'done') { fetchJobs(minScore, { offset: 0, limit: 50, total: 0 }); onStatsUpdate(); }
      }
    }, 3000);
  };

  useEffect(() => { fetchJobs(minScore, page); return () => clearInterval(tailorPollRef.current); }, []);

  const tailoring = tailorAllTask?.status === 'running';

  return (
    <div className="max-w-7xl mx-auto px-4 py-4">
      <div className="flex items-center gap-4 mb-6 p-3 bg-slate-800/50 rounded-xl border border-slate-700">
        <div className="flex items-center gap-2 bg-slate-800 rounded-lg px-3 py-1.5">
          <span className="text-xs text-slate-400">Min Score</span>
          <input type="range" min="1" max="10" value={minScore}
            onChange={e => { setMinScore(Number(e.target.value)); const np = { offset:0,limit:50,total:0 }; setPage(np); fetchJobs(Number(e.target.value), np); }} className="w-20" />
          <span className="text-xs text-slate-300 w-3">{minScore}</span>
        </div>
        <span className="text-sm text-slate-400">{page.total} jobs need tailoring</span>
        <div className="ml-auto flex items-center gap-2">
          {tailorAllTask && (
            <span className={`text-xs font-medium ${tailoring ? 'text-blue-400' : tailorAllTask.status === 'done' ? 'text-emerald-400' : 'text-red-400'}`}>
              {tailoring ? <><span className="spin inline-block">⟳</span> Tailoring all…</> : tailorAllTask.status === 'done' ? '✓ Done' : '✗ Error'}
            </span>
          )}
          <button onClick={handleTailorAll} disabled={tailoring || page.total === 0}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
            ✦ Tailor All
          </button>
          <button onClick={() => fetchJobs(minScore, page)} className="px-3 py-1.5 rounded-lg text-xs border border-slate-600 text-slate-300 hover:bg-slate-700 transition-colors">↻ Refresh</button>
        </div>
      </div>
      {loading && <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"><SkeletonCard /><SkeletonCard /><SkeletonCard /></div>}
      {!loading && jobs.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-slate-500">
          <div className="text-4xl">✅</div>
          <div className="text-lg font-medium">All jobs are tailored!</div>
        </div>
      )}
      {!loading && jobs.length > 0 && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {jobs.map(job => (
              <UntailoredCard key={job.url} job={job}
                onTailored={(url) => { setJobs(p => p.filter(x => x.url !== url)); setPage(p => ({ ...p, total: Math.max(0, p.total - 1) })); onStatsUpdate(); }}
                onDismiss={(url) => { setJobs(p => p.filter(x => x.url !== url)); setPage(p => ({ ...p, total: Math.max(0, p.total - 1) })); onStatsUpdate(); }} />
            ))}
          </div>
          <div className="flex items-center justify-between mt-8 text-sm text-slate-400">
            <span>Showing {page.total === 0 ? 0 : page.offset+1}–{Math.min(page.offset+page.limit,page.total)} of {page.total}</span>
            <div className="flex gap-2">
              <button onClick={() => { const np = {...page,offset:Math.max(0,page.offset-page.limit)}; setPage(np); fetchJobs(minScore,np); }} disabled={page.offset===0}
                className="px-4 py-2 rounded-lg border border-slate-700 hover:border-slate-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">← Prev</button>
              <button onClick={() => { const np = {...page,offset:page.offset+page.limit}; setPage(np); fetchJobs(minScore,np); }} disabled={page.offset+page.limit>=page.total}
                className="px-4 py-2 rounded-lg border border-slate-700 hover:border-slate-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors">Next →</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── Pipeline Funnel ────────────────────────────────────────────────────────

function PipelineFunnel({ funnel, onRefresh }) {
  if (!funnel) return (
    <div className="flex items-center gap-2 text-xs text-slate-500 px-1">
      <span className="spin inline-block">⟳</span> Loading funnel…
    </div>
  );

  const rows = [
    {
      stage: '1. Discover',
      done: funnel.discovered,
      doneColor: 'text-slate-200',
      pending: funnel.pending_enrich,
      pendingLabel: 'not yet enriched',
      pendingColor: funnel.pending_enrich > 0 ? 'text-amber-400' : 'text-emerald-400',
      cmd: 'enrich',
    },
    {
      stage: '2. Enrich',
      done: funnel.enriched,
      doneColor: 'text-slate-200',
      pending: funnel.pending_filter,
      pendingLabel: 'not yet filtered',
      pendingColor: funnel.pending_filter > 0 ? 'text-amber-400' : 'text-emerald-400',
      cmd: 'filter',
      extra: funnel.location_filtered > 0 ? `${funnel.location_filtered} rejected` : null,
      extraColor: 'text-slate-500',
    },
    {
      stage: '3. Filter',
      done: funnel.enriched - funnel.pending_filter - funnel.location_filtered,
      doneColor: 'text-slate-200',
      pending: funnel.pending_score,
      pendingLabel: 'not yet scored',
      pendingColor: funnel.pending_score > 0 ? 'text-amber-400' : 'text-emerald-400',
      cmd: 'score',
    },
    {
      stage: '4. Score',
      done: funnel.scored,
      doneColor: 'text-slate-200',
      pending: funnel.pending_tailor,
      pendingLabel: 'good fit (7+), not tailored',
      pendingColor: funnel.pending_tailor > 0 ? 'text-amber-400' : 'text-emerald-400',
      cmd: 'tailor',
    },
    {
      stage: '5. Tailor',
      done: funnel.tailored,
      doneColor: 'text-slate-200',
      pending: funnel.pending_cover,
      pendingLabel: 'missing cover letter',
      pendingColor: funnel.pending_cover > 0 ? 'text-amber-400' : 'text-emerald-400',
      cmd: 'cover',
    },
    {
      stage: '6. Cover',
      done: funnel.cover,
      doneColor: 'text-slate-200',
      pending: funnel.ready_to_apply,
      pendingLabel: 'ready to submit',
      pendingColor: funnel.ready_to_apply > 0 ? 'text-blue-400' : 'text-emerald-400',
      cmd: null,
    },
    {
      stage: '7. Apply',
      done: funnel.applied,
      doneColor: 'text-emerald-400',
      pending: funnel.apply_errors,
      pendingLabel: 'errors',
      pendingColor: funnel.apply_errors > 0 ? 'text-red-400' : null,
      cmd: null,
    },
  ];

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
        <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">Pipeline Status</h3>
        <button onClick={onRefresh} className="text-xs text-slate-500 hover:text-slate-300 transition-colors">↻ Refresh</button>
      </div>
      <div className="divide-y divide-slate-700/50">
        {rows.map(row => (
          <div key={row.stage} className="flex items-center gap-4 px-4 py-2.5 text-sm">
            <span className="text-slate-500 w-24 shrink-0">{row.stage}</span>
            <span className={`font-semibold w-10 text-right shrink-0 ${row.doneColor}`}>{row.done}</span>
            <span className="text-slate-700 shrink-0">→</span>
            {row.pending > 0 ? (
              <span className={`${row.pendingColor}`}>
                <span className="font-medium">{row.pending}</span>
                <span className="text-xs text-slate-500 ml-1">{row.pendingLabel}</span>
              </span>
            ) : (
              <span className="text-xs text-emerald-500">all done</span>
            )}
            {row.extra && (
              <span className={`text-xs ml-auto shrink-0 ${row.extraColor}`}>{row.extra}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Pipeline Tab ──────────────────────────────────────────────────────────

const ALL_STAGES = ['discover','enrich','filter','score','tailor','cover','pdf'];

// Module-level cache — survives tab switches
const _pc = { task: null, logLines: [], since: 0, pollId: null };

// Noise errors we suppress — expected failures that don't affect the run
const _SUPPRESS_ERRORS = [
  'Invalid country string',
  'all sites failed',
  'Smart extract failed: Timeout',
  'Smart extract error: Timeout',
  'Timeout 30000ms exceeded',
];

function parseProgress(lines) {
  // Extract structured events from log lines
  const events = [];
  for (const line of lines) {
    let m;
    m = line.match(/=== Stage: (\w+) ===/);
    if (m) { events.push({ type: 'stage', name: m[1] }); continue; }

    m = line.match(/Sites: ([^|]+)\|/);
    if (m) { events.push({ type: 'sites', sites: m[1].trim() }); continue; }

    m = line.match(/Full crawl: (\d+) search combinations/);
    if (m) { events.push({ type: 'info', text: `${m[1]} search combinations` }); continue; }

    m = line.match(/"([^"]+)" in [^\]]+\]\] (\d+) results -> (\d+) new, (\d+) dupes, (\d+) filtered/);
    if (m) { events.push({ type: 'query', query: m[1], total: +m[2], new: +m[3], dupes: +m[4], filtered: +m[5] }); continue; }

    m = line.match(/Progress: (\d+)\/(\d+) queries done \((\d+) new/);
    if (m) { events.push({ type: 'progress', done: +m[1], total: +m[2], new: +m[3] }); continue; }

    m = line.match(/Location filter complete: checked (\d+) jobs, filtered (\d+) out/);
    if (m) { events.push({ type: 'filter_done', checked: +m[1], filtered: +m[2] }); continue; }

    m = line.match(/Scored (\d+) jobs? for/);
    if (m) { events.push({ type: 'scored', count: +m[1] }); continue; }

    m = line.match(/Tailoring job: (.+?) \(/);
    if (m) { events.push({ type: 'tailoring', title: m[1] }); continue; }

    if (line.includes(' ERROR ') && !line.includes('Glassdoor')) {
      // Skip known noise errors
      if (_SUPPRESS_ERRORS.some(pat => line.includes(pat))) continue;
      const msg = (line.split(' ERROR ')[1] || '').slice(0, 120);
      events.push({ type: 'error', msg });
    }
  }
  return events;
}

function PipelineProgress({ events, isRunning, task }) {
  if (events.length === 0 && !isRunning) return null;

  // Group query events under their stage
  const sections = [];
  let current = null;
  let queryBuffer = [];
  let latestProgress = null;

  const flush = () => {
    if (current) { sections.push({ ...current, queries: queryBuffer, progress: latestProgress }); }
    queryBuffer = []; latestProgress = null;
  };

  for (const ev of events) {
    if (ev.type === 'stage') { flush(); current = ev; }
    else if (ev.type === 'query') queryBuffer.push(ev);
    else if (ev.type === 'progress') latestProgress = ev;
    else if (ev.type === 'sites') { if (current) current.sites = ev.sites; }
    else if (ev.type === 'filter_done') {
      flush();
      const existing = sections.find(s => s.type === 'stage' && s.name === 'filter');
      if (existing) { existing.filterDone = ev; } else { sections.push({ type: 'stage', name: 'filter', filterDone: ev }); }
      current = null;
    }
    else if (ev.type === 'info') { if (current) current.info = ev.text; }
    else if (ev.type === 'scored') { flush(); sections.push({ type: 'stage', name: 'score', scored: ev.count }); current = null; }
    else if (ev.type === 'tailoring') { if (current?.name === 'tailor') current.tailoredCount = (current.tailoredCount || 0) + 1; }
    else if (ev.type === 'error') { sections.push({ type: 'error', msg: ev.msg }); }
  }
  flush();

  const stageIcons = { discover: '🔍', enrich: '🔗', filter: '🧹', score: '📊', tailor: '✍️', cover: '📝', pdf: '📄' };

  return (
    <div className="flex flex-col gap-3">
      {sections.map((s, i) => (
        <div key={i}>
          {s.type === 'error' && (
            <div className="text-xs text-red-400 bg-red-900/20 rounded-lg px-3 py-2">{s.msg}</div>
          )}
          {s.type === 'stage' && (
            <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
              <div className="flex items-center gap-2 px-4 py-2.5 border-b border-slate-700 bg-slate-800/80">
                <span className="text-base">{stageIcons[s.name] || '⚙️'}</span>
                <span className="font-semibold text-slate-200 capitalize">{s.name}</span>
                {s.sites && <span className="text-xs text-slate-500 ml-2">{s.sites}</span>}
                {s.info && <span className="text-xs text-slate-500 ml-auto">{s.info}</span>}
                {s.filterDone && <span className="text-xs text-slate-400 ml-auto">{s.filterDone.checked} checked · <span className="text-amber-400">{s.filterDone.filtered} filtered out</span></span>}
                {s.scored !== undefined && <span className="text-xs text-slate-400 ml-auto">{s.scored} jobs scored</span>}
                {s.tailoredCount !== undefined && <span className="text-xs text-slate-400 ml-auto">{s.tailoredCount} tailored</span>}
              </div>
              {s.queries && s.queries.length > 0 && (() => {
                // Group queries by name and aggregate totals
                const grouped = {};
                for (const q of s.queries) {
                  if (!grouped[q.query]) grouped[q.query] = { query: q.query, total: 0, new: 0, dupes: 0, filtered: 0 };
                  grouped[q.query].total += q.total;
                  grouped[q.query].new += q.new;
                  grouped[q.query].dupes += q.dupes;
                  grouped[q.query].filtered += q.filtered;
                }
                const rows = Object.values(grouped);
                return (
                  <div>
                    <div className="divide-y divide-slate-700/50 max-h-56 overflow-y-auto">
                      {rows.map((q, qi) => (
                        <div key={qi} className="flex items-center gap-3 px-4 py-1.5 text-xs">
                          <span className="text-slate-300 flex-1 truncate" title={q.query}>{q.query}</span>
                          <span className="text-slate-500 w-16 text-right">{q.total} found</span>
                          <span className={`w-14 text-right font-medium ${q.new > 0 ? 'text-emerald-400' : 'text-slate-600'}`}>+{q.new}</span>
                          <span className="text-slate-600 w-14 text-right">{q.dupes} dupes</span>
                          <span className={`w-18 text-right ${q.filtered > 0 ? 'text-amber-600' : 'text-slate-600'}`}>{q.filtered} skip</span>
                        </div>
                      ))}
                    </div>
                    {s.progress && (
                      <div className="px-4 py-2 flex items-center gap-3 text-xs bg-slate-900/40 border-t border-slate-700/50">
                        <span className="text-slate-500">{s.progress.done}/{s.progress.total} queries</span>
                        <span className="text-emerald-400 font-medium">{s.progress.new} new jobs so far</span>
                        <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                          <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${Math.round(s.progress.done/s.progress.total*100)}%` }} />
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}
            </div>
          )}
        </div>
      ))}
      {isRunning && events.length === 0 && (
        <div className="text-xs text-slate-500 flex items-center gap-2 px-1">
          <span className="spin inline-block">⟳</span> Starting pipeline…
        </div>
      )}
    </div>
  );
}

function PipelineTab({ onStatsUpdate }) {
  const [stages, setStages] = useState(['discover','enrich','filter','score']);
  const [opts, setOpts] = useState({ min_score: 7, workers: 1, validation: 'normal', stream: false });
  const [task, setTask] = useState(_pc.task);
  const [logLines, setLogLines] = useState(_pc.logLines);
  const [funnel, setFunnel] = useState(null);
  const pollRef = useRef(_pc.pollId);

  const fetchFunnel = useCallback(async () => {
    const res = await fetch('/api/stats');
    const data = await res.json();
    setFunnel(data.funnel || null);
  }, []);

  const handleToggleStage = (s) => setStages(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]);

  // Resume polling if a task was running when we left the tab
  useEffect(() => {
    fetchFunnel();
    if (_pc.task?.status === 'running' && !pollRef.current) {
      startPolling(_pc.task.task_id);
    }
    return () => {}; // don't stop polling on unmount — it lives in _pc
  }, []);

  const startPolling = (task_id) => {
    if (pollRef.current) clearInterval(pollRef.current);
    const id = setInterval(async () => {
      const tr = await fetch(`/api/tasks/${task_id}?since=${_pc.since}`);
      const t = await tr.json();
      if (t.log_lines?.length > 0) {
        _pc.logLines = [..._pc.logLines, ...t.log_lines];
        _pc.since = t.log_total;
        setLogLines([..._pc.logLines]);
      }
      const newTask = { task_id, status: t.status, result: t.result, error: t.error };
      _pc.task = newTask;
      setTask({ ...newTask });
      if (t.status === 'done' || t.status === 'error') {
        clearInterval(id); _pc.pollId = null; pollRef.current = null;
        if (t.status === 'done') { onStatsUpdate(); fetchFunnel(); }
      }
    }, 2000);
    pollRef.current = id; _pc.pollId = id;
  };

  const handleRun = async () => {
    if (stages.length === 0) return;
    _pc.logLines = []; _pc.since = 0;
    setLogLines([]);
    const res = await fetch('/api/pipeline/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stages, ...opts }),
    });
    const { task_id } = await res.json();
    const newTask = { task_id, status: 'running', result: null, error: null };
    _pc.task = newTask; setTask({ ...newTask });
    startPolling(task_id);
  };

  const isRunning = task?.status === 'running';
  const statusColor = !task ? '' : isRunning ? 'text-blue-400' : task.status === 'done' ? 'text-emerald-400' : 'text-red-400';
  const events = parseProgress(logLines);

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 flex flex-col gap-5">
      <PipelineFunnel funnel={funnel} onRefresh={fetchFunnel} />
      <SectionCard title="Stages">
        <p className="text-xs text-slate-500 mb-3">Select which pipeline stages to run. Stages execute in order: discover → enrich → filter → score → tailor → cover → pdf.</p>
        <div className="flex flex-wrap gap-2">
          {ALL_STAGES.map(s => (
            <button key={s} onClick={() => handleToggleStage(s)}
              className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors capitalize ${stages.includes(s) ? 'bg-blue-600 border-blue-500 text-white' : 'border-slate-600 text-slate-400 hover:border-slate-400 hover:text-slate-200'}`}>
              {stages.includes(s) ? '✓ ' : ''}{s}
            </button>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Options">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400 flex items-center">
              Min Score: {opts.min_score}
              <InfoTip text="Only jobs with a fit score ≥ this threshold will be tailored and have cover letters generated. Score 7+ is recommended for quality applications." />
            </label>
            <input type="range" min="1" max="10" value={opts.min_score} onChange={e => setOpts(o => ({...o, min_score: Number(e.target.value)}))} />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400 flex items-center">
              Workers: {opts.workers}
              <InfoTip text="Number of parallel threads for the discover and enrich stages. Higher values speed up scraping but may trigger rate limits. Start with 1–2." />
            </label>
            <input type="range" min="1" max="8" value={opts.workers} onChange={e => setOpts(o => ({...o, workers: Number(e.target.value)}))} />
          </div>
          <div className="flex flex-col gap-2">
            <label className="text-xs text-slate-400 flex items-center">
              Validation Mode
              <InfoTip text="Controls how strictly the LLM output is checked. Normal: balanced checks. Strict: rejects resumes with any formatting issues. Lenient: accepts output even with minor problems — useful if you keep hitting validation failures." />
            </label>
            <div className="flex gap-3">
              {['normal','strict','lenient'].map(v => (
                <label key={v} className="flex items-center gap-1.5 cursor-pointer text-sm text-slate-300">
                  <input type="radio" name="validation" value={v} checked={opts.validation === v} onChange={() => setOpts(o => ({...o, validation: v}))} className="accent-blue-500" />
                  {v.charAt(0).toUpperCase() + v.slice(1)}
                </label>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-2 pt-4">
            <Toggle label="Stream mode" checked={opts.stream} onChange={v => setOpts(o => ({...o, stream: v}))} />
            <InfoTip text="Runs stages concurrently — enrich starts immediately as discover produces results. Faster overall but uses more resources. Best for full pipeline runs." />
          </div>
        </div>
      </SectionCard>

      <button onClick={handleRun} disabled={stages.length === 0 || isRunning}
        className="w-full py-3 rounded-xl font-semibold text-sm bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
        {isRunning ? <><span className="spin inline-block mr-2">⟳</span>Running pipeline…</> : `Run: ${stages.join(' → ')}`}
      </button>

      {task && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3 px-1">
            <span className={`text-sm font-medium ${statusColor}`}>
              {isRunning ? <><span className="spin inline-block mr-1">⟳</span>Running</> : task.status === 'done' ? '✓ Done' : '✗ Error'}
            </span>
            {logLines.length > 0 && (
              <button onClick={() => { _pc.logLines = []; _pc.since = 0; setLogLines([]); }}
                className="ml-auto text-xs text-slate-600 hover:text-slate-400 transition-colors">Clear</button>
            )}
          </div>

          <PipelineProgress events={events} isRunning={isRunning} task={task} />

          {task.status === 'done' && task.result?.stages && (
            <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Run Summary</div>
              <div className="flex flex-col gap-1.5">
                {task.result.stages.map(s => (
                  <div key={s.stage} className="flex items-center gap-2 text-sm">
                    <span className="text-slate-500 w-4">{(['discover','enrich','filter','score','tailor','cover','pdf'].indexOf(s.stage) >= 0 ? ['🔍','🔗','🧹','📊','✍️','📝','📄'][['discover','enrich','filter','score','tailor','cover','pdf'].indexOf(s.stage)] : '⚙️')}</span>
                    <span className={`font-medium w-16 capitalize ${s.status === 'ok' ? 'text-emerald-400' : s.status === 'skipped' ? 'text-slate-500' : 'text-red-400'}`}>{s.stage}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${s.status === 'ok' ? 'bg-emerald-900/40 text-emerald-400' : s.status === 'skipped' ? 'bg-slate-700 text-slate-500' : 'bg-red-900/40 text-red-400'}`}>{s.status}</span>
                    <span className="text-slate-500 text-xs ml-auto">{s.elapsed?.toFixed(1)}s</span>
                  </div>
                ))}
                <div className="border-t border-slate-700 mt-2 pt-2 text-xs text-slate-400 flex justify-between">
                  <span>Total time</span><span>{task.result.elapsed?.toFixed(1)}s</span>
                </div>
              </div>
            </div>
          )}

          {task.status === 'error' && (
            <div className="text-sm text-red-400 bg-red-900/20 rounded-xl p-4">{task.error}</div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Profile Tab ───────────────────────────────────────────────────────────

function ProfileTab() {
  const [profile, setProfile] = useState(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    fetch('/api/profile').then(r => r.json()).then(setProfile).catch(() => setToast({ ok: false, text: 'Failed to load profile' }));
  }, []);

  const set = (path, val) => {
    const keys = path.split('.');
    setProfile(p => {
      const n = JSON.parse(JSON.stringify(p));
      let obj = n;
      for (let i = 0; i < keys.length - 1; i++) obj = obj[keys[i]];
      obj[keys[keys.length - 1]] = val;
      return n;
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      await fetch('/api/profile', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(profile) });
      setToast({ ok: true, text: 'Profile saved!' });
    } catch { setToast({ ok: false, text: 'Failed to save profile' }); }
    setSaving(false);
  };

  if (!profile) return <div className="flex justify-center py-20 text-slate-500">Loading profile…</div>;

  const p = profile.personal || {};
  const wa = profile.work_authorization || {};
  const comp = profile.compensation || {};
  const exp = profile.experience || {};
  const sb = profile.skills_boundary || {};
  const rf = profile.resume_facts || {};
  const eeo = profile.eeo_voluntary || {};
  const avail = profile.availability || {};

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 flex flex-col gap-5">
      <Toast msg={toast} onClose={() => setToast(null)} />

      <SectionCard title="Personal Info">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <InputField label="Full Name" value={p.full_name} onChange={v => set('personal.full_name', v)} />
          <InputField label="Email" value={p.email} onChange={v => set('personal.email', v)} type="email" />
          <InputField label="Phone" value={p.phone} onChange={v => set('personal.phone', v)} placeholder="+1..." />
          <InputField label="City" value={p.city} onChange={v => set('personal.city', v)} />
          <InputField label="Country" value={p.country} onChange={v => set('personal.country', v)} />
          <InputField label="LinkedIn URL" value={p.linkedin_url} onChange={v => set('personal.linkedin_url', v)} />
          <InputField label="GitHub URL" value={p.github_url} onChange={v => set('personal.github_url', v)} />
          <InputField label="Portfolio URL" value={p.portfolio_url} onChange={v => set('personal.portfolio_url', v)} />
        </div>
      </SectionCard>

      <SectionCard title="Work Authorization">
        <p className="text-xs text-slate-500 mb-3">Used by the LLM to filter out jobs that require local work authorization or have no visa sponsorship.
          <InfoTip text="These flags are read during scoring. If 'Requires visa sponsorship' is on and a job explicitly says no sponsorship, it will score lower or be filtered out by the description filter stage." />
        </p>
        <div className="flex flex-col gap-4">
          <div className="flex items-center gap-2">
            <Toggle label="Legally authorized to work" checked={!!wa.legally_authorized_to_work} onChange={v => set('work_authorization.legally_authorized_to_work', v)} />
            <InfoTip text="Set to true if you already have the right to work in the target country without sponsorship (e.g. citizen, permanent resident). False means you need sponsorship." />
          </div>
          <div className="flex items-center gap-2">
            <Toggle label="Requires visa sponsorship" checked={!!wa.require_sponsorship} onChange={v => set('work_authorization.require_sponsorship', v)} />
            <InfoTip text="Set to true if you need the employer to sponsor your work visa. Jobs that explicitly state 'no sponsorship' will be filtered out by the description filter stage." />
          </div>
          <InputField label="Work Permit Type (e.g. H-1B, TN)" value={wa.work_permit_type} onChange={v => set('work_authorization.work_permit_type', v)} />
        </div>
      </SectionCard>

      <SectionCard title="Compensation">
        <p className="text-xs text-slate-500 mb-3">Used by the LLM when scoring fit — jobs with listed salaries far below your expectation will score lower.
          <InfoTip text="Salary data is only sometimes available on job listings. When present, the scorer will factor in whether the range overlaps with your expectation." />
        </p>
        <div className="grid grid-cols-2 gap-4">
          <InputField label="Salary Expectation" value={comp.salary_expectation} onChange={v => set('compensation.salary_expectation', v)} />
          <InputField label="Currency" value={comp.salary_currency} onChange={v => set('compensation.salary_currency', v)} placeholder="USD" />
          <InputField label="Min Range" value={comp.salary_range_min} onChange={v => set('compensation.salary_range_min', v)} />
          <InputField label="Max Range" value={comp.salary_range_max} onChange={v => set('compensation.salary_range_max', v)} />
        </div>
      </SectionCard>

      <SectionCard title="Experience">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <InputField label="Years of Experience" value={exp.years_of_experience_total} onChange={v => set('experience.years_of_experience_total', v)} />
          <InputField label="Education Level" value={exp.education_level} onChange={v => set('experience.education_level', v)} placeholder="Master's" />
          <InputField label="Current Title" value={exp.current_title} onChange={v => set('experience.current_title', v)} />
          <div>
            <label className="text-xs text-slate-400 flex items-center mb-1">
              Target Role(s)
              <InfoTip text="The role(s) you're targeting. Used by the LLM when scoring to assess how well a job aligns with your career direction. Can be a comma-separated list (e.g. 'Cloud Engineer, DevOps Engineer')." />
            </label>
            <input value={exp.target_role || ''} onChange={e => set('experience.target_role', e.target.value)}
              className="w-full bg-slate-900 border border-slate-600 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500" />
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Skills Boundary">
        <p className="text-xs text-slate-500 mb-3">Skills the LLM is allowed to highlight in your tailored resume. It will NOT invent skills outside these lists.
          <InfoTip text="This acts as a guardrail — the AI can only emphasize skills from these lists when tailoring. Add anything you're genuinely proficient in. Removing a skill means it won't be featured even if the job requires it." />
        </p>
        <div className="flex flex-col gap-4">
          <TagChipEditor label="Programming Languages" values={sb.programming_languages || []} onChange={v => set('skills_boundary.programming_languages', v)} />
          <TagChipEditor label="Frameworks" values={sb.frameworks || []} onChange={v => set('skills_boundary.frameworks', v)} />
          <TagChipEditor label="Tools & Platforms" values={sb.tools || []} onChange={v => set('skills_boundary.tools', v)} />
        </div>
      </SectionCard>

      <SectionCard title="Resume Facts">
        <p className="text-xs text-slate-500 mb-3">Verified facts the LLM must preserve exactly as-is when tailoring. These are never reworded or removed.
          <InfoTip text="Preserved companies, projects, and school names will always appear in the tailored resume exactly as written here. Real metrics (e.g. 'reduced latency by 40%') are kept verbatim to prevent hallucination." />
        </p>
        <div className="flex flex-col gap-4">
          <TagChipEditor label="Preserved Companies" values={rf.preserved_companies || []} onChange={v => set('resume_facts.preserved_companies', v)} />
          <TagChipEditor label="Preserved Projects" values={rf.preserved_projects || []} onChange={v => set('resume_facts.preserved_projects', v)} />
          <InputField label="Preserved School" value={rf.preserved_school} onChange={v => set('resume_facts.preserved_school', v)} />
          <TagChipEditor label="Real Metrics (verifiable facts)" values={rf.real_metrics || []} onChange={v => set('resume_facts.real_metrics', v)} />
        </div>
      </SectionCard>

      <SectionCard title="EEO (Voluntary)">
        <p className="text-xs text-slate-500 mb-3">Optional demographic info pre-filled on job application forms. Selecting "Decline to self-identify" is always valid.
          <InfoTip text="These values are used only when the auto-apply agent fills EEO questionnaires on application forms. They are never included in your tailored resume or visible to employers outside official EEO forms." />
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[
            ['Gender', 'eeo_voluntary.gender', ['Decline to self-identify','Male','Female','Non-binary']],
            ['Race / Ethnicity', 'eeo_voluntary.race_ethnicity', ['Decline to self-identify','Asian','Black or African American','Hispanic or Latino','White','Two or more races']],
            ['Veteran Status', 'eeo_voluntary.veteran_status', ['Decline to self-identify','Yes, protected veteran','No']],
            ['Disability Status', 'eeo_voluntary.disability_status', ['Decline to self-identify','Yes','No']],
          ].map(([label, path, options]) => (
            <div key={path} className="flex flex-col gap-1">
              <label className="text-xs text-slate-400">{label}</label>
              <select value={eeo[path.split('.')[1]] || ''} onChange={e => set(path, e.target.value)}
                className="bg-slate-900 border border-slate-600 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500">
                {options.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Availability">
        <InputField label="Earliest Start Date" value={avail.earliest_start_date} onChange={v => set('availability.earliest_start_date', v)} placeholder="immediate / 2 weeks / 1 month" />
        <p className="text-xs text-slate-500 mt-2">Used by the auto-apply agent when asked about availability or notice period on application forms.</p>
      </SectionCard>

      <button onClick={save} disabled={saving}
        className="w-full py-3 rounded-xl font-semibold text-sm bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-50">
        {saving ? 'Saving…' : 'Save Profile'}
      </button>
    </div>
  );
}

// ── Workday Config Section ─────────────────────────────────────────────────

function WorkdayConfig({ toast, setToast }) {
  const [employers, setEmployers] = useState(null);
  const [saving, setSaving] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newEmp, setNewEmp] = useState({ key: '', name: '', tenant: '', site_id: '', base_url: '' });

  useEffect(() => {
    fetch('/api/config/employers').then(r => r.json()).then(setEmployers).catch(() => setToast({ ok: false, text: 'Failed to load employers' }));
  }, []);

  const save = async (updated) => {
    setSaving(true);
    try {
      await fetch('/api/config/employers', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(updated) });
      setToast({ ok: true, text: 'Workday config saved!' });
    } catch { setToast({ ok: false, text: 'Failed to save' }); }
    setSaving(false);
  };

  const toggle = (key) => {
    const updated = { ...employers, [key]: { ...employers[key], enabled: employers[key].enabled === false ? true : false } };
    setEmployers(updated); save(updated);
  };

  const addEmployer = () => {
    if (!newEmp.key || !newEmp.tenant || !newEmp.base_url) return;
    const updated = { ...employers, [newEmp.key]: { name: newEmp.name || newEmp.key, tenant: newEmp.tenant, site_id: newEmp.site_id, base_url: newEmp.base_url, enabled: true } };
    setEmployers(updated); save(updated);
    setNewEmp({ key: '', name: '', tenant: '', site_id: '', base_url: '' }); setShowAdd(false);
  };

  const remove = (key) => {
    const updated = { ...employers };
    delete updated[key];
    setEmployers(updated); save(updated);
  };

  if (!employers) return <div className="text-xs text-slate-500 py-4">Loading Workday employers…</div>;

  const empList = Object.entries(employers);
  const enabled = empList.filter(([,v]) => v.enabled !== false).length;

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-500">
        {enabled}/{empList.length} employers active. The Workday scraper searches all enabled employers for matching job titles.
        <InfoTip text="Workday is a popular ATS used by enterprise companies. ApplyPilot hits their undocumented JSON API directly — no browser required. Disable employers you don't want to search, or add new ones using the Workday URL format: https://[tenant].wd[N].myworkdayjobs.com" />
      </p>
      <div className="max-h-72 overflow-y-auto flex flex-col gap-1 pr-1">
        {empList.map(([key, emp]) => {
          const on = emp.enabled !== false;
          return (
            <div key={key} className={`flex items-center gap-3 px-3 py-2 rounded-lg border transition-colors ${on ? 'border-slate-700 bg-slate-900/50' : 'border-slate-800 bg-slate-900/20 opacity-50'}`}>
              <button onClick={() => toggle(key)}
                className={`w-8 h-4 rounded-full transition-colors flex-shrink-0 relative ${on ? 'bg-blue-500' : 'bg-slate-600'}`}>
                <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-all ${on ? 'left-4' : 'left-0.5'}`} />
              </button>
              <div className="flex-1 min-w-0">
                <span className="text-sm text-slate-300">{emp.name || key}</span>
                <span className="text-xs text-slate-600 ml-2 truncate">{emp.base_url}</span>
              </div>
              <button onClick={() => remove(key)} className="text-slate-700 hover:text-red-400 text-xs px-1 transition-colors">✕</button>
            </div>
          );
        })}
      </div>
      {!showAdd ? (
        <button onClick={() => setShowAdd(true)} className="text-xs text-blue-400 hover:text-blue-300 text-left transition-colors">+ Add employer</button>
      ) : (
        <div className="border border-slate-700 rounded-xl p-4 flex flex-col gap-3">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Add Workday Employer</div>
          <div className="grid grid-cols-2 gap-2">
            {[['key','Key (unique ID, e.g. amazon)'],['name','Display name'],['tenant','Tenant (e.g. amazon)'],['site_id','Site ID (e.g. External)'],['base_url','Base URL (https://tenant.wdN.myworkdayjobs.com)']].map(([field, ph]) => (
              <input key={field} placeholder={ph} value={newEmp[field]} onChange={e => setNewEmp(p => ({...p, [field]: e.target.value}))}
                className={`bg-slate-900 border border-slate-600 text-slate-200 text-xs rounded-lg px-2 py-1.5 focus:outline-none focus:border-blue-500 ${field === 'base_url' ? 'col-span-2' : ''}`} />
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={addEmployer} className="px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white transition-colors">Add</button>
            <button onClick={() => setShowAdd(false)} className="px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-slate-200 transition-colors">Cancel</button>
          </div>
        </div>
      )}
      <button onClick={() => save(employers)} disabled={saving}
        className="px-4 py-2 rounded-lg text-xs font-medium border border-slate-600 text-slate-300 hover:bg-slate-700 transition-colors disabled:opacity-50">
        {saving ? 'Saving…' : 'Save Workday Config'}
      </button>
    </div>
  );
}

// ── Config Tab ────────────────────────────────────────────────────────────

const JOBSPY_SITES = ['indeed','linkedin','zip_recruiter','glassdoor','google'];

function ConfigTab({ onStatsUpdate }) {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null);
  const [purgeInput, setPurgeInput] = useState('');
  const [showPurge, setShowPurge] = useState(false);
  const [purging, setPurging] = useState(false);

  useEffect(() => {
    fetch('/api/config/searches').then(r => r.json()).then(setCfg).catch(() => setToast({ ok: false, text: 'Failed to load config' }));
  }, []);

  const setC = (path, val) => setCfg(c => {
    const n = JSON.parse(JSON.stringify(c));
    const keys = path.split('.');
    let obj = n;
    for (let i = 0; i < keys.length - 1; i++) { if (!obj[keys[i]]) obj[keys[i]] = {}; obj = obj[keys[i]]; }
    obj[keys[keys.length - 1]] = val;
    return n;
  });

  const save = async () => {
    setSaving(true);
    try {
      await fetch('/api/config/searches', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cfg) });
      setToast({ ok: true, text: 'Config saved!' });
    } catch { setToast({ ok: false, text: 'Failed to save config' }); }
    setSaving(false);
  };

  const doPurge = async () => {
    if (purgeInput !== 'purge') return;
    setPurging(true);
    const res = await fetch('/api/database', { method: 'DELETE' });
    const data = await res.json();
    setPurging(false);
    setShowPurge(false);
    setPurgeInput('');
    setToast({ ok: true, text: `Deleted ${data.deleted} jobs from database` });
    onStatsUpdate();
  };

  if (!cfg) return <div className="flex justify-center py-20 text-slate-500">Loading config…</div>;

  const defaults = cfg.defaults || {};
  const sites = cfg.sites || [];
  const queries = cfg.queries || [];
  const locationAccept = (cfg.location_accept || []).join('\\n');
  const locationReject = (cfg.location_reject_non_remote || []).join('\\n');
  const includeTitle = (cfg.include_title_any || []).join('\\n');
  const excludeTitle = (cfg.exclude_titles || []).join('\\n');
  const rejectPatterns = (cfg.description_reject_patterns || []).join('\\n');

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 flex flex-col gap-5">
      <Toast msg={toast} onClose={() => setToast(null)} />

      <SectionCard title="Job Boards">
        <p className="text-xs text-slate-500 mb-3">Select which job boards to scrape during the discover stage. Enabling more boards finds more jobs but takes longer.
          <InfoTip text="Indeed and LinkedIn have the widest coverage. Glassdoor includes salary data. Google aggregates from many sources. ZipRecruiter skews US-focused." />
        </p>
        <div className="flex flex-wrap gap-3">
          {JOBSPY_SITES.map(s => (
            <label key={s} className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={sites.includes(s)} onChange={e => {
                const updated = e.target.checked ? [...sites, s] : sites.filter(x => x !== s);
                setC('sites', updated);
              }} className="w-4 h-4 accent-blue-500 rounded" />
              <span className="text-sm text-slate-300 capitalize">{s.replace('_', ' ')}</span>
            </label>
          ))}
        </div>
      </SectionCard>

      <SectionCard title="Search Parameters">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400 flex items-center">
              Results per site: {defaults.results_per_site ?? 75}
              <InfoTip text="Maximum number of job listings to fetch per site per search query. Higher values give more coverage but slow down the discover stage and may hit rate limits." />
            </label>
            <input type="range" min="10" max="200" step="5" value={defaults.results_per_site ?? 75}
              onChange={e => setC('defaults.results_per_site', Number(e.target.value))} />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400 flex items-center">
              Max job age (hours): {defaults.hours_old ?? 120}
              <InfoTip text="Only fetch jobs posted within this many hours. Lower values (24–48h) find the freshest postings. Higher values (168h = 1 week) give more results but include older listings." />
            </label>
            <input type="range" min="24" max="720" step="24" value={defaults.hours_old ?? 120}
              onChange={e => setC('defaults.hours_old', Number(e.target.value))} />
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Search Queries">
        <div className="flex flex-col gap-2">
          {queries.map((q, i) => (
            <div key={i} className="flex items-center gap-2">
              <input type="text" value={q.query || ''} onChange={e => {
                const updated = [...queries]; updated[i] = { ...updated[i], query: e.target.value }; setC('queries', updated);
              }} className="flex-1 bg-slate-900 border border-slate-600 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500" placeholder="Search query…" />
              <select value={q.tier || 1} onChange={e => {
                const updated = [...queries]; updated[i] = { ...updated[i], tier: Number(e.target.value) }; setC('queries', updated);
              }} className="bg-slate-900 border border-slate-600 text-slate-300 text-sm rounded-lg px-2 py-2 focus:outline-none w-20">
                <option value={1}>Tier 1</option><option value={2}>Tier 2</option><option value={3}>Tier 3</option>
              </select>
              <button onClick={() => setC('queries', queries.filter((_, j) => j !== i))} className="text-red-400 hover:text-red-300 px-2 py-1 text-sm">✕</button>
            </div>
          ))}
          <button onClick={() => setC('queries', [...queries, { query: '', tier: 2 }])}
            className="mt-1 px-3 py-2 rounded-lg text-sm border border-dashed border-slate-600 text-slate-400 hover:border-blue-500 hover:text-blue-400 transition-colors">
            + Add Query
          </button>
        </div>
      </SectionCard>

      <SectionCard title="Location Filters">
        <p className="text-xs text-slate-500 mb-3">Applied during the discover stage to pre-filter jobs by their listed location field — before full description is scraped.
          <InfoTip text="Accept patterns: only keep jobs whose location matches one of these (e.g. 'Remote', 'Worldwide'). Reject patterns: drop jobs whose location matches (e.g. 'United States'). Leave accept empty to allow all locations." />
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400">Accept patterns (one per line)</label>
            <textarea rows={6} value={locationAccept} onChange={e => setC('location_accept', e.target.value.split('\\n').map(s => s.trim()).filter(Boolean))}
              className="bg-slate-900 border border-slate-600 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500 resize-none font-mono" />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400">Reject patterns (one per line)</label>
            <textarea rows={6} value={locationReject} onChange={e => setC('location_reject_non_remote', e.target.value.split('\\n').map(s => s.trim()).filter(Boolean))}
              className="bg-slate-900 border border-slate-600 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500 resize-none font-mono" />
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Title Filters">
        <p className="text-xs text-slate-500 mb-3">Applied during discover to filter jobs by title before any LLM processing.
          <InfoTip text="Include list: if non-empty, only jobs whose title contains at least one of these terms are kept. Exclude list: jobs whose title contains any of these are always dropped. Title matching is case-insensitive." />
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400">Include if title contains ANY (one per line)</label>
            <textarea rows={8} value={includeTitle} onChange={e => setC('include_title_any', e.target.value.split('\\n').map(s => s.trim()).filter(Boolean))}
              className="bg-slate-900 border border-slate-600 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500 resize-none font-mono" />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-slate-400">Exclude if title contains ANY (one per line)</label>
            <textarea rows={8} value={excludeTitle} onChange={e => setC('exclude_titles', e.target.value.split('\\n').map(s => s.trim()).filter(Boolean))}
              className="bg-slate-900 border border-slate-600 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500 resize-none font-mono" />
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Workday Employers">
        <WorkdayConfig toast={toast} setToast={setToast} />
      </SectionCard>

      <SectionCard title="Description Reject Patterns">
        <p className="text-xs text-slate-500 mb-3">Jobs whose full description matches any of these phrases (case-insensitive) will be auto-filtered as country-restricted remote. One pattern per line.</p>
        <textarea rows={10} value={rejectPatterns} onChange={e => setC('description_reject_patterns', e.target.value.split('\\n').map(s => s.trim()).filter(Boolean))}
          className="w-full bg-slate-900 border border-slate-600 text-slate-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500 resize-y font-mono" />
      </SectionCard>

      <button onClick={save} disabled={saving}
        className="w-full py-3 rounded-xl font-semibold text-sm bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-50">
        {saving ? 'Saving…' : 'Save Config'}
      </button>

      {/* Danger zone */}
      <div className="border border-red-900/50 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-red-400 uppercase tracking-wide mb-2">⚠ Danger Zone</h3>
        <p className="text-sm text-slate-400 mb-4">Delete all jobs from the database. This cannot be undone.</p>
        {!showPurge ? (
          <button onClick={() => setShowPurge(true)} className="px-4 py-2 rounded-lg text-sm font-medium border border-red-700 text-red-400 hover:bg-red-900/30 transition-colors">
            Purge All Jobs
          </button>
        ) : (
          <div className="flex items-center gap-3">
            <input type="text" value={purgeInput} onChange={e => setPurgeInput(e.target.value)} placeholder="Type 'purge' to confirm"
              className="flex-1 bg-slate-900 border border-red-700 text-slate-200 text-sm rounded-lg px-3 py-2 focus:outline-none" />
            <button onClick={doPurge} disabled={purgeInput !== 'purge' || purging}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-red-700 hover:bg-red-600 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
              {purging ? '…' : 'Confirm'}
            </button>
            <button onClick={() => { setShowPurge(false); setPurgeInput(''); }} className="text-slate-400 hover:text-slate-200 text-sm px-2">Cancel</button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Root App ──────────────────────────────────────────────────────────────

function App() {
  const [activeTab, setActiveTab] = useState('apply');
  const [stats, setStats] = useState(null);
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('ap-theme') || 'dark';
    if (saved === 'light') document.documentElement.classList.add('light');
    else document.documentElement.classList.remove('light');
    return saved;
  });

  const toggleTheme = useCallback(() => {
    setTheme(prev => {
      const next = prev === 'dark' ? 'light' : 'dark';
      if (next === 'light') document.documentElement.classList.add('light');
      else document.documentElement.classList.remove('light');
      localStorage.setItem('ap-theme', next);
      return next;
    });
  }, []);

  const fetchStats = useCallback(async () => {
    try { const res = await fetch('/api/stats'); setStats(await res.json()); } catch {}
  }, []);

  useEffect(() => { fetchStats(); }, []);

  return (
    <div className="min-h-screen" style={{ backgroundColor: 'var(--ap-bg)' }}>
      <Header stats={stats} activeTab={activeTab} setActiveTab={setActiveTab} theme={theme} toggleTheme={toggleTheme} />
      {activeTab === 'apply'      && <ReadyToApplyTab onStatsUpdate={fetchStats} />}
      {activeTab === 'jobs'       && <JobsTab onStatsUpdate={fetchStats} />}
      {activeTab === 'untailored' && <UntailoredTab onStatsUpdate={fetchStats} />}
      {activeTab === 'pipeline'   && <PipelineTab onStatsUpdate={fetchStats} />}
      {activeTab === 'profile'    && <ProfileTab />}
      {activeTab === 'config'     && <ConfigTab onStatsUpdate={fetchStats} />}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
</script>
</body>
</html>"""
