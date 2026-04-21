"""ApplyPilot Web API — FastAPI application entry point."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from applypilot.config import load_env
from applypilot.web.routers import auth, jobs, pipeline, config, stream

# Load .env early so all routers see GEMINI_API_KEY / OPENAI_API_KEY / LLM_URL
load_env()

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(_app):
    from applypilot.database import init_db
    init_db()
    yield

app = FastAPI(title="ApplyPilot API", docs_url="/api/docs", redoc_url=None, lifespan=lifespan)

_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)   # public — no auth dependency
app.include_router(jobs.router)
app.include_router(pipeline.router)
app.include_router(config.router)
app.include_router(stream.router)
