import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID, EVIDENCE_IDS } from "./fixtures/seed-data";

test.describe("Data Lineage Page", () => {
  test("lineage page loads with heading", async ({ page }) => {
    await page.goto("/lineage");
    await expect(
      page.getByRole("heading", { name: "Data Lineage" })
    ).toBeVisible();
  });

  test("lineage page has lookup form", async ({ page }) => {
    await page.goto("/lineage");
    await expect(page.getByPlaceholder(/550e8400/)).toBeVisible();
    await expect(page.getByPlaceholder("Evidence Item ID")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Trace Lineage" })
    ).toBeVisible();
  });

  test("lineage page shows empty state", async ({ page }) => {
    await page.goto("/lineage");
    await expect(
      page.getByText("Enter an engagement and evidence ID to trace lineage")
    ).toBeVisible();
  });

  test("entering seeded engagement ID in lineage form", async ({ page }) => {
    await page.goto("/lineage");
    await page.getByPlaceholder(/550e8400/).fill(ENGAGEMENT_ID);
    await expect(page.getByPlaceholder(/550e8400/)).toHaveValue(ENGAGEMENT_ID);
    await expect(
      page.getByRole("button", { name: "Trace Lineage" })
    ).toBeVisible();
  });

  test("entering evidence ID with engagement ID", async ({ page }) => {
    await page.goto("/lineage");
    await page.getByPlaceholder(/550e8400/).fill(ENGAGEMENT_ID);
    await page
      .getByPlaceholder("Evidence Item ID")
      .fill(EVIDENCE_IDS["loan-policy"]);
    await expect(page.getByPlaceholder(/550e8400/)).toHaveValue(ENGAGEMENT_ID);
    await expect(page.getByPlaceholder("Evidence Item ID")).toHaveValue(
      EVIDENCE_IDS["loan-policy"]
    );
  });
});
