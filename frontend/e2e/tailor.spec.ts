import { test, expect } from "@playwright/test";
import { installApiStubs, stubTaskStreamDone, FAKE_JOB } from "./helpers/stubs";

/**
 * Tailor flow happy path — fully stubbed.
 *
 * NOTE: this test exercises a route (`/jobs`) that is gated by the Clerk
 * middleware. In the current codebase there is no test-mode bypass, so the
 * test will be redirected to /login. We mark it `fixme` until the app
 * grows a `NEXT_PUBLIC_TEST_MODE` short-circuit (or @clerk/testing is
 * wired up). The structure is in place so `playwright test --list` shows
 * it and a future engineer can flip the flag.
 *
 * What it would assert when enabled:
 *   - GET /api/jobs returns the stub job (one card visible).
 *   - Clicking "Tailor" issues POST /api/jobs/.../tailor → returns task_id.
 *   - SSE stream emits status=done → the JobCard exits its loading state.
 *   - The list refreshes (onRefresh) without errors.
 */
test.describe("Tailor flow", () => {
  test.beforeEach(async ({ page }) => {
    await installApiStubs(page);
    await stubTaskStreamDone(page);

    // Tailor endpoint — return a synthetic task_id.
    await page.route("**/api/jobs/*/tailor**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ task_id: "task_test_tailor_42" }),
      }),
    );
  });

  test.fixme("clicking Tailor on a job triggers a task and clears the spinner", async ({ page }) => {
    await page.goto("/jobs");

    // Wait for the stubbed job to render
    const jobCard = page.locator("text=" + FAKE_JOB.title).first();
    await expect(jobCard).toBeVisible();

    // Click Tailor button on that card
    const tailorBtn = page.getByRole("button", { name: /^Tailor$/ }).first();
    await tailorBtn.click();

    // After SSE done event, the spinner should disappear (button clickable again)
    await expect(tailorBtn).toBeEnabled({ timeout: 5_000 });
  });
});
