"""Config routes — profile, searches, env keys, resume.

BE-002: most handlers in this module are sync ``def`` routes that Starlette
already dispatches on the threadpool, so DB calls inside them don't block the
event loop. Async handlers (``upload_resume_pdf``, ``parse_resume``) offload
their blocking file/LLM work via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re as _re
from pathlib import Path

import yaml
from fastapi import APIRouter, Body, Depends, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from typing import Any

from applypilot.config import APP_DIR, PROFILE_PATH, SEARCH_CONFIG_PATH
from applypilot.database import get_connection
from applypilot.web.auth import get_current_user
from applypilot.web.core import _start_task, parse_limiter, trigger_score_for_user
from applypilot.web.schemas import (
    EnvConfigResponse,
    NotificationsResponse,
    NotificationsUpdateRequest,
    ParseResumeRequest,
    ParseResumeResponse,
    ProfileUpdateResponse,
    ResumeResponse,
    ResumeUpdateRequest,
    ResumeUpdateResponse,
    ResumeUploadResponse,
    SchedulerStatusResponse,
    SearchesUpdateResponse,
    SystemStatusResponse,
)

router = APIRouter(dependencies=[Depends(get_current_user)])

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@router.get("/api/profile")
def get_profile(user: dict = Depends(get_current_user)) -> JSONResponse:
    conn = get_connection()
    row = conn.execute("SELECT profile_json FROM users WHERE id = ?", (user["id"],)).fetchone()
    if row and row[0]:
        return JSONResponse(json.loads(row[0]))
    # Fall back to filesystem profile for existing single-user installs
    if not PROFILE_PATH.exists():
        raise HTTPException(status_code=404, detail="profile.json not found. Create it via the Profile page.")
    return JSONResponse(json.loads(PROFILE_PATH.read_text(encoding="utf-8")))


@router.put("/api/profile", response_model=ProfileUpdateResponse)
def update_profile(
    data: dict[str, Any] = Body(...),
    user: dict = Depends(get_current_user),
) -> ProfileUpdateResponse:
    """Persist the deeply-partial profile dict the frontend posted.

    We accept ``dict[str, Any]`` rather than the strict ``Profile`` model
    because the model would discard unknown nested keys via ``model_dump``
    round-tripping, breaking forward-compat with new UI fields. The OpenAPI
    shape is documented via ``schemas.Profile``.
    """
    conn = get_connection()
    conn.execute(
        "UPDATE users SET profile_json = ? WHERE id = ?",
        (json.dumps(data, ensure_ascii=False), user["id"]),
    )
    conn.commit()
    task_id = trigger_score_for_user(user["id"])
    return ProfileUpdateResponse(ok=True, scoring_task_id=task_id)


# ---------------------------------------------------------------------------
# Searches config
# ---------------------------------------------------------------------------

@router.get("/api/config/searches")
def get_searches(user: dict = Depends(get_current_user)) -> JSONResponse:
    conn = get_connection()
    row = conn.execute("SELECT searches_json FROM users WHERE id = ?", (user["id"],)).fetchone()
    if row and row[0]:
        data = json.loads(row[0])
    elif SEARCH_CONFIG_PATH.exists():
        data = yaml.safe_load(SEARCH_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    else:
        raise HTTPException(status_code=404, detail="searches.yaml not found.")
    if "description_reject_patterns" not in data:
        # Kept lazy: applypilot.discovery is the legacy single-user discovery
        # module; dragging it in at module load just to read DEFAULT_REJECT_PATTERNS
        # would pull jobspy/scraping deps into every request path. Lazy import
        # keeps the cold-start footprint small.
        from applypilot.discovery.filter import DEFAULT_REJECT_PATTERNS
        data["description_reject_patterns"] = DEFAULT_REJECT_PATTERNS
    return JSONResponse(data)


@router.put("/api/config/searches", response_model=SearchesUpdateResponse)
def update_searches(
    data: dict[str, Any] = Body(...),
    user: dict = Depends(get_current_user),
) -> SearchesUpdateResponse:
    """Round-trip the searches config blob.

    Accepts ``dict[str, Any]`` instead of the strict ``SearchConfig`` model
    so the GET-injected ``description_reject_patterns`` (and anything else
    the frontend echoes back unchanged) survive a save unmodified. The
    OpenAPI shape is documented via ``schemas.SearchConfig``.
    """
    conn = get_connection()
    conn.execute(
        "UPDATE users SET searches_json = ? WHERE id = ?",
        (json.dumps(data), user["id"]),
    )
    conn.commit()
    return SearchesUpdateResponse(ok=True)


# ---------------------------------------------------------------------------
# Employers registry — REMOVED.
#
# The previous GET/PUT /api/config/employers endpoints read/wrote a
# process-global YAML file with no per-user scoping (SEC-004, SEC-011, BE-014).
# Any authenticated user could clobber the shared employers config for the
# entire tenant pool, and the GET leaked global discovery configuration
# cross-tenant. The discovery worker now lives in a separate repo
# (applypilot-discovery) and owns its own employer registry, so per-user
# overrides are out of scope here. If we ever reintroduce per-user
# employer preferences, store them in users.profile_json scoped by user["id"].
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# .env presence flags (read-only)
#
# Configuration is a deploy-time concern: the .env file is owned by the
# operator, never by an authenticated end-user. We expose ONLY boolean
# presence flags so the UI can show "LLM is configured" without leaking
# secrets, key prefixes, or distinguishing which provider is in use beyond
# what is needed to render status. The non-secret model name is included
# because it is already surfaced via /api/system/status.
# ---------------------------------------------------------------------------


@router.get("/api/config/env", response_model=EnvConfigResponse)
def get_env_config() -> EnvConfigResponse:
    """Return boolean presence flags for configured providers.

    Never returns secret material (no masked keys, no partial echoes, no
    raw values). Reads from the live process environment so it reflects
    what the running server actually sees.
    """
    return EnvConfigResponse(
        gemini_configured=bool(os.getenv("GEMINI_API_KEY")),
        openai_configured=bool(os.getenv("OPENAI_API_KEY")),
        llm_url_set=bool(os.getenv("LLM_URL")),
        llm_model=os.getenv("LLM_MODEL") or None,
    )


# ---------------------------------------------------------------------------
# Resume text
# ---------------------------------------------------------------------------

@router.get("/api/config/resume", response_model=ResumeResponse)
def get_resume_text(user: dict = Depends(get_current_user)) -> ResumeResponse:
    conn = get_connection()
    row = conn.execute("SELECT resume_text FROM users WHERE id = ?", (user["id"],)).fetchone()
    if row and row[0]:
        return ResumeResponse(text=row[0], exists=True)
    # Fall back to filesystem for existing single-user installs
    from applypilot.config import RESUME_PATH
    if not RESUME_PATH.exists():
        return ResumeResponse(text="", exists=False)
    return ResumeResponse(text=RESUME_PATH.read_text(encoding="utf-8"), exists=True)


@router.put("/api/config/resume", response_model=ResumeUpdateResponse)
def update_resume_text(
    body: ResumeUpdateRequest, user: dict = Depends(get_current_user)
) -> ResumeUpdateResponse:
    conn = get_connection()
    conn.execute(
        "UPDATE users SET resume_text = ? WHERE id = ?",
        (body.text, user["id"]),
    )
    conn.commit()
    task_id = trigger_score_for_user(user["id"])
    return ResumeUpdateResponse(ok=True, scoring_task_id=task_id)


def _persist_uploaded_pdf(dest: Path, content: bytes) -> None:
    """Sync helper: ensure parent dir exists and write the PDF blob."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)


@router.post("/api/config/resume/upload", response_model=ResumeUploadResponse)
async def upload_resume_pdf(
    request: Request, user: dict = Depends(get_current_user)
) -> ResumeUploadResponse:
    """Multipart PDF upload — kept on Request so we can read ``form()`` directly.

    Pydantic doesn't model multipart bodies cleanly; the response is typed.
    """
    form = await request.form()
    file: UploadFile = form.get("file")  # type: ignore
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    dest = APP_DIR / "users" / str(user["id"]) / "resume.pdf"
    content = await file.read()
    # BE-002: file I/O can block on slow disks / NFS — push it to the threadpool.
    await asyncio.to_thread(_persist_uploaded_pdf, dest, content)

    task_id = _start_task(_extract_resume_text, dest, user["id"])
    return ResumeUploadResponse(ok=True, size=len(content), task_id=task_id)


def _extract_resume_text(pdf_path: Path, user_id: int | None = None) -> dict:
    from applypilot.config import RESUME_PATH
    from pypdf import PdfReader
    try:
        reader = PdfReader(str(pdf_path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if text:
            RESUME_PATH.write_text(text, encoding="utf-8")
            if user_id is not None:
                conn = get_connection()
                conn.execute("UPDATE users SET resume_text = ? WHERE id = ?", (text, user_id))
                conn.commit()
            return {"extracted": True, "chars": len(text)}
    except Exception:
        pass
    return {"extracted": False}


# ---------------------------------------------------------------------------
# Resume CV parse (LLM extraction → profile fields)
# ---------------------------------------------------------------------------

@router.post("/api/config/resume/parse", response_model=ParseResumeResponse)
async def parse_resume(
    body: ParseResumeRequest, user: dict = Depends(get_current_user)
) -> ParseResumeResponse:
    """Parse resume text with LLM and return extracted profile fields.

    Rate-limited per user: parse-CV is potentially heavier than a tailor
    (large free-form text + JSON-mode LLM call), so we use a tighter
    sliding window than tailor/cover (SEC-012).
    """
    parse_limiter.check(user["id"])

    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")

    # `applypilot.llm` is intentionally lazy: get_client() probes the env to
    # pick a provider on first call and we don't want to do that at import
    # time (which would make tests that patch env vars after import flaky).
    from applypilot.llm import get_client

    prompt = (
        "You are a resume parser. Extract structured information from the resume text below.\n"
        "Return ONLY a valid JSON object with these exact keys (omit keys you cannot find):\n"
        "{\n"
        '  "full_name": "",\n'
        '  "email": "",\n'
        '  "phone": "",\n'
        '  "city": "",\n'
        '  "country": "",\n'
        '  "linkedin_url": "",\n'
        '  "github_url": "",\n'
        '  "portfolio_url": "",\n'
        '  "target_role": "",\n'
        '  "years_of_experience_total": 0,\n'
        '  "education_level": "",\n'
        '  "skills": {"languages": [], "frameworks": [], "devops": [], "databases": [], "tools": []},\n'
        '  "companies": [],\n'
        '  "projects": [],\n'
        '  "school": "",\n'
        '  "metrics": []\n'
        "}\n\n"
        "Resume text:\n"
        f"{text[:8000]}"
    )

    def _parse() -> str:
        client = get_client()
        return client.chat([{"role": "user", "content": prompt}], temperature=0.1, json_mode=True)

    try:
        # asyncio.to_thread (Python 3.9+) replaces the deprecated
        # get_event_loop().run_in_executor(None, ...) pattern (BE-015).
        raw = await asyncio.to_thread(_parse)
        match = _re.search(r"\{[\s\S]*\}", raw)
        if not match:
            log.error("Resume parse: no JSON in LLM response: %r", raw[:500])
            raise ValueError("No JSON in response")
        extracted = json.loads(match.group())
        return ParseResumeResponse(ok=True, extracted=extracted)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse failed: {e}")


# ---------------------------------------------------------------------------
# Notification preferences
# ---------------------------------------------------------------------------

@router.get("/api/config/notifications", response_model=NotificationsResponse)
def get_notifications(user: dict = Depends(get_current_user)) -> NotificationsResponse:
    conn = get_connection()
    row = conn.execute(
        "SELECT email_notifications FROM users WHERE id = ?", (user["id"],)
    ).fetchone()
    return NotificationsResponse(
        email_notifications=bool(row["email_notifications"]) if row else False,
    )


@router.put("/api/config/notifications", response_model=NotificationsResponse)
def update_notifications(
    body: NotificationsUpdateRequest, user: dict = Depends(get_current_user)
) -> NotificationsResponse:
    enabled = 1 if body.email_notifications else 0
    conn = get_connection()
    conn.execute(
        "UPDATE users SET email_notifications = ? WHERE id = ?", (enabled, user["id"])
    )
    conn.commit()
    return NotificationsResponse(email_notifications=bool(enabled))


# ---------------------------------------------------------------------------
# System status
# ---------------------------------------------------------------------------

@router.get("/api/system/status", response_model=SystemStatusResponse)
def system_status() -> SystemStatusResponse:
    # Kept lazy: `applypilot.config.get_tier` and `applypilot.llm._detect_provider`
    # both read env vars eagerly. Hoisting would freeze the values at import
    # time, defeating the point of `/api/system/status` (which exists to
    # reflect the *live* server config).
    from applypilot.config import get_tier
    from applypilot.llm import _detect_provider

    tier = get_tier()
    tier_labels = {1: "Discovery Only", 2: "AI Scoring & Tailoring"}
    provider, model, _key = _detect_provider()

    return SystemStatusResponse(
        tier=tier,
        tier_label=tier_labels.get(tier, "Unknown"),
        llm_provider=provider,
        llm_model=model,
    )


# ---------------------------------------------------------------------------
# Scheduler status
# ---------------------------------------------------------------------------

@router.get("/api/scheduler/status", response_model=SchedulerStatusResponse)
def scheduler_status() -> SchedulerStatusResponse:
    from applypilot.scheduler import last_sync_info
    info = last_sync_info()
    return SchedulerStatusResponse(
        last_sync=info.get("last_sync"),
        jobs_found=info.get("jobs_found", 0),
    )


