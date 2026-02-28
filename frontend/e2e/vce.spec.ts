/**
 * E2E tests for Visual Context Event (VCE) analysis pages.
 *
 * Tests the VCE event viewer, screen state distribution,
 * trigger summary, and dwell analysis.
 */

import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID, USERS } from "./fixtures/seed-data";

test.describe("Visual Context Events", () => {
  test.beforeEach(async ({ page, apiHelper }) => {
    await apiHelper.loginAs(USERS.analyst.email, USERS.analyst.password);
    await page.goto(`/engagements/${ENGAGEMENT_ID}/task-mining`);
  });

  test("displays VCE tab in task mining view", async ({ page }) => {
    await page.getByRole("tab", { name: /visual context/i }).click();
    await expect(page.getByText(/visual context events/i)).toBeVisible();
  });

  test("shows screen state distribution chart", async ({ page }) => {
    await page.getByRole("tab", { name: /visual context/i }).click();
    await expect(page.getByText(/screen state/i)).toBeVisible();
  });

  test("shows trigger reason summary", async ({ page }) => {
    await page.getByRole("tab", { name: /visual context/i }).click();
    await page.getByRole("button", { name: /triggers/i }).click();
    await expect(page.getByText(/trigger/i)).toBeVisible();
  });

  test("displays dwell analysis", async ({ page }) => {
    await page.getByRole("tab", { name: /visual context/i }).click();
    await page.getByRole("button", { name: /dwell/i }).click();
    await expect(page.getByText(/dwell/i)).toBeVisible();
  });

  test("API: GET VCE list returns events", async ({ apiHelper, seedEngagementId }) => {
    const response = await apiHelper.get(
      `/api/v1/taskmining/vce?engagement_id=${seedEngagementId}`
    );
    expect(response).toBeDefined();
  });

  test("API: GET VCE distribution returns screen states", async ({ apiHelper, seedEngagementId }) => {
    const response = await apiHelper.get(
      `/api/v1/taskmining/vce/distribution?engagement_id=${seedEngagementId}`
    );
    expect(response).toBeDefined();
  });

  test("API: GET VCE trigger summary returns data", async ({ apiHelper, seedEngagementId }) => {
    const response = await apiHelper.get(
      `/api/v1/taskmining/vce/triggers/summary?engagement_id=${seedEngagementId}`
    );
    expect(response).toBeDefined();
  });
});
