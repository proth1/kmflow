import { test, expect } from "@playwright/test";

test.describe("Monitoring Page", () => {
  test("monitoring page loads with heading", async ({ page }) => {
    await page.goto("/monitoring");
    await expect(
      page.getByRole("heading", { name: "Monitoring Dashboard" })
    ).toBeVisible();
  });

  test("monitoring page has main content area", async ({ page }) => {
    await page.goto("/monitoring");
    await expect(page.locator("main").first()).toBeVisible();
  });
});
