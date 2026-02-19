import { test, expect } from "@playwright/test";

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
});
