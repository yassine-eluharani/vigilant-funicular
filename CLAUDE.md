# ApplyPilot

AI-powered job application automation pipeline. Discovers jobs, scores them against your profile, tailors resumes, generates cover letters, and auto-submits applications via browser automation.

## Tech Stack

- Python 3.11+, Typer CLI, SQLite (WAL mode), Playwright, FastAPI
- LLM: Gemini (default), OpenAI, or local (Ollama/llama.cpp) — auto-detected from env vars
- Auto-apply: Claude Code CLI + Chrome CDP + Playwright MCP server

## Project Layout

```
src/applypilot/
├── cli.py                  # Typer CLI — entry point (init, run, apply, status, dashboard)
├── config.py               # Paths (~/.applypilot/), tier system, env loading
├── database.py             # SQLite schema (single `jobs` table), thread-local connections
├── pipeline.py             # 6-stage orchestrator (sequential or streaming)
├── llm.py                  # Unified LLM client with Gemini dual-API fallback
├── view.py                 # Static HTML dashboard generator
├── discovery/
│   ├── jobspy.py           # Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google
│   ├── workday.py          # Workday ATS API scraper (48+ employers)
│   ├── smartextract.py     # AI-powered arbitrary website scraper
│   └── filter.py           # Pre-scoring location/country filter (regex patterns)
├── enrichment/
│   └── detail.py           # Full description + apply URL (JSON-LD → CSS → LLM cascade)
├── scoring/
│   ├── scorer.py           # Job fit scoring (1-10 scale)
│   ├── tailor.py           # Resume tailoring (structured JSON output)
│   ├── cover_letter.py     # Cover letter generation
│   ├── pdf.py              # HTML → PDF conversion via Playwright
│   └── validator.py        # Banned words, fabrication detection, LLM leak phrases
├── apply/
│   ├── launcher.py         # Job acquisition, Claude Code process spawning
│   ├── chrome.py           # Chrome lifecycle, CDP port management, profile cloning
│   ├── prompt.py           # Prompt generation for form filling
│   └── dashboard.py        # Live apply status tracking
├── wizard/
│   └── init.py             # First-time setup wizard
├── web/
│   └── server.py           # FastAPI live dashboard (stats, job list, log streaming)
└── config/
    ├── employers.yaml      # Workday employer definitions
    ├── sites.yaml          # Direct career sites + blocked sites
    └── searches.example.yaml
```

## Pipeline Stages

Run with `applypilot run [stages...]` or `applypilot run` for all.

1. **discover** — Scrape job boards + Workday portals + custom sites → store URLs in DB
2. **enrich** — Fetch full descriptions and apply URLs (3-tier cascade: JSON-LD → CSS → LLM)
3. **filter** — Pre-scoring location/country filter via regex patterns (saves LLM tokens)
4. **score** — LLM scores job-candidate fit 1-10 using profile + resume
5. **tailor** — LLM generates tailored resume JSON (max 5 retries, validated)
6. **cover** — LLM generates cover letter (max 5 retries, validated)
7. **pdf** — Convert tailored resumes/cover letters to PDF
8. **apply** — Auto-submit via `applypilot apply` (Chrome + Claude Code, parallel workers)

## User Config (`~/.applypilot/`)

- `profile.json` — Name, email, location, work auth, skills, resume facts, EEO
- `searches.yaml` — Queries, locations, boards, title filters, location filters
- `resume.txt` / `resume.pdf` — Master resume
- `.env` — `GEMINI_API_KEY`, `OPENAI_API_KEY`, `LLM_MODEL`, `LLM_URL`, `CAPSOLVER_API_KEY`

## Tier System

- **Tier 1** (Discovery): Python only → init, discover, enrich, status, dashboard
- **Tier 2** (AI Scoring): + LLM API key → score, tailor, cover, pdf, run
- **Tier 3** (Auto-Apply): + Claude Code CLI + Chrome + Node.js → apply

## Key Patterns

- **Database**: Single `jobs` table, URL as primary key, SQLite WAL mode, thread-local connections
- **LLM client**: Auto-detects provider from env vars. Gemini tries OpenAI-compat first, falls back to native API on 403/404. Exponential backoff on rate limits.
- **Validation**: 42 banned words, 20 LLM leak phrases, fabrication watchlist. Modes: strict/normal/lenient.
- **Parallelism**: `--workers N` for discovery/enrichment (ThreadPoolExecutor) and apply (separate Chrome instances). `--stream` runs stages concurrently.
- **Deduplication**: By URL (primary key). Duplicate check on store.

## Commands

```bash
applypilot init                     # Setup wizard
applypilot doctor                   # Verify setup
applypilot run [stages...]          # Run pipeline (--workers, --stream, --min-score, --validation, --dry-run)
applypilot apply                    # Auto-submit (--workers, --continuous, --headless, --limit)
applypilot status                   # Pipeline stats
applypilot dashboard                # Open HTML dashboard
```

## Development

```bash
pip install -e ".[dev]"
playwright install chromium
pytest tests/ -v
ruff check src/
```
