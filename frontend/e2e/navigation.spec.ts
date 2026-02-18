import { test, expect } from "@playwright/test";

test.describe("Navigation", () => {
  test("home page loads and shows KMFlow heading", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/KMFlow/i);
  });

  test("copilot page loads with chat interface", async ({ page }) => {
    await page.goto("/copilot");
    await expect(page.getByText("KMFlow Copilot")).toBeVisible();
    await expect(page.getByPlaceholder("Enter engagement UUID")).toBeVisible();
    await expect(page.getByPlaceholder("Ask a question...")).toBeVisible();
  });

  test("conformance page loads with upload form", async ({ page }) => {
    await page.goto("/conformance");
    await expect(
      page.getByText("Conformance Checking Dashboard")
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Upload Reference Model" })
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Run Conformance Check" })
    ).toBeVisible();
  });

  test("monitoring page loads", async ({ page }) => {
    await page.goto("/monitoring");
    await expect(page.getByText("Monitoring")).toBeVisible();
  });

  test("portal page loads", async ({ page }) => {
    await page.goto("/portal");
    await expect(
      page.getByRole("heading", { name: "KMFlow Client Portal", exact: true })
    ).toBeVisible();
  });
});
