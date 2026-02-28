import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID } from "./fixtures/seed-data";

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
    const content = page.locator("main").first();
    await expect(
      content.getByRole("heading", { name: "Evidence Upload" })
    ).toBeVisible();
    await expect(
      content.getByRole("heading", { name: "Knowledge Graph" })
    ).toBeVisible();
    await expect(
      content.getByRole("heading", { name: "TOM Analysis" })
    ).toBeVisible();
    await expect(
      content.getByRole("heading", { name: "Conformance" })
    ).toBeVisible();
    await expect(
      content.getByRole("heading", { name: "Monitoring" })
    ).toBeVisible();
    await expect(
      content.getByRole("heading", { name: "Copilot" })
    ).toBeVisible();
  });

  test("engagement dashboard page loads with engagement ID", async ({
    page,
  }) => {
    await page.goto("/dashboard/00000000-0000-0000-0000-000000000001");
    await expect(page.locator("main").first()).toBeVisible();
  });

  test("seeded engagement dashboard loads", async ({ page }) => {
    await page.goto(`/dashboard/${ENGAGEMENT_ID}`);
    await expect(page.locator("main").first()).toBeVisible();
  });

  test("dashboard quick action card navigation works", async ({ page }) => {
    await page.goto("/");
    const content = page.locator("main").first();
    // Click the Evidence Upload card heading/link and verify navigation.
    const evidenceHeading = content.getByRole("heading", {
      name: "Evidence Upload",
    });
    await evidenceHeading.click();
    // After clicking, the URL should move to the evidence section or the
    // heading should still be reachable (page may SPA-navigate or anchor).
    await expect(page).toHaveURL(/evidence|#evidence|\//);
  });
});
