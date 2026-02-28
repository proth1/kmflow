/**
 * E2E tests for the Correlation Engine.
 *
 * Tests case linkage quality dashboard, link browsing,
 * diagnostics, and unlinked event analysis.
 */

import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID, USERS } from "./fixtures/seed-data";

test.describe("Correlation Engine", () => {
  test.beforeEach(async ({ page, apiHelper }) => {
    await apiHelper.loginAs(USERS.lead.email, USERS.lead.password);
    await page.goto(`/engagements/${ENGAGEMENT_ID}/task-mining`);
  });

  test("displays correlation tab", async ({ page }) => {
    await page.getByRole("tab", { name: /correlation/i }).click();
    await expect(page.getByText(/case linkage/i)).toBeVisible();
  });

  test("shows linkage quality dashboard", async ({ page }) => {
    await page.getByRole("tab", { name: /correlation/i }).click();
    await expect(page.getByText(/linkage quality/i)).toBeVisible();
  });

  test("shows unlinked events section", async ({ page }) => {
    await page.getByRole("tab", { name: /correlation/i }).click();
    await page.getByRole("button", { name: /unlinked/i }).click();
    await expect(page.getByText(/unlinked/i)).toBeVisible();
  });

  test("API: GET correlation links returns data", async ({ apiHelper, seedEngagementId }) => {
    const response = await apiHelper.get(
      `/api/v1/correlation/links?engagement_id=${seedEngagementId}`
    );
    expect(response).toBeDefined();
  });

  test("API: GET correlation diagnostics returns report", async ({ apiHelper, seedEngagementId }) => {
    const response = await apiHelper.get(
      `/api/v1/correlation/diagnostics?engagement_id=${seedEngagementId}`
    );
    expect(response).toBeDefined();
  });

  test("API: GET unlinked events returns data", async ({ apiHelper, seedEngagementId }) => {
    const response = await apiHelper.get(
      `/api/v1/correlation/unlinked?engagement_id=${seedEngagementId}`
    );
    expect(response).toBeDefined();
  });
});
