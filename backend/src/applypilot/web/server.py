"""ApplyPilot Web API — FastAPI application entry point."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from applypilot.config import load_env
from applypilot.web.routers import auth, jobs, pipeline, config, stream, stripe_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Load .env early so all routers see GEMINI_API_KEY / OPENAI_API_KEY / LLM_URL
load_env()

_debug = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")


@asynccontextmanager
async def lifespan(_app):
    from applypilot.database import init_db, cleanup_old_jobs, cleanup_closed_jobs
    init_db()
    cleanup_old_jobs(days=60)
    cleanup_closed_jobs(grace_days=7)
    yield

app = FastAPI(
    title="ApplyPilot API",
    docs_url="/api/docs" if _debug else None,
    redoc_url=None,
    lifespan=lifespan,
)

_raw_origins = os.environ.get("CORS_ORIGINS", "")
_cors_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()] if _raw_origins else []
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=bool(_cors_origins),  # credentials require explicit origins
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health", include_in_schema=False)
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


app.include_router(auth.router)           # public — no auth dependency
app.include_router(stripe_router.router)  # public — webhook must be unauthenticated
app.include_router(jobs.router)
app.include_router(pipeline.router)
app.include_router(config.router)
app.include_router(stream.router)
