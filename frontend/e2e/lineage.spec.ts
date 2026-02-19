import { test, expect } from "@playwright/test";

test.describe("Data Lineage Page", () => {
  test("lineage page loads with heading", async ({ page }) => {
    await page.goto("/lineage");
    await expect(
      page.getByRole("heading", { name: "Data Lineage" })
    ).toBeVisible();
  });

  test("lineage page has lookup form", async ({ page }) => {
    await page.goto("/lineage");
    await expect(page.getByPlaceholder(/550e8400/)).toBeVisible();
    await expect(page.getByPlaceholder("Evidence Item ID")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Trace Lineage" })
    ).toBeVisible();
  });

  test("lineage page shows empty state", async ({ page }) => {
    await page.goto("/lineage");
    await expect(
      page.getByText("Enter an engagement and evidence ID to trace lineage")
    ).toBeVisible();
  });
});
