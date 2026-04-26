# ApplyPilot

Multi-user SaaS platform: a background discovery worker continuously populates a shared job database; users log in, see jobs scored against their CV, then tailor resumes and generate cover letters per job.

**Fullstack monorepo** — Next.js frontend + FastAPI backend + Docker.
**Discovery worker** lives in a separate repo (`applypilot-discovery`) and shares the same Turso DB.

## Tech Stack

- **Frontend**: Next.js 16 (App Router), React 19, Tailwind CSS v4, TypeScript
- **Backend**: Python 3.11+, FastAPI, Turso (libSQL via HTTP) or SQLite (WAL mode, dev)
- **Auth**: Clerk (RS256 JWTs — no passwords stored)
- **LLM**: Gemini (default), OpenAI, or local (Ollama/llama.cpp) — auto-detected from env vars
- **Payments**: Stripe Checkout + webhook
- **Infra**: Docker + Docker Compose (dev + prod), nginx reverse proxy

## Project Layout

```
applypilot/
├── backend/
│   ├── src/applypilot/
│   │   ├── web/
│   │   │   ├── server.py           # FastAPI app entry point + lifespan
│   │   │   ├── core.py             # Task registry, URL helpers, auto-scoring, rate limiter
│   │   │   ├── auth.py             # Clerk JWT verify, upsert_user, usage limits
│   │   │   └── routers/
│   │   │       ├── auth.py         # /api/auth/me, /api/auth/upgrade
│   │   │       ├── jobs.py         # /api/jobs, /api/stats, tailor, cover, status mutations
│   │   │       ├── pipeline.py     # /api/pipeline/run, /api/pipeline/maybe-score, /api/tasks
│   │   │       ├── config.py       # profile, searches, resume, env keys, scheduler status
│   │   │       ├── stripe_router.py# /api/stripe/create-checkout, /api/stripe/webhook
│   │   │       └── stream.py       # /api/stream/task/{id} (SSE)
│   │   ├── discovery/              # jobspy, workday, smartextract, filter (kept for reference)
│   │   ├── enrichment/detail.py    # Full description + apply URL cascade
│   │   ├── scoring/                # scorer, tailor, cover_letter, pdf, validator, indexer
│   │   ├── notifications.py        # Email digest (Resend + SMTP fallback)
│   │   ├── database.py             # Schema, migrations, helpers, cleanup_old_jobs
│   │   ├── scheduler.py            # Discovery run tracking helpers (is_stale, last_sync_info)
│   │   ├── llm.py                  # Unified LLM client (Gemini/OpenAI/local)
│   │   ├── pipeline.py             # Score-only pipeline orchestrator
│   │   └── config.py               # Paths (APPLYPILOT_DIR), tier system
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── layout.tsx              # Root layout: Sidebar + ToastProvider
│   │   ├── (dashboard)/
│   │   │   ├── jobs/page.tsx       # Jobs dashboard — auto-scores on mount
│   │   │   ├── pipeline/page.tsx   # Pipeline control (score stage only)
│   │   │   ├── profile/page.tsx    # Profile & config (5 tabs)
│   │   │   └── setup/page.tsx      # Onboarding wizard (4 steps)
│   │   └── (marketing)/
│   │       ├── page.tsx            # Landing page
│   │       └── pricing/page.tsx    # Pricing page
│   ├── components/
│   │   ├── ui/Toast.tsx
│   │   ├── layout/Sidebar.tsx
│   │   └── jobs/                   # JobCard, JobFilters, JobDetailDrawer, ScoreBadge
│   ├── lib/
│   │   ├── api.ts                  # Typed fetch wrappers for all endpoints
│   │   ├── types.ts                # Job, Stats, Task, Profile, UserInfo, SystemStatus
│   │   └── hooks/                  # useJobs, useStats, useSSE
│   ├── next.config.ts              # output: standalone, /api proxy rewrite
│   └── Dockerfile
├── nginx/
│   ├── nginx.conf                  # HTTP + HTTPS, /api/ → backend, SSE-safe
│   └── Dockerfile
├── docker-compose.yml              # Base (shared volumes)
├── docker-compose.dev.yml          # Hot reload, direct ports, no nginx
├── docker-compose.prod.yml         # Optimized builds, nginx on :80/:443
├── setup-ssl.sh                    # Certbot SSL setup helper
├── sync-shared-modules.sh          # Sync shared modules to applypilot-discovery
└── .env.example
```

## Architecture

```
Browser → nginx → Next.js (3000)
                → FastAPI (8000) → Turso DB (shared)
                                                ↑
                              applypilot-discovery worker (separate repo)
                              runs every 2h: discover → enrich → filter → index
```

**Discovery worker** (`applypilot-discovery/`) handles the shared job pool:
1. **discover** — Scrape job boards (JobSpy: Indeed, LinkedIn, etc.) + popular searches
2. **enrich** — Full descriptions + apply URLs (3-tier: JSON-LD → CSS → LLM)
3. **filter** — Mark country-restricted jobs (`apply_status='location_filtered'`)
4. **index** — LLM extracts structured metadata once per job (`job_metadata_json`)

**Main platform** handles per-user actions:
- **score** — LLM rates fit 1–10 against user profile + resume (runs automatically)
- **tailor** — LLM generates tailored resume JSON per job (on-demand, usage-limited)
- **cover** — LLM generates cover letter per job (on-demand, usage-limited)

## Key Patterns

- **Auth**: Clerk RS256 JWTs. `get_current_user()` verifies + upserts user on every request. No passwords.
- **DB**: `jobs` table (shared, written by discovery worker). `user_jobs` table (per-user scores/tailors/covers). `users` table (Clerk-synced, stores profile/resume/searches as JSON).
- **Turso**: `_TursoConnection` in `database.py` — sqlite3-compatible HTTP wrapper. Has `__enter__`/`__exit__` so `with get_connection()` works. Auto-commits.
- **Auto-scoring**: `trigger_score_for_user(user_id)` in `core.py`. Called on profile/resume save and on jobs-page mount via `POST /api/pipeline/maybe-score`. Idempotent.
- **Rate limiting**: `RateLimiter` in `core.py` — sliding window, in-memory per user. Applied to tailor/cover/pipeline.
- **LLM client**: Auto-detects provider from env vars. Gemini tries OpenAI-compat first, falls back to native API on 403/404. Exponential backoff on rate limits.
- **SSE**: `GET /api/stream/task/{id}?token=<jwt>` — token as query param (EventSource can't send headers).
- **Validation**: 42 banned words, 20 LLM leak phrases, fabrication watchlist. Modes: strict/normal/lenient.
- **Cleanup**: `cleanup_old_jobs(days=60)` runs on startup — deletes unscored jobs older than 60 days.
- **Stripe**: `POST /api/stripe/create-checkout` → Stripe Checkout. `POST /api/stripe/webhook` flips tier to `pro`. Falls back to direct upgrade when `STRIPE_SECRET_KEY` not set.

## Tier System

- **Free**: 3 tailors/month, 1 cover letter/month. Jobs scoring ≥ 8 are blurred (`locked: true`).
- **Pro**: Unlimited tailors + cover letters. All jobs visible.

Upgrade flow: free user clicks "Upgrade" → Stripe Checkout → webhook → `tier='pro'` in DB.

## User Config (stored in `users` DB row)

- `profile_json` — Name, email, location, work auth, skills, resume facts, EEO
- `searches_json` — Queries, locations, boards, title filters, location filters
- `resume_text` — Master resume (plain text)

Also used from filesystem (legacy single-user fallback): `$APPLYPILOT_DIR/profile.json`, `searches.yaml`, `resume.txt`.

## Environment Variables

```bash
# Auth (required)
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_...
CLERK_SECRET_KEY=sk_...

# Database (required for production)
DATABASE_URL=libsql://...
DATABASE_TOKEN=...

# LLM (at least one required for scoring/tailoring)
GEMINI_API_KEY=...
OPENAI_API_KEY=...    # alternative
LLM_MODEL=...         # override model

# Stripe (optional — enables paid upgrades)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
STRIPE_SUCCESS_URL=http://yourdomain.com/jobs?upgraded=true
STRIPE_CANCEL_URL=http://yourdomain.com/pricing

# Email notifications (optional — one of the two)
RESEND_API_KEY=re_...
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASS=...
SMTP_FROM=noreply@yourdomain.com

# Misc
APPLYPILOT_DIR=/data          # defaults to ~/.applypilot
CORS_ORIGINS=https://yourdomain.com
FRONTEND_ORIGIN=https://yourdomain.com
```

## Development

```bash
# Full stack (recommended)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up

# Backend only (no Docker)
cd backend && pip install -e ".[dev]"
APPLYPILOT_DIR=./data uvicorn applypilot.web.server:app --reload --port 8000

# Frontend only (no Docker)
cd frontend && npm install && npm run dev

# API docs
open http://localhost:8000/api/docs
```

## Production

```bash
mkdir -p data
cp .env.example .env   # fill in your secrets
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

# Set up SSL (requires DOMAIN env var)
DOMAIN=yourdomain.com ./setup-ssl.sh
```

## Discovery Worker (separate repo)

`applypilot-discovery` runs independently on a homelab LXC or any server.
It shares the same `DATABASE_URL`/`DATABASE_TOKEN` as the main platform.

The main platform's `GET /api/scheduler/status` reads `discovery_runs` to show
when the worker last ran. The manual sync trigger was removed — all discovery is
handled by the worker's own schedule.

**Shared modules** (`discovery.py`, `enrichment.py`, `filter.py`, `indexer.py`, `llm.py`, `turso.py`)
are inlined copies from this repo. Run `./sync-shared-modules.sh` to push
updates from this repo → discovery worker.
