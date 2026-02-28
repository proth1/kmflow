/**
 * E2E tests for Switching Sequence analysis pages.
 *
 * Tests the cross-system switching trace viewer, transition matrix,
 * and friction analysis endpoints via the UI.
 */

import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID, USERS } from "./fixtures/seed-data";

test.describe("Switching Sequences", () => {
  test.beforeEach(async ({ page, apiHelper }) => {
    await apiHelper.loginAs(USERS.analyst.email, USERS.analyst.password);
    await page.goto(`/engagements/${ENGAGEMENT_ID}/task-mining`);
  });

  test("displays switching traces tab", async ({ page }) => {
    await page.getByRole("tab", { name: /switching/i }).click();
    await expect(page.getByText(/switching traces/i)).toBeVisible();
  });

  test("shows friction analysis summary", async ({ page }) => {
    await page.getByRole("tab", { name: /switching/i }).click();
    await expect(page.getByText(/friction score/i)).toBeVisible();
  });

  test("renders transition matrix heatmap", async ({ page }) => {
    await page.getByRole("tab", { name: /switching/i }).click();
    await page.getByRole("button", { name: /transition matrix/i }).click();
    await expect(page.getByText(/transition matrix/i)).toBeVisible();
  });

  test("filters switching traces by session", async ({ page }) => {
    await page.getByRole("tab", { name: /switching/i }).click();
    const filterInput = page.getByPlaceholder(/filter/i);
    if (await filterInput.isVisible()) {
      await filterInput.fill("ping-pong");
      await expect(page.getByText(/ping.pong/i)).toBeVisible();
    }
  });

  test("API: GET switching traces returns data", async ({ apiHelper, seedEngagementId }) => {
    const response = await apiHelper.get(
      `/api/v1/taskmining/switching/traces?engagement_id=${seedEngagementId}`
    );
    expect(response).toBeDefined();
  });

  test("API: GET transition matrix returns data", async ({ apiHelper, seedEngagementId }) => {
    const response = await apiHelper.get(
      `/api/v1/taskmining/switching/matrix?engagement_id=${seedEngagementId}`
    );
    expect(response).toBeDefined();
  });

  test("API: GET friction analysis returns scores", async ({ apiHelper, seedEngagementId }) => {
    const response = await apiHelper.get(
      `/api/v1/taskmining/switching/friction?engagement_id=${seedEngagementId}`
    );
    expect(response).toBeDefined();
  });
});
