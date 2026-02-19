import { test, expect } from "@playwright/test";

test.describe("Shelf Requests Page", () => {
  test("shelf requests page loads with heading", async ({ page }) => {
    await page.goto("/shelf-requests");
    await expect(
      page.getByRole("heading", { name: "Shelf Data Requests" })
    ).toBeVisible();
  });

  test("shelf requests page has engagement ID input", async ({ page }) => {
    await page.goto("/shelf-requests");
    await expect(
      page.getByPlaceholder(/550e8400/)
    ).toBeVisible();
  });

  test("shelf requests page shows empty state without engagement", async ({
    page,
  }) => {
    await page.goto("/shelf-requests");
    await expect(
      page.getByText("Enter an engagement ID to view shelf requests")
    ).toBeVisible();
  });
});
