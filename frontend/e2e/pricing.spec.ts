import { test, expect } from "@playwright/test";
import { installApiStubs } from "./helpers/stubs";

/**
 * The marketing /pricing page is public; its "Upgrade to Pro" CTA links to
 * /register (the in-app upgrade-to-Stripe flow lives on /profile and is
 * covered separately by manual / integration tests since it requires an
 * authenticated session).
 *
 * If/when the pricing page learns to call `createCheckoutSession()` directly
 * (e.g. via a "Buy now" button), the Stripe stub below is wired and ready.
 */
test.describe("Pricing page", () => {
  test.beforeEach(async ({ page }) => {
    await installApiStubs(page);

    // Stub Stripe checkout — fulfil with a redirect URL the app can follow.
    await page.route("**/api/stripe/create-checkout", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ checkout_url: "/register?upgrade=pro" }),
      }),
    );
  });

  test("renders both tiers and the upgrade CTA", async ({ page }) => {
    await page.goto("/pricing");
    await expect(page.getByRole("heading", { name: /Simple, honest pricing/i })).toBeVisible();
    await expect(page.getByText("Free", { exact: false }).first()).toBeVisible();
    await expect(page.getByText("Upgrade to Pro", { exact: false }).first()).toBeVisible();
  });

  test("clicking 'Upgrade to Pro' navigates away from /pricing", async ({ page }) => {
    await page.goto("/pricing");
    const cta = page.getByRole("link", { name: /Upgrade to Pro/i }).first();
    await expect(cta).toBeVisible();

    await Promise.all([
      page.waitForURL((url) => !url.pathname.startsWith("/pricing")),
      cta.click(),
    ]);

    // The current implementation routes pricing CTAs to /register; if the
    // flow ever changes to call Stripe directly, the route stub above will
    // already accept it — just update this assertion accordingly.
    await expect(page).toHaveURL(/\/register|\/login|\/checkout/);
  });
});
