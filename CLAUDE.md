# ApplyPilot

AI-powered job application automation pipeline. Discovers jobs, scores them against your profile, tailors resumes, generates cover letters, and auto-submits applications via browser automation.

**This is a fullstack monorepo** — Next.js frontend + FastAPI backend + Docker.

## Tech Stack

- **Frontend**: Next.js 16 (App Router), React 19, Tailwind CSS v4, TypeScript
- **Backend**: Python 3.11+, FastAPI, SQLite (WAL mode), Playwright, Rich
- **LLM**: Gemini (default), OpenAI, or local (Ollama/llama.cpp) — auto-detected from env vars
- **Auto-apply**: Claude Code CLI + Chrome CDP + Playwright MCP server
- **Infra**: Docker + Docker Compose (dev + prod), nginx reverse proxy

## Project Layout

```
applypilot/
├── backend/
│   ├── src/applypilot/
│   │   ├── web/
│   │   │   ├── server.py           # FastAPI app entry point
│   │   │   ├── core.py             # Shared task registry, URL helpers
│   │   │   └── routers/            # jobs, pipeline, config, apply, stream
│   │   ├── discovery/              # jobspy, workday, smartextract, filter
│   │   ├── enrichment/detail.py    # Full description + apply URL cascade
│   │   ├── scoring/                # scorer, tailor, cover_letter, pdf, validator
│   │   ├── apply/                  # launcher, chrome, prompt, dashboard
│   │   ├── config/                 # employers.yaml, sites.yaml, searches.example.yaml
│   │   ├── database.py             # SQLite schema, thread-local connections
│   │   ├── llm.py                  # Unified LLM client (Gemini/OpenAI/local)
│   │   ├── pipeline.py             # 7-stage pipeline orchestrator
│   │   └── config.py               # Paths (APPLYPILOT_DIR), tier system
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── layout.tsx              # Root layout: Sidebar + ToastProvider
│   │   ├── jobs/page.tsx           # Jobs Dashboard
│   │   ├── pipeline/page.tsx       # Pipeline Control
│   │   ├── profile/page.tsx        # Profile & Config (5 tabs)
│   │   └── apply/page.tsx          # Apply Tracker
│   ├── components/
│   │   ├── ui/Toast.tsx            # Global toast notifications
│   │   ├── layout/Sidebar.tsx      # Navigation sidebar
│   │   ├── jobs/                   # JobCard, JobFilters, JobDetailDrawer, ScoreBadge
│   │   ├── pipeline/               # StageSelector, LogStream, FunnelChart
│   │   └── apply/                  # WorkerCard (inline in page)
│   ├── lib/
│   │   ├── api.ts                  # Typed fetch wrappers for all endpoints
│   │   ├── types.ts                # Job, Stats, Task, WorkerState, Profile, SystemStatus
│   │   └── hooks/                  # useJobs, useStats, useSSE, useApplyWorkers
│   ├── next.config.ts              # output: standalone, /api proxy rewrite
│   └── Dockerfile
├── nginx/
│   ├── nginx.conf                  # /api/ → backend, /* → frontend, SSE-safe
│   └── Dockerfile
├── docker-compose.yml              # Base (shared services, data volume)
├── docker-compose.dev.yml          # Hot reload, direct ports, no nginx
├── docker-compose.prod.yml         # Optimized builds, nginx on :80/:443
├── data/                           # Bind-mounted volume: DB, profile, resumes
└── .env.example
```

## Pipeline Stages

1. **discover** — Scrape job boards + Workday portals + custom sites → store URLs in DB
2. **enrich** — Fetch full descriptions and apply URLs (3-tier: JSON-LD → CSS → LLM)
3. **filter** — Pre-scoring location/country filter via regex (saves LLM tokens)
4. **score** — LLM scores job-candidate fit 1–10 using profile + resume
5. **tailor** — LLM generates tailored resume JSON (max 5 retries, validated)
6. **cover** — LLM generates cover letter (max 5 retries, validated)
7. **pdf** — Convert tailored resumes/cover letters to PDF

## User Config (mounted at `data/` → `/data` in Docker)

- `profile.json` — Name, email, location, work auth, skills, resume facts, EEO
- `searches.yaml` — Queries, locations, boards, title filters, location filters
- `resume.txt` / `resume.pdf` — Master resume
- `.env` — `GEMINI_API_KEY`, `OPENAI_API_KEY`, `LLM_MODEL`, `LLM_URL`, `CAPSOLVER_API_KEY`

## Tier System

- **Tier 1** (Discovery): Python only → discover, enrich, filter
- **Tier 2** (AI Scoring): + LLM API key → score, tailor, cover, pdf
- **Tier 3** (Auto-Apply): + Claude Code CLI + Chrome → apply

## Key Patterns

- **Config path**: `APPLYPILOT_DIR` env var (defaults to `~/.applypilot`, set to `/data` in Docker)
- **Database**: Single `jobs` table, URL as primary key, SQLite WAL mode, thread-local connections
- **LLM client**: Auto-detects provider from env vars. Gemini tries OpenAI-compat first, falls back to native API on 403/404. Exponential backoff on rate limits.
- **Validation**: 42 banned words, 20 LLM leak phrases, fabrication watchlist. Modes: strict/normal/lenient.
- **SSE**: `/api/stream/task/{id}` for pipeline logs, `/api/stream/apply` for worker state
- **Apply workers**: Run in separate subprocess (`multiprocessing.Process`) to avoid FastAPI signal conflicts

## Development

```bash
# Start dev environment
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Backend only (no Docker)
cd backend && pip install -e ".[dev]"
APPLYPILOT_DIR=./data uvicorn applypilot.web.server:app --reload --port 8000

# Frontend only (no Docker)
cd frontend && npm install && npm run dev

# API docs (dev only)
open http://localhost:8000/api/docs
```

## Production

```bash
# Build and start prod
mkdir -p data
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

# Access: http://localhost (nginx on port 80)
```
