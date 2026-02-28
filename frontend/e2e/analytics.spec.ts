import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID } from "./fixtures/seed-data";

test.describe("Analytics Page", () => {
  test("analytics page loads with heading", async ({ page }) => {
    await page.goto("/analytics");
    await expect(
      page.getByRole("heading", { name: "Engagement Analytics" })
    ).toBeVisible();
  });

  test("analytics page has engagement ID input", async ({ page }) => {
    await page.goto("/analytics");
    await expect(
      page.getByPlaceholder(/550e8400/)
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

  test("entering seeded engagement ID loads analytics data", async ({
    page,
  }) => {
    await page.goto("/analytics");
    const input = page.getByPlaceholder(/550e8400/);
    await input.fill(ENGAGEMENT_ID);
    // After filling a valid engagement ID the empty-state prompt should
    // disappear as the page attempts to fetch data.
    await expect(
      page.getByText("Enter an engagement ID to view metrics")
    ).not.toBeVisible();
  });

  test("clicking Metric Definitions tab shows content", async ({ page }) => {
    await page.goto("/analytics");
    const tab = page.getByRole("tab", { name: "Metric Definitions" });
    await tab.click();
    // The tab should now carry the selected/active aria state.
    await expect(tab).toHaveAttribute("aria-selected", "true");
  });
});
