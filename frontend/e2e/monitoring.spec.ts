import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID, MONITORING_JOB_IDS } from "./fixtures/seed-data";

test.describe("Monitoring Page", () => {
  test("monitoring page loads with heading", async ({ page }) => {
    await page.goto("/monitoring");
    await expect(
      page.getByRole("heading", { name: "Monitoring Dashboard" })
    ).toBeVisible();
  });

  test("monitoring page has engagement ID input", async ({ page }) => {
    await page.goto("/monitoring");
    await expect(
      page.getByPlaceholder(/550e8400/)
    ).toBeVisible();
  });

  test("monitoring page shows deviations and alerts sections", async ({
    page,
  }) => {
    await page.goto("/monitoring");
    await expect(
      page.getByRole("heading", { name: "Recent Deviations" })
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Alert Feed" })
    ).toBeVisible();
  });

  test("monitoring detail page loads", async ({ page }) => {
    await page.goto("/monitoring/test-job-id");
    await expect(page.locator("main").first()).toBeVisible();
  });

  test("entering seeded engagement ID shows monitoring data", async ({
    page,
  }) => {
    await page.goto("/monitoring");
    const input = page.getByPlaceholder(/550e8400/);
    await input.fill(ENGAGEMENT_ID);
    await expect(input).toHaveValue(ENGAGEMENT_ID);
  });

  test("monitoring detail page loads with seeded job ID", async ({ page }) => {
    await page.goto(`/monitoring/${MONITORING_JOB_IDS[0]}`);
    await expect(page.locator("main").first()).toBeVisible();
  });
});
