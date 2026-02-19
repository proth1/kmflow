import { test, expect } from "@playwright/test";

test.describe("Analytics Page", () => {
  test("analytics page loads with heading", async ({ page }) => {
    await page.goto("/analytics");
    await expect(
      page.getByRole("heading", { name: "Analytics & Metrics" })
    ).toBeVisible();
  });

  test("analytics page has engagement ID input", async ({ page }) => {
    await page.goto("/analytics");
    await expect(
      page.getByPlaceholder("Enter engagement UUID")
    ).toBeVisible();
  });

  test("analytics page shows tabs", async ({ page }) => {
    await page.goto("/analytics");
    await expect(
      page.getByRole("tab", { name: "Performance Summary" })
    ).toBeVisible();
    await expect(
      page.getByRole("tab", { name: "Metric Definitions" })
    ).toBeVisible();
  });

  test("analytics performance tab shows empty state without engagement", async ({
    page,
  }) => {
    await page.goto("/analytics");
    await expect(
      page.getByText("Enter an engagement ID to view metrics")
    ).toBeVisible();
  });
});
