import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID } from "./fixtures/seed-data";

test.describe("Reports Page", () => {
  test("reports page loads with heading", async ({ page }) => {
    await page.goto("/reports");
    await expect(
      page.getByRole("heading", { name: "Reports" })
    ).toBeVisible();
  });

  test("reports page has engagement ID input", async ({ page }) => {
    await page.goto("/reports");
    await expect(
      page.getByPlaceholder(/550e8400/)
    ).toBeVisible();
  });

  test("reports page shows all report type cards", async ({ page }) => {
    await page.goto("/reports");
    await expect(
      page.getByRole("heading", { name: "Engagement Summary" })
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Gap Analysis" })
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Governance Overlay" })
    ).toBeVisible();
  });

  test("generate buttons are disabled without engagement ID", async ({
    page,
  }) => {
    await page.goto("/reports");
    const buttons = page.getByRole("button", { name: "Generate JSON" });
    const count = await buttons.count();
    for (let i = 0; i < count; i++) {
      await expect(buttons.nth(i)).toBeDisabled();
    }
  });

  test("entering seeded engagement ID enables generate buttons", async ({
    page,
  }) => {
    await page.goto("/reports");
    const input = page.getByPlaceholder(/550e8400/);
    await input.fill(ENGAGEMENT_ID);
    await expect(input).toHaveValue(ENGAGEMENT_ID);
    const buttons = page.getByRole("button", { name: "Generate JSON" });
    const count = await buttons.count();
    for (let i = 0; i < count; i++) {
      await expect(buttons.nth(i)).toBeEnabled();
    }
  });

  test("report type cards are clickable", async ({ page }) => {
    await page.goto("/reports");
    await expect(
      page.getByRole("heading", { name: "Engagement Summary" })
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Gap Analysis" })
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Governance Overlay" })
    ).toBeVisible();
  });
});
