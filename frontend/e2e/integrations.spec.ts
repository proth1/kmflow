import { test, expect } from "@playwright/test";

test.describe("Integrations Page", () => {
  test("integrations page loads with heading", async ({ page }) => {
    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: "Integrations" })
    ).toBeVisible();
  });

  test("integrations page shows tabs", async ({ page }) => {
    await page.goto("/integrations");
    await expect(
      page.getByRole("tab", { name: "Connections" })
    ).toBeVisible();
    await expect(
      page.getByRole("tab", { name: "Available Connectors" })
    ).toBeVisible();
  });

  test("integrations page has refresh button", async ({ page }) => {
    await page.goto("/integrations");
    await expect(
      page.getByRole("button", { name: "Refresh" })
    ).toBeVisible();
  });
});
