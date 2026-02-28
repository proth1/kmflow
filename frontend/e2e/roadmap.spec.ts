import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID } from "./fixtures/seed-data";

test.describe("Roadmap Page", () => {
  test("roadmap page loads with engagement ID parameter", async ({ page }) => {
    await page.goto("/roadmap/demo-1", { waitUntil: "domcontentloaded" });
    const main = page.locator("main").first();
    await expect(main).toBeVisible();
  });

  test("roadmap page loads with seeded engagement ID", async ({ page }) => {
    await page.goto(`/roadmap/${ENGAGEMENT_ID}`, { waitUntil: "domcontentloaded" });
    const main = page.locator("main").first();
    await expect(main).toBeVisible();
  });

  test("roadmap page renders content area", async ({ page }) => {
    await page.goto(`/roadmap/${ENGAGEMENT_ID}`, { waitUntil: "domcontentloaded" });
    const main = page.locator("main").first();
    await expect(main).toBeVisible();
  });
});
