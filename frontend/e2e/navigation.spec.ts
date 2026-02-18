import { test, expect } from "@playwright/test";

test.describe("Navigation", () => {
  test("home page loads and shows dashboard heading", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/KMFlow/i);
    await expect(
      page.getByRole("heading", { name: "Process Intelligence Dashboard" })
    ).toBeVisible();
  });

  test("sidebar is visible on desktop", async ({ page }) => {
    await page.goto("/");
    // Sidebar shows KMFlow branding
    await expect(page.locator("aside").getByText("KMFlow")).toBeVisible();
  });

  test("sidebar navigation links to key sections", async ({ page }) => {
    await page.goto("/");
    const sidebar = page.locator("aside");
    await expect(sidebar.getByText("Dashboard")).toBeVisible();
    await expect(sidebar.getByText("Monitoring")).toBeVisible();
    await expect(sidebar.getByText("Copilot")).toBeVisible();
    await expect(sidebar.getByText("Portal")).toBeVisible();
    await expect(sidebar.getByText("Conformance")).toBeVisible();
    await expect(sidebar.getByText("Processes")).toBeVisible();
  });

  test("clicking sidebar link navigates to page", async ({ page }) => {
    await page.goto("/");
    const sidebar = page.locator("aside");
    await sidebar.getByText("Conformance").click();
    await expect(page).toHaveURL(/\/conformance/);
    await expect(
      page.getByText("Conformance Checking Dashboard")
    ).toBeVisible();
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

  test("processes page loads", async ({ page }) => {
    await page.goto("/processes");
    await expect(
      page.getByRole("heading", { name: "Process Management" })
    ).toBeVisible();
  });
});
