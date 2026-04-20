"""Config routes — profile, searches, employers, env keys, resume."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from applypilot.config import PROFILE_PATH, SEARCH_CONFIG_PATH, CONFIG_DIR, APP_DIR
from applypilot.web.auth import get_current_user
from applypilot.web.core import _start_task

EMPLOYERS_PATH = CONFIG_DIR / "employers.yaml"

router = APIRouter(dependencies=[Depends(get_current_user)])


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@router.get("/api/profile")
def get_profile() -> JSONResponse:
    if not PROFILE_PATH.exists():
        raise HTTPException(status_code=404, detail="profile.json not found. Create it via the Profile page.")
    return JSONResponse(json.loads(PROFILE_PATH.read_text(encoding="utf-8")))


@router.put("/api/profile")
async def update_profile(request: Request) -> JSONResponse:
    data = await request.json()
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Searches config
# ---------------------------------------------------------------------------

@router.get("/api/config/searches")
def get_searches() -> JSONResponse:
    if not SEARCH_CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="searches.yaml not found.")
    data = yaml.safe_load(SEARCH_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if "description_reject_patterns" not in data:
        from applypilot.discovery.filter import DEFAULT_REJECT_PATTERNS
        data["description_reject_patterns"] = DEFAULT_REJECT_PATTERNS
    return JSONResponse(data)


@router.put("/api/config/searches")
async def update_searches(request: Request, user: dict = Depends(get_current_user)) -> JSONResponse:
    import json as _json
    data = await request.json()
    SEARCH_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEARCH_CONFIG_PATH.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    # Persist per-user copy so the background scheduler can discover for this user
    try:
        from applypilot.database import get_connection
        conn = get_connection()
        conn.execute(
            "UPDATE users SET searches_json = ? WHERE id = ?",
            (_json.dumps(data), int(user["sub"])),
        )
        conn.commit()
    except Exception:
        pass  # Non-fatal — shared yaml is the source of truth
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Employers registry (Workday)
# ---------------------------------------------------------------------------

@router.get("/api/config/employers")
def get_employers() -> JSONResponse:
    if not EMPLOYERS_PATH.exists():
        return JSONResponse({})
    data = yaml.safe_load(EMPLOYERS_PATH.read_text(encoding="utf-8")) or {}
    return JSONResponse(data.get("employers", {}))


@router.put("/api/config/employers")
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
# .env API keys
# ---------------------------------------------------------------------------

_SECRET_KEYS = {"GEMINI_API_KEY", "OPENAI_API_KEY", "CAPSOLVER_API_KEY"}
_ALL_ENV_KEYS = _SECRET_KEYS | {"LLM_URL", "LLM_MODEL"}


@router.get("/api/config/env")
def get_env_config() -> JSONResponse:
    env_path = APP_DIR / ".env"
    result: dict = {k: None for k in _ALL_ENV_KEYS}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k in _ALL_ENV_KEYS:
                result[k] = "***" if k in _SECRET_KEYS and v else (v or None)
    return JSONResponse(result)


@router.put("/api/config/env")
async def update_env_config(request: Request) -> JSONResponse:
    data = await request.json()
    env_path = APP_DIR / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            existing[k.strip()] = v.strip()

    for k, v in data.items():
        if v in ("", None, "***"):   # "***" means unchanged — don't overwrite
            if v in ("", None):
                existing.pop(k, None)
        else:
            existing[k] = v

    env_path.write_text(
        "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n",
        encoding="utf-8",
    )
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Resume text
# ---------------------------------------------------------------------------

@router.get("/api/config/resume")
def get_resume_text() -> JSONResponse:
    from applypilot.config import RESUME_PATH
    if not RESUME_PATH.exists():
        return JSONResponse({"text": "", "exists": False})
    return JSONResponse({"text": RESUME_PATH.read_text(encoding="utf-8"), "exists": True})


@router.put("/api/config/resume")
async def update_resume_text(request: Request) -> JSONResponse:
    from applypilot.config import RESUME_PATH
    body = await request.json()
    RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESUME_PATH.write_text(body.get("text", ""), encoding="utf-8")
    return JSONResponse({"ok": True})


@router.post("/api/config/resume/upload")
async def upload_resume_pdf(request: Request) -> JSONResponse:
    form = await request.form()
    file: UploadFile = form.get("file")  # type: ignore
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    dest = APP_DIR / "resume.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    dest.write_bytes(content)

    task_id = _start_task(_extract_resume_text, dest)
    return JSONResponse({"ok": True, "size": len(content), "task_id": task_id})


def _extract_resume_text(pdf_path: Path) -> dict:
    from applypilot.config import RESUME_PATH
    from pypdf import PdfReader
    try:
        reader = PdfReader(str(pdf_path))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        if text:
            RESUME_PATH.write_text(text, encoding="utf-8")
            return {"extracted": True, "chars": len(text)}
    except Exception:
        pass
    return {"extracted": False}


# ---------------------------------------------------------------------------
# Resume CV parse (LLM extraction → profile fields)
# ---------------------------------------------------------------------------

@router.post("/api/config/resume/parse")
async def parse_resume(request: Request) -> JSONResponse:
    """Parse resume text with LLM and return extracted profile fields."""
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")

    from applypilot.llm import get_client
    import asyncio, re as _re

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
        return client.chat([{"role": "user", "content": prompt}], temperature=0.1)

    try:
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, _parse)
        match = _re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise ValueError("No JSON in response")
        extracted = json.loads(match.group())
        return JSONResponse({"ok": True, "extracted": extracted})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parse failed: {e}")


# ---------------------------------------------------------------------------
# System status
# ---------------------------------------------------------------------------

@router.get("/api/system/status")
def system_status() -> JSONResponse:
    from applypilot.config import get_tier
    from applypilot.llm import _detect_provider

    tier = get_tier()
    tier_labels = {1: "Discovery Only", 2: "AI Scoring & Tailoring"}
    provider, model, _key = _detect_provider()

    return JSONResponse({
        "tier": tier,
        "tier_label": tier_labels.get(tier, "Unknown"),
        "llm_provider": provider,
        "llm_model": model,
    })


# ---------------------------------------------------------------------------
# Scheduler status
# ---------------------------------------------------------------------------

@router.get("/api/scheduler/status")
def scheduler_status() -> JSONResponse:
    from applypilot.scheduler import last_sync_info
    return JSONResponse(last_sync_info())


@router.post("/api/scheduler/trigger")
def scheduler_trigger() -> JSONResponse:
    """Manually kick off a background discovery cycle (runs async)."""
    from applypilot.web.core import _start_task
    from applypilot.scheduler import run_cycle
    task_id = _start_task(run_cycle)
    return JSONResponse({"ok": True, "task_id": task_id})
