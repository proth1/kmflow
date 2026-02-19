import { test, expect } from "@playwright/test";

test.describe("Evidence Upload Page", () => {
  test("evidence page loads with heading", async ({ page }) => {
    await page.goto("/evidence");
    await expect(
      page.getByRole("heading", { name: "Evidence Upload" })
    ).toBeVisible();
  });

  test("evidence page has engagement ID input", async ({ page }) => {
    await page.goto("/evidence");
    await expect(
      page.getByPlaceholder("Enter engagement UUID")
    ).toBeVisible();
  });

  test("upload area is disabled without engagement ID", async ({ page }) => {
    await page.goto("/evidence");
    await expect(
      page.getByText("Enter a valid engagement ID above to enable file uploads")
    ).toBeVisible();
  });

  test("upload area enables after entering engagement ID", async ({
    page,
  }) => {
    await page.goto("/evidence");
    await page
      .getByPlaceholder("Enter engagement UUID")
      .fill("00000000-0000-0000-0000-000000000001");
    await expect(
      page.getByText("Drag & drop files or click to browse")
    ).toBeVisible();
  });
});
