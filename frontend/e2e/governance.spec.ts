import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID } from "./fixtures/seed-data";

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
      page.getByPlaceholder(/550e8400/)
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

  test("entering seeded engagement ID loads governance data", async ({
    page,
  }) => {
    await page.goto("/governance");
    await page.getByPlaceholder(/550e8400/).fill(ENGAGEMENT_ID);
    await expect(page.getByRole("tab", { name: "Data Catalog" })).toBeVisible();
  });

  test("clicking SLA Health tab shows content", async ({ page }) => {
    await page.goto("/governance");
    const slaTab = page.getByRole("tab", { name: "SLA Health" });
    await slaTab.click();
    await expect(slaTab).toHaveAttribute("aria-selected", "true");
  });

  test("clicking Policies tab shows content", async ({ page }) => {
    await page.goto("/governance");
    const policiesTab = page.getByRole("tab", { name: "Policies" });
    await policiesTab.click();
    await expect(policiesTab).toHaveAttribute("aria-selected", "true");
  });
});
