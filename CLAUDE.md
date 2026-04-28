# ApplyPilot

Multi-user SaaS platform: a background discovery worker continuously populates a shared job database; users log in, see jobs scored against their CV, then tailor resumes and generate cover letters per job.

**Fullstack monorepo** — Next.js frontend + FastAPI backend + Docker.
**Discovery worker** lives in a separate repo (`applypilot-discovery`) and shares the same Turso DB.

> Deeper context (architecture, module map, decisions, per-area details) lives in the personal KB at `~/.claude/memory-compiler/knowledge/projects/applypilot/`. This file is the repo-portable summary — anything that ships with the code goes here; anything that changes often goes in the KB.

## Tech Stack

- **Frontend**: Next.js 16 (App Router), React 19, Tailwind CSS v4, TypeScript
- **Backend**: Python 3.11+, FastAPI, Turso (libSQL via HTTP) or SQLite (WAL mode, dev)
- **Auth**: Clerk (RS256 JWTs — no passwords stored)
- **LLM**: Gemini (default), OpenAI, or local (Ollama/llama.cpp) — auto-detected from env vars
- **Payments**: Stripe Checkout + webhook
- **Infra**: Docker + Docker Compose (dev + prod), nginx reverse proxy

## Project Layout (top-level)

```
applypilot/
├── backend/                 # FastAPI app (src/applypilot/), pyproject.toml, Dockerfile
├── frontend/                # Next.js app (app/, components/, lib/), Dockerfile
├── nginx/                   # Reverse proxy config + Dockerfile
├── docker-compose.yml       # Base
├── docker-compose.dev.yml   # Hot reload, direct ports, no nginx
├── docker-compose.prod.yml  # Optimized builds, nginx on :80/:443
├── setup-ssl.sh             # Certbot SSL helper
├── sync-shared-modules.sh   # Push shared modules → applypilot-discovery
└── .env.example
```

Full module tree and per-file responsibilities: see KB `architecture/module-map`.

## Architecture

Browser → nginx → Next.js + FastAPI → Turso (shared with `applypilot-discovery` worker, separate repo).

The discovery worker runs `discover → enrich → filter → index` on its own schedule. The main platform only runs `score` (per-user) and on-demand `tailor` / `cover`. See KB `architecture/data-flow` and `pipeline/_index` for details.

## Tier System

- **Free**: 3 tailors/month, 1 cover letter/month. Jobs scoring ≥ 8 are blurred (`locked: true`).
- **Pro**: Unlimited tailors + cover letters. All jobs visible.

Upgrade flow: free user clicks "Upgrade" → Stripe Checkout → webhook → `tier='pro'` in DB. Falls back to direct upgrade when `STRIPE_SECRET_KEY` not set.

## User Config (stored in `users` DB row)

- `profile_json` — Name, email, location, work auth, skills, resume facts, EEO
- `searches_json` — Queries, locations, boards, title filters, location filters
- `resume_text` — Master resume (plain text)

Filesystem fallback (legacy single-user): `$APPLYPILOT_DIR/profile.json`, `searches.yaml`, `resume.txt`.

## Environment Variables

```bash
# Auth (required)
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_...
CLERK_SECRET_KEY=sk_...
# CLERK_AUDIENCE=...  # optional — pin JWT `aud` claim for defense in depth
                      # (issuer is always pinned, derived from the publishable key)

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

## Discovery Worker

Lives in `applypilot-discovery` (separate repo), shares the same `DATABASE_URL`/`DATABASE_TOKEN`. Shared modules (`discovery.py`, `enrichment.py`, `filter.py`, `indexer.py`, `llm.py`, `turso.py`) are inlined copies — run `./sync-shared-modules.sh` to push updates from this repo.

## Backend dependency lockfile (INF-019)

`backend/requirements.lock` is the source of truth for production installs and is committed to the repo. The Dockerfile installs from it directly. Whenever you edit `backend/pyproject.toml`, regenerate the lockfile:

```bash
cd backend
uv pip compile pyproject.toml -o requirements.lock
# or, with pip-tools:
# pip-compile pyproject.toml -o requirements.lock
```

Commit the regenerated `requirements.lock` alongside the `pyproject.toml` change.

## Frontend E2E tests (TST-020)

Playwright tests live in `frontend/e2e/`. All `/api/*` calls are stubbed via `route.fulfill` (see `frontend/e2e/helpers/stubs.ts`) so tests run without a live backend. Run locally:

```bash
cd frontend
npm run e2e         # installs Chromium, then runs tests
npm run e2e:test    # skips browser install (assumes already installed)
```

CI runs the suite in `.github/workflows/ci.yml:frontend`. Tests that depend on Clerk-protected routes are currently `test.fixme()`'d until a `NEXT_PUBLIC_TEST_MODE` auth bypass lands in the app — the structure exists so flipping them on is a one-line change.

## Skill usage

When a task matches an active skill's trigger (listed in the disposition below), invoke it via the `Skill` tool before proceeding — don't just rely on training knowledge. Specifically:

- **Workflow skills (`superpowers`)** are proactive — invoke without being asked:
  - `brainstorming` — before any new feature, component, or behavior change
  - `writing-plans` — when a task has more than ~3 steps or touches multiple files
  - `test-driven-development` — before implementing a feature or bugfix
  - `systematic-debugging` — when a bug, test failure, or unexpected behavior shows up
  - `verification-before-completion` — before claiming work is done, fixed, or passing
  - `requesting-code-review` / `receiving-code-review` — at major milestones or before merge
  - `using-git-worktrees` — when starting work that needs isolation
  - `dispatching-parallel-agents` / `subagent-driven-development` — for 2+ independent tasks
- **Domain skills** fire on their own triggers — invoke them when:
  - Editing FastAPI routes / Pydantic models → `fastapi-expert`
  - Editing Python beyond a one-liner → `python-pro`
  - Editing Next.js pages, layouts, route handlers → `nextjs-developer`
  - Editing TS types, generics, type guards → `typescript-pro`
  - Touching auth, Stripe webhooks, multi-user data isolation → `secure-code-guardian`
  - Writing/debugging Playwright (liveness checks, future E2E) → `playwright-expert`
  - Editing Dockerfiles, compose files, nginx config → `devops-engineer`
  - Building UI components or pages with design intent → `frontend-design`

If multiple skills match, invoke the most specific one first. Skip if the task is too small (typo fix, one-line edit, read-only question).

<!-- skills-disposition: catalog-version=2026-04-27-73f386cf3fe4 updated=2026-04-27 -->
## Skills disposition

**Active in this project:**
- `fastapi-expert` (plugin-skill from `fullstack-dev-skills`) — backend framework match
- `python-pro` (plugin-skill from `fullstack-dev-skills`) — Python 3.11+ codebase
- `secure-code-guardian` (plugin-skill from `fullstack-dev-skills`) — JWT, Stripe webhook, multi-user data isolation surface
- `nextjs-developer` (plugin-skill from `fullstack-dev-skills`) — Next.js 16 App Router with route groups
- `typescript-pro` (plugin-skill from `fullstack-dev-skills`) — TS frontend with Job/Stats/Task type system
- `playwright-expert` (plugin-skill from `fullstack-dev-skills`) — Playwright now in backend container for liveness checks
- `devops-engineer` (plugin-skill from `fullstack-dev-skills`) — Docker Compose + nginx + SSL stack
- `frontend-design@claude-plugins-official` (full plugin) — distinctive, production-grade frontend design
- `superpowers@superpowers-marketplace` (full plugin) — 14 workflow skills incl. brainstorming, systematic-debugging, TDD, plan execution, code review

**Declined:**
- `prompt-engineer` — declined despite heavy LLM use; user prefers to refine prompts manually

**Deferred:** _none_
