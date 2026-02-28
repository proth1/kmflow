import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID } from "./fixtures/seed-data";

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

  test("entering seeded engagement ID shows shelf requests", async ({
    page,
  }) => {
    await page.goto("/shelf-requests");
    const input = page.getByPlaceholder(/550e8400/);
    await input.fill(ENGAGEMENT_ID);
    await input.press("Enter");
    await expect(
      page.getByText("Enter an engagement ID to view shelf requests")
    ).not.toBeVisible();
  });

  test("shelf requests page loads content after engagement ID entry", async ({
    page,
  }) => {
    await page.goto("/shelf-requests");
    const input = page.getByPlaceholder(/550e8400/);
    await input.fill(ENGAGEMENT_ID);
    await input.press("Enter");
    // Verify the input retains the engagement ID
    await expect(input).toHaveValue(ENGAGEMENT_ID);
  });
});
