/**
 * Shared route stubs for E2E tests.
 *
 * Tests should never hit a real backend, real Clerk, or real Stripe. Every
 * `/api/*` call is intercepted with `page.route(...)` here.
 */
import type { Page, Route } from "@playwright/test";

export const FAKE_USER = {
  user: {
    id: "user_test_123",
    email: "test@applypilot.dev",
    full_name: "Test User",
    tier: "pro" as const,
    usage: { tailors_used: 0, covers_used: 0 },
    limits: { tailors: -1, covers: -1 },
  },
};

export const FAKE_JOB = {
  url: "https://example.com/jobs/test-engineer",
  url_encoded: "aHR0cHM6Ly9leGFtcGxlLmNvbS9qb2JzL3Rlc3QtZW5naW5lZXI",
  title: "Senior Test Engineer",
  company: "ApplyPilot Inc.",
  location: "Remote",
  site: "indeed",
  fit_score: 9,
  score_reasoning: "Strong skill match with the resume — Python, FastAPI, testing.",
  apply_status: null as string | null,
  application_url: "https://example.com/jobs/test-engineer/apply",
  has_pdf: false,
  has_cover_pdf: false,
  resume_text: null as string | null,
  cover_letter_text: null as string | null,
  favorited: false,
  locked: false,
};

export const FAKE_STATS = {
  total: 1,
  scored: 1,
  applied: 0,
  dismissed: 0,
  by_score: { "9": 1 },
  by_status: {},
};

/**
 * Install a default set of API stubs on a Page. Individual tests can layer
 * additional `page.route(...)` calls on top to override specific endpoints
 * (e.g. forcing a 429 on /tailor).
 */
export async function installApiStubs(page: Page): Promise<void> {
  // Auth — return a logged-in pro user
  await page.route("**/api/auth/me", (route: Route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FAKE_USER) }),
  );

  // Stats
  await page.route("**/api/stats", (route: Route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(FAKE_STATS) }),
  );

  // Jobs list
  await page.route("**/api/jobs?**", (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ jobs: [FAKE_JOB], total: 1 }),
    }),
  );
  await page.route("**/api/jobs", (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ jobs: [FAKE_JOB], total: 1 }),
    }),
  );

  // Maybe-score (auto-trigger on /jobs mount)
  await page.route("**/api/pipeline/maybe-score", (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ started: false, reason: "test-mode" }),
    }),
  );

  // Scheduler status
  await page.route("**/api/scheduler/status", (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ last_sync: null, jobs_found: 0 }),
    }),
  );
}

/**
 * Stub the SSE task stream to immediately emit a `status: done` event.
 * Used by tailor / cover tests to short-circuit the progress wait.
 */
export async function stubTaskStreamDone(page: Page): Promise<void> {
  await page.route("**/api/stream/task/**", (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      headers: { "cache-control": "no-cache" },
      // Emit a single named event then close. EventSource will fire the
      // "status" listener with data="done" and the JS path resolves.
      body: 'event: status\ndata: done\n\n',
    }),
  );

  // Polling fallback in useTaskProgress hits /api/tasks/{id} — return done too
  await page.route("**/api/tasks/**", (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "done", logs: [] }),
    }),
  );
}
