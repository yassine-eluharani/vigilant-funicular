"""ApplyPilot Web API — FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from applypilot.config import load_env
from applypilot.web.middleware import (
    RequestIdMiddleware,
    install_request_id_logging,
    request_id_var,  # noqa: F401  (re-exported for other modules)
)
from applypilot.web.routers import auth, jobs, pipeline, config, stream

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
install_request_id_logging()
log = logging.getLogger(__name__)

# Load .env early so all routers see GEMINI_API_KEY / OPENAI_API_KEY / LLM_URL
load_env()

_debug = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")


def _parse_cors_origins(raw: str) -> list[str]:
    """Parse the ``CORS_ORIGINS`` env var, refusing wildcard entries.

    A literal ``*`` collapses CORS into "trust everyone", which combined with
    credentials creates an obvious CSRF foothold. We refuse it outright and
    fall back to an empty list (CORS effectively disabled) so the app can still
    boot in dev without the operator silently shipping a wide-open policy.
    """
    if not raw:
        return []
    parts = [o.strip() for o in raw.split(",") if o.strip()]
    if any(p == "*" for p in parts):
        log.error(
            "CORS_ORIGINS contains '*', which is not allowed. "
            "Set explicit origins (e.g. https://example.com). Falling back to no origins."
        )
        # In production we'd rather refuse to start than ship a wildcard policy.
        if os.environ.get("APPLYPILOT_ENV", "").lower() == "production":
            print(
                "FATAL: CORS_ORIGINS='*' is forbidden in production.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        return [p for p in parts if p != "*"]
    return parts


@asynccontextmanager
async def lifespan(_app):
    from applypilot.database import init_db, cleanup_old_jobs, cleanup_closed_jobs
    from applypilot.web.core import mark_orphan_tasks_on_startup, _periodic_score_loop
    await asyncio.to_thread(init_db)
    await asyncio.to_thread(cleanup_old_jobs, 3)
    await asyncio.to_thread(cleanup_closed_jobs, 7)
    mark_orphan_tasks_on_startup()  # TST-015: flag in-flight tasks lost to restart

    # Continuous scoring + auto-tailor — picks up newly-discovered jobs
    # without needing the user to open /apply. Runs forever, cancelled when
    # FastAPI shuts down. Tunable via AUTO_SCORE_INTERVAL_SECONDS.
    score_task = asyncio.create_task(_periodic_score_loop())
    try:
        yield
    finally:
        score_task.cancel()
        try:
            await score_task
        except (asyncio.CancelledError, Exception):
            pass

app = FastAPI(
    title="ApplyPilot API",
    docs_url="/api/docs" if _debug else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Request-ID middleware must be added before CORS so it wraps every response
# (including CORS preflights) with an X-Request-ID header.
app.add_middleware(RequestIdMiddleware)

_cors_origins = _parse_cors_origins(os.environ.get("CORS_ORIGINS", ""))
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=bool(_cors_origins),  # credentials require explicit origins
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health", include_in_schema=False)
@app.get("/api/health", include_in_schema=False)
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


app.include_router(auth.router)           # public — no auth dependency
app.include_router(jobs.router)
app.include_router(pipeline.router)
app.include_router(config.router)
app.include_router(stream.router)
