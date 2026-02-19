import { test, expect } from "@playwright/test";

test.describe("TOM Alignment Page", () => {
  test("TOM page loads with engagement ID parameter", async ({ page }) => {
    await page.goto("/tom/00000000-0000-0000-0000-000000000001");
    const main = page.locator("main");
    await expect(main).toBeVisible();
  });

  test("TOM page shows heading", async ({ page }) => {
    await page.goto("/tom/00000000-0000-0000-0000-000000000001");
    await expect(
      page.getByRole("heading", { name: /TOM/i })
    ).toBeVisible();
  });
});
