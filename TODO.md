# ApplyPilot SaaS — TODO

## Context

ApplyPilot is a job application **preparation** tool. It discovers jobs, scores
them for fit, tailors resumes, and generates cover letters. The user applies
themselves — we don't auto-submit anything. This is deliberate: no platform
bans, no legal liability, no trust issues, higher callback rates.

The CLI is deprioritised — all work targets the web dashboard.
Not open-source — closed-source SaaS for profit.

Positioning: "We find the right jobs, score them, and prepare everything —
you just review and click apply."

Pricing reference: Teal ($29/mo), Huntr ($40/mo), Jobsolv ($49/mo).

---

## Phase 0 — Web App Completion (current state → usable product)

These items make the web app fully functional for a single user before
tackling SaaS infrastructure.

- [ ] **Dashboard overview tab** — landing page showing pipeline funnel
      (already built), score distribution chart, recent activity feed,
      quick-action buttons ("Run discover", "Tailor all 7+")
- [ ] **Job detail view** — click a job card to see full description,
      tailored resume side-by-side, cover letter preview. Currently you
      can only expand/collapse or open external links
- [ ] **Ready to Apply tab** — for each tailored job, show:
      - Download buttons: tailored CV (PDF), cover letter (PDF)
      - One-click copy for cover letter text
      - Direct link to the job's application page
      - Job description summary + why it scored high
      - "Mark as Applied" button to track progress
      - "Skip" button to remove from the ready queue
      This is the core UX — make it dead simple
- [ ] **Resume preview/edit** — view the tailored resume in the dashboard,
      allow manual edits before PDF generation. Currently text-only in API
- [ ] **Undo dismiss** — dismissed jobs can't be recovered without SQL.
      Add a "restore" button in the dismissed jobs view
- [ ] **Job deduplication** — same role at same company posted on Indeed +
      LinkedIn + Glassdoor appears 3x. Deduplicate by (company, title,
      location)
- [ ] **Scheduled discovery** — "run discover every 6 hours" without
      leaving a terminal open. Cron-like scheduler in the web UI
- [ ] **Notifications** — email or browser notification when new
      high-scoring jobs are found or tailoring completes
- [ ] **Export** — download job list as CSV, tailored resumes as ZIP
- [ ] **Application tracker** — after user marks "Applied", track status:
      applied → interview → offer → rejected. Simple kanban or list view

---

## Phase 1 — Auth + Multi-Tenancy (SaaS foundation)

- [ ] **Authentication** — add login/signup. Options: Supabase Auth
      (fastest, includes row-level security), Auth0, or Firebase Auth.
      Need:
      - Login/register pages in the React SPA
      - JWT middleware on all /api/* routes
      - Protected routes in frontend
- [ ] **User model** — users table: id, email, name, created_at, plan,
      stripe_customer_id
- [ ] **Multi-tenant database** — add `user_id` column to jobs table and
      every query. All data must be scoped to the authenticated user
- [ ] **Migrate SQLite → PostgreSQL** — SQLite can't handle concurrent
      users. Use SQLAlchemy or raw asyncpg. Keep migration path for
      existing single-user databases
- [ ] **Per-user config storage** — profile.json, searches.yaml, resume
      currently live in ~/.applypilot/. Move to database (JSON columns or
      separate tables). Each user gets their own config
- [ ] **Per-user API key vault** — users bring their own Gemini/OpenAI
      keys. Encrypt at rest (Fernet or AWS KMS). Never log or expose in
      API responses. Or: provide a shared LLM backend and meter usage
- [ ] **File storage** — tailored resumes, cover letters, PDFs currently
      on local disk. Move to S3/R2/MinIO with per-user prefixes
- [ ] **Rate limiting** — per-user request limits (token bucket on Redis).
      Free tier: 50 jobs/day discovery, 10 tailors/day

---

## Phase 2 — Production Infrastructure

- [ ] **Background job queue** — replace in-memory `_tasks` dict and
      daemon threads with Celery + Redis (or Dramatiq, or ARQ for async).
      Pipeline stages become celery tasks. Benefits: survives restarts,
      distributed workers, retry policies, dead letter queue
- [ ] **Separate frontend build** — extract the embedded React SPA from
      server.py into a proper Vite/Next.js project. Currently it's 1500+
      lines of JSX in a Python string. Benefits: HMR, TypeScript,
      component testing, CDN deployment
- [ ] **HTTPS + reverse proxy** — remove localhost-only binding. Deploy
      behind nginx/Caddy with TLS termination. Or use a PaaS (Railway,
      Render, Fly.io)
- [ ] **Health checks** — add /health and /ready endpoints for load
      balancer probes
- [ ] **Logging + monitoring** — structured JSON logs, ship to
      Datadog/Grafana/ELK. Add Sentry for error tracking. Track: API
      latency, LLM token usage per user, pipeline stage durations
- [ ] **Audit trail** — log all mutations: who changed what, when.
      Required for compliance (GDPR, SOC 2)
- [ ] **CORS lockdown** — replace allow_origins=["*"] with actual
      frontend domain whitelist
- [ ] **Graceful shutdown** — drain in-flight requests, checkpoint
      running pipeline tasks to resume after restart

---

## Phase 3 — Billing + Monetization

- [ ] **Stripe integration** — subscription billing with Stripe Checkout.
      Webhook handler for payment events (subscription.created,
      invoice.paid, subscription.cancelled)
- [ ] **Plan tiers** — suggested starting point:
      - Free: 50 discovered jobs/day, 5 tailored resumes/mo
      - Pro ($29/mo): unlimited discover, 100 tailors/mo
      - Team ($79/mo): everything + shared job board + priority support
- [ ] **Usage metering** — track per-user: jobs discovered, LLM tokens
      consumed, resumes tailored, storage used.
      Display usage dashboard in settings
- [ ] **Overage handling** — soft limits with email warnings at 80%/100%.
      Hard block or per-unit billing for overages
- [ ] **Trial period** — 14-day free trial of Pro features, no credit
      card required. Convert to free tier after expiry
- [ ] **BYOK discount** — users who bring their own LLM API key get a
      discount (saves you LLM API costs)

---

## Phase 4 — Growth + Differentiation

- [ ] **Application analytics** — track which tailored resumes get
      callbacks. Feed this back into scoring/tailoring prompts. "Jobs
      where your tailored resume got a response had these patterns..."
- [ ] **Interview prep** — after marking "Applied", surface likely
      interview questions based on the job description + your resume.
      Upsell opportunity
- [ ] **Team/agency mode** — career coaches or staffing agencies manage
      multiple candidates. Shared employer configs, bulk operations
- [ ] **API access** — let power users and agencies integrate via REST
      API with API keys. Per-request billing
- [ ] **Browser extension** — "Save this job to ApplyPilot" from any job
      board page. One-click import into your pipeline
- [ ] **Mobile-friendly dashboard** — current Tailwind layout is
      responsive but not optimised for mobile review flows
- [ ] **Webhook integrations** — push notifications to Slack, Discord,
      email when new matches found or tailoring completes

---

## Phase 5 — Compliance + Legal

- [ ] **GDPR compliance** — data deletion endpoint (right to erasure),
      data export (right to portability), consent management, DPA for
      EU customers
- [ ] **EU AI Act** — employment AI is "high risk". Need: transparency
      about AI-generated content, human oversight checkpoints (the
      user-applies-themselves model already satisfies this)
- [ ] **Scam job detection** — flag suspicious postings (no company
      name, asks for payment, P.O. box address, gmail contact)
- [ ] **Terms of Service** — standard SaaS terms. No auto-apply
      liability since the user submits themselves
- [ ] **Resume authenticity disclaimer** — make clear that tailored
      resumes must reflect real experience. The validation system
      (fabrication watchlist, banned words) is a selling point here

---

## Not Doing (deliberate)

- Auto-apply / form submission — user applies themselves
- CLI improvements — web is the focus
- Mobile native app — responsive web is sufficient for now
- Volume play — not competing on "500 apps/day". Quality positioning
- Build own LLM — use existing providers, focus on prompts and validation
- Open-source — closed-source SaaS for profit
