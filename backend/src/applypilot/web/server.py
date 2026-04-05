"""ApplyPilot Web API — FastAPI application entry point."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from applypilot.web.routers import jobs, pipeline, config, apply, stream

app = FastAPI(title="ApplyPilot API", docs_url="/api/docs", redoc_url=None)

_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(pipeline.router)
app.include_router(config.router)
app.include_router(apply.router)
app.include_router(stream.router)
