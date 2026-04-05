"""Config routes — profile, searches, employers, env keys, resume."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from applypilot.config import PROFILE_PATH, SEARCH_CONFIG_PATH, CONFIG_DIR, APP_DIR
from applypilot.web.core import _start_task

EMPLOYERS_PATH = CONFIG_DIR / "employers.yaml"

router = APIRouter()


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
async def update_searches(request: Request) -> JSONResponse:
    data = await request.json()
    SEARCH_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEARCH_CONFIG_PATH.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
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
    import subprocess
    try:
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
# System status
# ---------------------------------------------------------------------------

@router.get("/api/system/status")
def system_status() -> JSONResponse:
    import shutil
    from applypilot.config import get_tier
    from applypilot.llm import _detect_provider

    tier = get_tier()
    tier_labels = {1: "Discovery Only", 2: "AI Scoring & Tailoring", 3: "Full Auto-Apply"}
    provider, model, _key = _detect_provider()

    return JSONResponse({
        "tier": tier,
        "tier_label": tier_labels.get(tier, "Unknown"),
        "llm_provider": provider,
        "llm_model": model,
        "has_chrome": bool(
            shutil.which("google-chrome") or
            shutil.which("chromium") or
            shutil.which("chromium-browser")
        ),
        "has_claude_cli": bool(shutil.which("claude")),
    })
