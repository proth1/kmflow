import { test, expect } from "@playwright/test";

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
      page.getByPlaceholder("Enter engagement UUID")
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
});
