import { test, expect } from "@playwright/test";
import { installApiStubs } from "./helpers/stubs";

/**
 * Smoke test — verifies the public login page renders and the marketing
 * shell is reachable without auth.
 *
 * Why /login, not /jobs: the dashboard is gated by Clerk middleware
 * (frontend/proxy.ts). Stubbing Clerk's full session machinery from the
 * test layer is brittle — when the codebase grows a real test-mode bypass
 * we'll add a /jobs-shell test here. For now this asserts the public
 * surface area of the auth flow is healthy.
 */
test.describe("Auth & shell", () => {
  test.beforeEach(async ({ page }) => {
    await installApiStubs(page);
  });

  test("login page renders the Clerk sign-in form", async ({ page }) => {
    await page.goto("/login");
    // The page hydrates Clerk's <SignIn /> — the brand block ("ApplyPilot")
    // and the © footer are static and safe to assert against.
    await expect(page.getByRole("link", { name: /ApplyPilot/i }).first()).toBeVisible();
    await expect(page.locator("text=© 2026 ApplyPilot")).toBeVisible();
  });

  test("marketing landing page is reachable without auth", async ({ page }) => {
    await page.goto("/");
    // Landing page is public; the register CTA is the primary action.
    await expect(page.getByRole("link", { name: /register|get started|sign up/i }).first()).toBeVisible();
  });

  test("protected route redirects unauthenticated users to /login", async ({ page }) => {
    // Clerk middleware (proxy.ts) should kick in. We don't assert the exact
    // redirect destination because Clerk may inject `?next=` and `__clerk_*`
    // params; just check we end up on /login.
    await page.goto("/jobs");
    await expect(page).toHaveURL(/\/login/);
  });
});
