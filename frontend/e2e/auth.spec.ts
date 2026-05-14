import { test, expect } from "@playwright/test";
import { installApiStubs } from "./helpers/stubs";

/**
 * Smoke test — verifies the public login page renders and protected routes
 * push unauthenticated users to it.
 *
 * The marketing landing was removed in the personal-tool revamp; `/` now
 * resolves through Clerk middleware to /login the same way any other
 * dashboard route does.
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

  test("protected route redirects unauthenticated users to /login", async ({ page }) => {
    // Clerk middleware (proxy.ts) should kick in. We don't assert the exact
    // redirect destination because Clerk may inject `?next=` and `__clerk_*`
    // params; just check we end up on /login.
    await page.goto("/apply");
    await expect(page).toHaveURL(/\/login/);
  });
});
