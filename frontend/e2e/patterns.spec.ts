import { test, expect } from "./fixtures/base";

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

  test("patterns search accepts input", async ({ page }) => {
    await page.goto("/patterns");
    const searchInput = page.getByPlaceholder("Search patterns...");
    await searchInput.fill("approval");
    await expect(searchInput).toHaveValue("approval");
  });

  test("clicking All category button stays on patterns", async ({ page }) => {
    await page.goto("/patterns");
    await page.getByRole("button", { name: "All" }).click();
    await expect(page).toHaveURL(/\/patterns/);
    await expect(
      page.getByRole("heading", { name: "Process Patterns" })
    ).toBeVisible();
  });
});
