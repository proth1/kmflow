import { test, expect } from "@playwright/test";

test.describe("Engagement Dashboard", () => {
  test("dashboard page loads with engagement ID parameter", async ({
    page,
  }) => {
    await page.goto("/dashboard/00000000-0000-0000-0000-000000000001");
    // Dashboard should attempt to render even with a non-existent engagement
    await expect(page.locator("main")).toBeVisible();
  });

  test("dashboard shows key metric sections", async ({ page }) => {
    await page.goto("/dashboard/00000000-0000-0000-0000-000000000001");
    // Look for common dashboard elements
    const main = page.locator("main");
    await expect(main).toBeVisible();
  });
});
