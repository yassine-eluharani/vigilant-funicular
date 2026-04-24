FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src ./src
RUN pip install --no-cache-dir --timeout 120 --retries 5 -e ".[prod]"

# Install Playwright Chromium for PDF generation
RUN playwright install chromium --with-deps

# ── Development stage ─────────────────────────────────────────────────────────
FROM base AS development
ENV PYTHONDONTWRITEBYTECODE=1

# ── Production stage ──────────────────────────────────────────────────────────
FROM base AS production
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONOPTIMIZE=1
