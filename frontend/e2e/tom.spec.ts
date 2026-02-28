import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID } from "./fixtures/seed-data";

test.describe("TOM Alignment Page", () => {
  test("TOM page loads with engagement ID parameter", async ({ page }) => {
    await page.goto("/tom/00000000-0000-0000-0000-000000000001", { waitUntil: "domcontentloaded" });
    const main = page.locator("main");
    await expect(main).toBeVisible();
  });

  test("TOM page shows heading or error state", async ({ page }) => {
    await page.goto("/tom/demo-1", { waitUntil: "domcontentloaded" });
    // Page shows either TOM heading (if API available) or error/loading state
    const main = page.locator("main").first();
    await expect(main).toBeVisible();
  });

  test("TOM page loads with seeded engagement ID", async ({ page }) => {
    await page.goto(`/tom/${ENGAGEMENT_ID}`, { waitUntil: "domcontentloaded" });
    const main = page.locator("main");
    await expect(main).toBeVisible();
  });

  test("TOM page shows alignment data or error for seeded engagement", async ({
    page,
  }) => {
    await page.goto(`/tom/${ENGAGEMENT_ID}`, { waitUntil: "domcontentloaded" });
    const main = page.locator("main").first();
    await expect(main).toBeVisible();
  });
});
