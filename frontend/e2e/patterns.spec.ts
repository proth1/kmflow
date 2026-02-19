import { test, expect } from "@playwright/test";

test.describe("Patterns Page", () => {
  test("patterns page loads with heading", async ({ page }) => {
    await page.goto("/patterns");
    await expect(
      page.getByRole("heading", { name: "Process Patterns" })
    ).toBeVisible();
  });

  test("patterns page has search input", async ({ page }) => {
    await page.goto("/patterns");
    await expect(
      page.getByPlaceholder("Search patterns...")
    ).toBeVisible();
  });

  test("patterns page has refresh button", async ({ page }) => {
    await page.goto("/patterns");
    await expect(
      page.getByRole("button", { name: "Refresh" })
    ).toBeVisible();
  });

  test("patterns page shows All category filter", async ({ page }) => {
    await page.goto("/patterns");
    await expect(
      page.getByRole("button", { name: "All" })
    ).toBeVisible();
  });
});
