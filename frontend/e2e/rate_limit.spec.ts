import { test, expect } from "@playwright/test";
import { installApiStubs, FAKE_JOB } from "./helpers/stubs";

/**
 * Rate-limit surfacing.
 *
 * Like `tailor.spec.ts`, this hits a Clerk-gated route. Marked `fixme`
 * until the app gains a test-mode auth bypass.
 *
 * Behavior under test:
 *   - POST /api/jobs/.../tailor returns 429 with a "Rate limit exceeded"
 *     body (matching backend/src/applypilot/web/core.py:RateLimiter).
 *   - The JobCard's catch-block surfaces the message via `useToast()`.
 *
 * The current JobCard implementation swallows tailor errors silently
 * (`catch {}` — see frontend/components/jobs/JobCard.tsx). When that's
 * fixed to call `toast(err.message, false)`, this test will start passing
 * and we drop the `fixme`.
 */
test.describe("Rate limit handling", () => {
  test.beforeEach(async ({ page }) => {
    await installApiStubs(page);

    // Tailor returns 429 with backend-style error body.
    await page.route("**/api/jobs/*/tailor**", (route) =>
      route.fulfill({
        status: 429,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Rate limit exceeded. Try again in 60s." }),
      }),
    );
  });

  test.fixme("surfaces a 429 from the tailor endpoint as an error toast", async ({ page }) => {
    await page.goto("/jobs");

    const jobCard = page.locator("text=" + FAKE_JOB.title).first();
    await expect(jobCard).toBeVisible();

    await page.getByRole("button", { name: /^Tailor$/ }).first().click();

    // Toast is rendered by ToastProvider — match the rate-limit message.
    await expect(page.locator("text=/Rate limit/i")).toBeVisible({ timeout: 5_000 });
  });
});
