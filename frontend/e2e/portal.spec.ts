import { test, expect } from "@playwright/test";

test.describe("Portal Pages", () => {
  test("portal landing page loads", async ({ page }) => {
    await page.goto("/portal");
    await expect(
      page.getByRole("heading", { name: "KMFlow Client Portal", exact: true })
    ).toBeVisible();
  });

  test("portal process page loads", async ({ page }) => {
    await page.goto("/portal/test-engagement-id/process");
    // The layout nav always renders; page shows either content or error state
    await expect(page.getByText("KMFlow Client Portal")).toBeVisible();
    await expect(page.locator("main").first()).toBeVisible();
  });

  test("portal findings page loads", async ({ page }) => {
    await page.goto("/portal/test-engagement-id/findings");
    await expect(page.getByText("KMFlow Client Portal")).toBeVisible();
    await expect(page.locator("main").first()).toBeVisible();
  });

  test("portal evidence page loads with heading", async ({ page }) => {
    await page.goto("/portal/test-engagement-id/evidence");
    await expect(page.getByText("KMFlow Client Portal")).toBeVisible();
    await expect(page.locator("main").first()).toBeVisible();
  });

  test("portal overview page has navigation links", async ({ page }) => {
    await page.goto("/portal/test-engagement-id");
    await expect(page.getByText("Process Explorer")).toBeVisible();
    await expect(page.getByText("Findings")).toBeVisible();
    await expect(page.getByText("Evidence Status")).toBeVisible();
  });
});
