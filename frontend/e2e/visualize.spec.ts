import { test, expect } from "./fixtures/base";
import { PROCESS_MODEL_ID } from "./fixtures/seed-data";

test.describe("Visualize Page", () => {
  test("visualize page loads with model ID parameter", async ({ page }) => {
    await page.goto("/visualize/demo-1", { waitUntil: "domcontentloaded" });
    const main = page.locator("main").first();
    await expect(main).toBeVisible();
  });

  test("visualize page loads with seeded process model ID", async ({ page }) => {
    await page.goto(`/visualize/${PROCESS_MODEL_ID}`, { waitUntil: "domcontentloaded" });
    const main = page.locator("main").first();
    await expect(main).toBeVisible();
  });

  test("visualize page renders content area", async ({ page }) => {
    await page.goto(`/visualize/${PROCESS_MODEL_ID}`, { waitUntil: "domcontentloaded" });
    const main = page.locator("main").first();
    await expect(main).toBeVisible();
  });
});
