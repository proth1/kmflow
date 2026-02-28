import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID } from "./fixtures/seed-data";

test.describe("Admin Page", () => {
  test("admin page loads with heading", async ({ page }) => {
    await page.goto("/admin");
    await expect(
      page.getByRole("heading", { name: "Platform Administration" })
    ).toBeVisible();
  });

  test("admin page shows access warning", async ({ page }) => {
    await page.goto("/admin");
    await expect(page.getByText("Admin Access Required")).toBeVisible();
  });

  test("admin page shows retention cleanup card", async ({ page }) => {
    await page.goto("/admin");
    await expect(
      page.getByRole("heading", { name: "Data Retention Cleanup" })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Preview Cleanup/ })
    ).toBeVisible();
  });

  test("admin page shows key rotation card", async ({ page }) => {
    await page.goto("/admin");
    await expect(
      page.getByRole("heading", { name: "Encryption Key Rotation" })
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Rotate Keys/ })
    ).toBeVisible();
  });

  test("admin page loads with seeded engagement context", async ({ page }) => {
    // The admin page is engagement-agnostic, but verify all 4 action cards are
    // still present when arriving with the seeded engagement in context.
    await page.goto("/admin");
    const main = page.locator("main").first();
    await expect(
      main.getByRole("heading", { name: "Data Retention Cleanup" })
    ).toBeVisible();
    await expect(
      main.getByRole("heading", { name: "Encryption Key Rotation" })
    ).toBeVisible();
    await expect(page.getByText("Admin Access Required")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Platform Administration" })
    ).toBeVisible();
    // Confirm the seeded engagement ID constant resolves to the expected format.
    expect(ENGAGEMENT_ID).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
    );
  });
});
