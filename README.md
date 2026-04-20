# ApplyPilot

AI-powered job discovery and application toolkit. Discovers jobs across multiple boards, scores them against your profile, tailors resumes, and generates cover letters.

## Stack

- **Frontend** — Next.js (App Router), Tailwind CSS, TypeScript
- **Backend** — FastAPI, SQLite / Turso (libSQL)
- **LLM** — Gemini (default), OpenAI, or local (Ollama / llama.cpp)
- **Infra** — Docker Compose, nginx

## Quick Start

```bash
cp .env.example .env
# Fill in GEMINI_API_KEY and JWT_SECRET in .env

docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
# Open http://localhost
```

For local development with hot reload:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

## Pipeline

| Stage | What it does |
|-------|-------------|
| Discover | Scrapes job boards (Indeed, LinkedIn, etc.) + Workday portals |
| Enrich | Fetches full descriptions and apply URLs |
| Filter | Location/keyword pre-filter (saves LLM tokens) |
| Score | LLM scores job-candidate fit 1–10 |
| Tailor | LLM rewrites resume per job, never fabricates |
| Cover | LLM writes a targeted cover letter per job |
| PDF | Converts tailored resumes and cover letters to PDF |

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `GEMINI_API_KEY` | Yes (or OpenAI) | LLM provider key |
| `JWT_SECRET` | Yes | Token signing secret (`openssl rand -hex 32`) |
| `DATABASE_URL` | No | Turso URL (`libsql://...`) — defaults to local SQLite |
| `DATABASE_TOKEN` | If Turso | Auth token for Turso |

## Discovery Service

A standalone worker that pre-populates the job database on a schedule. Designed to run on a homelab server pointing at the same Turso database as the main app.

```bash
cd discovery-service
cp .env.example .env   # fill in DATABASE_URL + DATABASE_TOKEN
python main.py
```

See [`discovery-service/setup-lxc.sh`](discovery-service/setup-lxc.sh) for automated LXC setup with systemd + GitHub Actions CI/CD.

## Data

Mount a volume at `/data` for persistence. Put your `profile.json`, `searches.yaml`, and `resume.pdf` there. See [`profile.example.json`](profile.example.json) for the expected shape.

## License

[AGPL-3.0](LICENSE)
