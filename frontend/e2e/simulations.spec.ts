import { test, expect } from "@playwright/test";

test.describe("Simulations Page", () => {
  test("simulations page loads with heading", async ({ page }) => {
    await page.goto("/simulations");
    await expect(
      page.getByRole("heading", { name: "Simulations" })
    ).toBeVisible();
  });

  test("simulations page shows tabs", async ({ page }) => {
    await page.goto("/simulations");
    await expect(
      page.getByRole("tab", { name: "Scenarios" })
    ).toBeVisible();
    await expect(
      page.getByRole("tab", { name: "Results" })
    ).toBeVisible();
  });

  test("simulations page has refresh button", async ({ page }) => {
    await page.goto("/simulations");
    await expect(
      page.getByRole("button", { name: "Refresh" })
    ).toBeVisible();
  });
});
