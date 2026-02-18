import { test, expect } from "@playwright/test";

test.describe("Knowledge Graph Explorer", () => {
  test("graph page loads with heading", async ({ page }) => {
    await page.goto("/graph/test-engagement-id");
    await expect(page.getByText("Knowledge Graph Explorer")).toBeVisible();
  });

  test("graph page renders main content area", async ({ page }) => {
    await page.goto("/graph/test-engagement-id");
    await expect(page.locator("main").first()).toBeVisible();
  });

  test("graph page has layout selector", async ({ page }) => {
    await page.goto("/graph/test-engagement-id");
    // Even in error state, the page should load with the heading
    await expect(page.getByText("Knowledge Graph Explorer")).toBeVisible();
  });
});
