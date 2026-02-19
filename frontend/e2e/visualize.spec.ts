import { test, expect } from "@playwright/test";

test.describe("Visualize Page", () => {
  test("visualize page loads with model ID parameter", async ({ page }) => {
    await page.goto("/visualize/demo-1");
    const main = page.locator("main").first();
    await expect(main).toBeVisible();
  });
});
