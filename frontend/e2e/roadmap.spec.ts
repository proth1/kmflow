import { test, expect } from "@playwright/test";

test.describe("Roadmap Page", () => {
  test("roadmap page loads with engagement ID parameter", async ({ page }) => {
    await page.goto("/roadmap/demo-1");
    const main = page.locator("main").first();
    await expect(main).toBeVisible();
  });
});
