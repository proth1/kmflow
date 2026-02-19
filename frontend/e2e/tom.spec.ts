import { test, expect } from "@playwright/test";

test.describe("TOM Alignment Page", () => {
  test("TOM page loads with engagement ID parameter", async ({ page }) => {
    await page.goto("/tom/00000000-0000-0000-0000-000000000001");
    const main = page.locator("main");
    await expect(main).toBeVisible();
  });

  test("TOM page shows heading or error state", async ({ page }) => {
    await page.goto("/tom/demo-1");
    // Page shows either TOM heading (if API available) or error state
    const heading = page.getByRole("heading", { name: /TOM Alignment Dashboard/i });
    const errorHeading = page.getByRole("heading", { name: /Error/i });
    await expect(heading.or(errorHeading)).toBeVisible();
  });
});
