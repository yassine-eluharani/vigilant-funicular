# syntax=docker/dockerfile:1.7

# ── Builder stage ─────────────────────────────────────────────────────────────
# TODO(INF-018): pin to digest via Renovate (e.g. python:3.12-slim@sha256:...).
# Manual pinning would drift on every base-image update; Renovate (or
# Dependabot's Docker support) is the correct long-term fix.
FROM python:3.12-slim AS builder

# WORKDIR matches the production stage (/app) so the editable install's
# egg-link points at /app/src — which exists in BOTH stages (final stage
# COPYs src there, dev compose bind-mounts source there for hot reload).
WORKDIR /app

# Build deps (gcc) live ONLY in the builder image so the final image stays
# slim (INF-017).
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Build everything inside an isolated virtualenv. We then copy the venv
# wholesale into the production image, so no compiler ends up there.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
RUN pip install --no-cache-dir --upgrade pip

# Copy ONLY the manifest + lockfile first so the dependency layer is cached
# across source edits (INF-004).
#
# `requirements.lock` is generated from `pyproject.toml` via:
#     uv pip compile pyproject.toml -o requirements.lock
# (or, if `pip-tools` is preferred: `pip-compile pyproject.toml -o requirements.lock`).
# Regenerate whenever `pyproject.toml` changes and commit the result — the
# lockfile is the source of truth for production installs (INF-019).
COPY pyproject.toml requirements.lock ./

# Install pinned runtime deps from the lockfile. The lockfile already pins
# every transitive dep, so pip just installs exactly what's listed.
RUN pip install --no-cache-dir --timeout 120 --retries 5 \
        -r requirements.lock

# Now copy the source and install the package itself without touching deps.
# Editable install (`-e`) so dev's bind-mount (/app/src) is picked up live.
# WORKDIR /app above ensures the egg-link points to /app/src — a path that
# also exists in the production stage (which COPYs src to /app/src).
COPY src ./src
RUN pip install --no-cache-dir --no-deps -e .

# ── Base stage ────────────────────────────────────────────────────────────────
# TODO(INF-018): pin to digest via Renovate.
FROM python:3.12-slim AS base

WORKDIR /app

# Runtime-only deps. curl is required for the HEALTHCHECK below.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Pull the prebuilt virtualenv from the builder stage. No gcc in this
# image (INF-017).
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    VIRTUAL_ENV=/opt/venv

# Bring source over so the editable install in /opt/venv resolves.
COPY src ./src
COPY pyproject.toml ./

# Install Playwright Chromium for PDF generation (skipped in dev to save
# disk). --with-deps installs apt packages, which needs root.
ARG INSTALL_PLAYWRIGHT=false
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
        playwright install chromium --with-deps \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# Create a non-root user and make /app + /data writable (INF-005).
RUN groupadd -r app && useradd -r -g app -m -d /home/app app && \
    mkdir -p /data /app && \
    chown -R app:app /app /data /home/app /opt/venv

# Hand the Playwright browser cache (installed as root above) over to the
# runtime user.
RUN if [ -d /root/.cache/ms-playwright ]; then \
        mkdir -p /home/app/.cache && \
        mv /root/.cache/ms-playwright /home/app/.cache/ms-playwright && \
        chown -R app:app /home/app/.cache; \
    fi
ENV PLAYWRIGHT_BROWSERS_PATH=/home/app/.cache/ms-playwright

# Healthcheck — uses /api/health (lightweight FastAPI handler).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

USER app

# ── Development stage ─────────────────────────────────────────────────────────
FROM base AS development
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["uvicorn", "applypilot.web.server:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Production stage ──────────────────────────────────────────────────────────
FROM base AS production
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONOPTIMIZE=1
# Single worker only: in-memory state in web/core.py (rate limiter, task
# registry, SSE) is not shared across workers. Scaling beyond 1 requires
# Redis-backed state.
CMD ["uvicorn", "applypilot.web.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
