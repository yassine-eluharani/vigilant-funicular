# syntax=docker/dockerfile:1.7

# TODO(INF-018): pin to digest via Renovate (e.g. node:20-alpine@sha256:...).
# Manual pinning would drift on every base-image update; let Renovate handle it.
FROM node:20-alpine AS base

WORKDIR /app

# Healthcheck tooling — wget ships with alpine, no extra install needed.

# ── Dependencies stage ────────────────────────────────────────────────────────
FROM base AS deps
# INF-020: enforce that package-lock.json is present. Drop the `*` glob so
# COPY fails outright if the lockfile is missing, and double-check after.
COPY package.json package-lock.json ./
RUN test -f package-lock.json || (echo "ERROR: package-lock.json missing — run 'npm install' locally and commit it." >&2 && exit 1)
RUN npm ci

# ── Development stage ─────────────────────────────────────────────────────────
FROM base AS development
COPY --from=deps /app/node_modules ./node_modules
COPY . .
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget --quiet --spider http://localhost:3000/ || exit 1
CMD ["npm", "run", "dev"]

# ── Builder stage ─────────────────────────────────────────────────────────────
FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
# NEXT_PUBLIC_* vars are baked into the JS bundle at build time
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
# BACKEND_URL is used by next.config.ts rewrites, which are also evaluated at build time
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL
RUN npm run build

# ── Production stage ──────────────────────────────────────────────────────────
FROM base AS production
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget --quiet --spider http://localhost:3000/ || exit 1
CMD ["node", "server.js"]
