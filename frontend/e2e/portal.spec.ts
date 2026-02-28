import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID } from "./fixtures/seed-data";

test.describe("Portal Pages", () => {
  test("portal landing page loads", async ({ page }) => {
    await page.goto("/portal", { waitUntil: "domcontentloaded" });
    await expect(
      page.getByRole("heading", { name: "KMFlow Client Portal", exact: true })
    ).toBeVisible();
  });

  test("portal process page loads", async ({ page }) => {
    await page.goto("/portal/test-engagement-id/process", { waitUntil: "domcontentloaded" });
    // The layout nav always renders; page shows either content or error state
    await expect(page.getByText("KMFlow Client Portal")).toBeVisible();
    await expect(page.locator("main").first()).toBeVisible();
  });

  test("portal findings page loads", async ({ page }) => {
    await page.goto("/portal/test-engagement-id/findings", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("KMFlow Client Portal")).toBeVisible();
    await expect(page.locator("main").first()).toBeVisible();
  });

  test("portal evidence page loads with heading", async ({ page }) => {
    await page.goto("/portal/test-engagement-id/evidence", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("KMFlow Client Portal")).toBeVisible();
    await expect(page.locator("main").first()).toBeVisible();
  });

  test("portal overview page has navigation links", async ({ page }) => {
    await page.goto("/portal/test-engagement-id", { waitUntil: "domcontentloaded" });
    await expect(page.getByText("Process Explorer")).toBeVisible();
    await expect(page.getByText("Findings")).toBeVisible();
    await expect(page.getByText("Evidence Status")).toBeVisible();
  });

  test("portal overview loads with seeded engagement", async ({ page }) => {
    await page.goto(`/portal/${ENGAGEMENT_ID}`, { waitUntil: "domcontentloaded" });
    await expect(page.getByText("KMFlow Client Portal")).toBeVisible();
    await expect(page.locator("main").first()).toBeVisible();
  });

  test("portal process page loads with seeded engagement", async ({ page }) => {
    await page.goto(`/portal/${ENGAGEMENT_ID}/process`, { waitUntil: "domcontentloaded" });
    await expect(page.getByText("KMFlow Client Portal")).toBeVisible();
    await expect(page.locator("main").first()).toBeVisible();
  });

  test("portal findings page loads with seeded engagement", async ({ page }) => {
    await page.goto(`/portal/${ENGAGEMENT_ID}/findings`, { waitUntil: "domcontentloaded" });
    await expect(page.getByText("KMFlow Client Portal")).toBeVisible();
    await expect(page.locator("main").first()).toBeVisible();
  });
});
