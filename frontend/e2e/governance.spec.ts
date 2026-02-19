import { test, expect } from "@playwright/test";

test.describe("Governance Page", () => {
  test("governance page loads with heading", async ({ page }) => {
    await page.goto("/governance");
    await expect(
      page.getByRole("heading", { name: "Data Governance" })
    ).toBeVisible();
  });

  test("governance page has engagement ID input", async ({ page }) => {
    await page.goto("/governance");
    await expect(
      page.getByPlaceholder("Enter engagement UUID")
    ).toBeVisible();
  });

  test("governance page shows tabs", async ({ page }) => {
    await page.goto("/governance");
    await expect(page.getByRole("tab", { name: "Data Catalog" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "SLA Health" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Policies" })).toBeVisible();
  });

  test("governance catalog tab shows empty state", async ({ page }) => {
    await page.goto("/governance");
    await expect(
      page.getByText("Enter an engagement ID to view catalog")
    ).toBeVisible();
  });
});
