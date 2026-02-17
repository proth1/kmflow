import { test, expect } from "@playwright/test";

test.describe("Monitoring Page", () => {
  test("monitoring page loads with heading", async ({ page }) => {
    await page.goto("/monitoring");
    await expect(page.getByText("Monitoring")).toBeVisible();
  });

  test("monitoring page has main content area", async ({ page }) => {
    await page.goto("/monitoring");
    const main = page.locator("main");
    await expect(main).toBeVisible();
  });
});
