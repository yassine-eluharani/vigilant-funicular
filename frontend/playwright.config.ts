import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for ApplyPilot frontend E2E tests (TST-020).
 *
 * Goals:
 *   - All `/api/*` calls are stubbed via `route.fulfill` so tests run without
 *     a live backend or Stripe / Clerk credentials.
 *   - The dev server is auto-started by Playwright on port 3000.
 *   - `NEXT_PUBLIC_TEST_MODE=1` is set so the frontend can opt-out of Clerk
 *     middleware in tests if/when that wiring lands. Until then, tests that
 *     hit auth-protected routes use route stubs to satisfy auth-state checks.
 *
 * Run: `npm run e2e`  (installs Chromium first time, then runs)
 *      `npm run e2e:test`  (skip the install step, useful in CI cache hits)
 */
export default defineConfig({
  testDir: "./e2e",
  // Avoid `test.only` slipping into CI.
  forbidOnly: !!process.env.CI,
  // No retries locally; CI gets one extra shot to absorb flakes.
  retries: process.env.CI ? 1 : 0,
  // Single worker keeps the dev server warm and avoids port contention.
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",

  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
    // Tests stub the network — block any unexpected outbound traffic by
    // failing fast on uncaught calls (configured per-test via route.abort).
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      // Signal to app code (where it checks) that we're in test mode. Today
      // the codebase doesn't read this — when it does, tests can rely on
      // server-side bypass instead of route stubbing.
      NEXT_PUBLIC_TEST_MODE: "1",
      // Clerk needs *some* publishable key at build/dev time. The dummy key
      // is base64("test-mode.clerk.accounts.dev$") and is not a real
      // account; Clerk client-side calls are stubbed in tests.
      NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY:
        process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ??
        "pk_test_dGVzdC1tb2RlLmNsZXJrLmFjY291bnRzLmRldiQ",
    },
  },
});
