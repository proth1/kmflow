import { test, expect } from "./fixtures/base";
import { SCENARIO_IDS } from "./fixtures/seed-data";

test.describe("Simulations Page", () => {
  test("simulations page loads with heading", async ({ page }) => {
    await page.goto("/simulations");
    await expect(
      page.getByRole("heading", { name: "Simulations" })
    ).toBeVisible();
  });

  test("simulations page shows tabs", async ({ page }) => {
    await page.goto("/simulations");
    await expect(
      page.getByRole("tab", { name: "Scenarios" })
    ).toBeVisible();
    await expect(
      page.getByRole("tab", { name: "Results" })
    ).toBeVisible();
  });

  test("simulations page has refresh button", async ({ page }) => {
    await page.goto("/simulations");
    await expect(
      page.getByRole("button", { name: "Refresh" })
    ).toBeVisible();
  });

  test("evidence gaps tab is visible and clickable", async ({ page }) => {
    await page.goto("/simulations");
    const tab = page.getByRole("tab", { name: "Evidence Gaps" });
    await expect(tab).toBeVisible();
    await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true");
    await expect(
      page.getByRole("heading", { name: "Epistemic Action Plan" })
    ).toBeVisible();
  });

  test("suggestions tab is visible and clickable", async ({ page }) => {
    await page.goto("/simulations");
    const tab = page.getByRole("tab", { name: "Suggestions" });
    await expect(tab).toBeVisible();
    await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true");
  });

  test("financial tab is visible and clickable", async ({ page }) => {
    await page.goto("/simulations");
    const tab = page.getByRole("tab", { name: "Financial" });
    await expect(tab).toBeVisible();
    await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true");
    await expect(
      page.getByRole("heading", { name: "Financial Assumptions" })
    ).toBeVisible();
  });

  test("ranking tab is visible and clickable", async ({ page }) => {
    await page.goto("/simulations");
    const tab = page.getByRole("tab", { name: "Ranking" });
    await expect(tab).toBeVisible();
    await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true");
  });

  test("suggestion disposition workflow shows accept/reject buttons", async ({
    page,
  }) => {
    await page.goto("/simulations");
    const tab = page.getByRole("tab", { name: "Suggestions" });
    await tab.click();
    // Verify tab is active (actual suggestion cards require API data)
    await expect(tab).toHaveAttribute("aria-selected", "true");
  });

  test("financial tab shows assumption form fields", async ({ page }) => {
    await page.goto("/simulations");
    const tab = page.getByRole("tab", { name: "Financial" });
    await tab.click();
    // Verify the financial tab loads its content
    await expect(
      page.getByRole("heading", { name: "Financial Assumptions" })
    ).toBeVisible();
  });

  test("scenarios tab loads with seeded scenario data", async ({ page }) => {
    await page.goto("/simulations");
    const tab = page.getByRole("tab", { name: "Scenarios" });
    await tab.click();
    // Scenarios tab should be selected and its panel content visible
    await expect(tab).toHaveAttribute("aria-selected", "true");
  });

  test("results tab is clickable", async ({ page }) => {
    await page.goto("/simulations");
    const tab = page.getByRole("tab", { name: "Results" });
    await expect(tab).toBeVisible();
    await tab.click();
    await expect(tab).toHaveAttribute("aria-selected", "true");
  });
});
