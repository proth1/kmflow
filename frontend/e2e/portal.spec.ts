import { test, expect } from "@playwright/test";

test.describe("Portal Pages", () => {
  test("portal landing page loads", async ({ page }) => {
    await page.goto("/portal");
    await expect(page.getByText("Client Portal")).toBeVisible();
  });

  test("portal process page loads with heading", async ({ page }) => {
    await page.goto("/portal/test-engagement-id/process");
    await expect(page.getByText("Process Explorer")).toBeVisible();
  });

  test("portal findings page loads with table", async ({ page }) => {
    await page.goto("/portal/test-engagement-id/findings");
    await expect(page.getByText("Gap Analysis Findings")).toBeVisible();
    await expect(page.locator("table")).toBeVisible();
  });

  test("portal evidence page loads with heading", async ({ page }) => {
    await page.goto("/portal/test-engagement-id/evidence");
    await expect(page.getByText("Evidence Status")).toBeVisible();
  });

  test("portal overview page has navigation links", async ({ page }) => {
    await page.goto("/portal/test-engagement-id");
    await expect(page.getByText("Process Explorer")).toBeVisible();
    await expect(page.getByText("Findings")).toBeVisible();
    await expect(page.getByText("Evidence Status")).toBeVisible();
  });
});
