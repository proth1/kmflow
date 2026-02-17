import { test, expect } from "@playwright/test";

test.describe("Conformance Dashboard", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/conformance");
  });

  test("upload form has all required fields", async ({ page }) => {
    await expect(page.getByLabel("Name")).toBeVisible();
    await expect(page.getByLabel("Industry")).toBeVisible();
    await expect(page.getByLabel("Process Area")).toBeVisible();
    await expect(page.getByLabel("BPMN XML").first()).toBeVisible();
  });

  test("upload button is present", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /upload reference model/i })
    ).toBeVisible();
  });

  test("check form has engagement and reference model fields", async ({
    page,
  }) => {
    await expect(page.getByLabel("Engagement ID")).toBeVisible();
    await expect(page.getByLabel("Reference Model")).toBeVisible();
    await expect(page.getByLabel("Observed BPMN XML")).toBeVisible();
  });

  test("run check button is present", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /run conformance check/i })
    ).toBeVisible();
  });

  test("shows empty state for reference models", async ({ page }) => {
    await expect(
      page.getByText("No reference models uploaded yet")
    ).toBeVisible();
  });
});
