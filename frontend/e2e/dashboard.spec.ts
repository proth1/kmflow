import { test, expect } from "@playwright/test";

test.describe("Dashboard", () => {
  test("home page loads as dashboard with quick actions", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Process Intelligence Dashboard" })
    ).toBeVisible();
    await expect(page.getByText("Quick Actions")).toBeVisible();
  });

  test("dashboard shows platform status card", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Platform Status")).toBeVisible();
  });

  test("dashboard quick action cards link to sections", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Evidence Upload")).toBeVisible();
    await expect(page.getByText("Knowledge Graph")).toBeVisible();
    await expect(page.getByText("TOM Analysis")).toBeVisible();
    await expect(page.getByText("Conformance")).toBeVisible();
    await expect(page.getByText("Monitoring")).toBeVisible();
    await expect(page.getByText("Copilot")).toBeVisible();
  });

  test("engagement dashboard page loads with engagement ID", async ({
    page,
  }) => {
    await page.goto("/dashboard/00000000-0000-0000-0000-000000000001");
    await expect(page.locator("main")).toBeVisible();
  });
});
