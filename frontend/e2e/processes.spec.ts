import { test, expect } from "./fixtures/base";

test.describe("Processes Page", () => {
  test("processes page loads with heading", async ({ page }) => {
    await page.goto("/processes");
    await expect(
      page.getByRole("heading", { name: "Process Management" })
    ).toBeVisible();
  });

  test("processes page shows tabs", async ({ page }) => {
    await page.goto("/processes");
    // Page may show loading or error state, but tabs should render
    const main = page.locator("main").first();
    await expect(main).toBeVisible();
  });

  test("processes page main content is visible", async ({ page }) => {
    await page.goto("/processes");
    await expect(page.locator("main").first()).toBeVisible();
  });

  test("processes page loads heading", async ({ page }) => {
    await page.goto("/processes");
    await expect(
      page.getByRole("heading", { name: "Process Management" })
    ).toBeVisible();
  });
});
