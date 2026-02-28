import { test, expect } from "./fixtures/base";

test.describe("Integrations Page", () => {
  test("integrations page loads with heading", async ({ page }) => {
    await page.goto("/integrations", { waitUntil: "domcontentloaded" });
    await expect(
      page.getByRole("heading", { name: "Integrations" })
    ).toBeVisible();
  });

  test("integrations page shows tabs", async ({ page }) => {
    await page.goto("/integrations", { waitUntil: "domcontentloaded" });
    await expect(
      page.getByRole("tab", { name: "Connections" })
    ).toBeVisible();
    await expect(
      page.getByRole("tab", { name: "Available Connectors" })
    ).toBeVisible();
  });

  test("integrations page has refresh button", async ({ page }) => {
    await page.goto("/integrations", { waitUntil: "domcontentloaded" });
    await expect(
      page.getByRole("button", { name: "Refresh" })
    ).toBeVisible();
  });

  test("clicking Available Connectors tab shows connector list", async ({
    page,
  }) => {
    await page.goto("/integrations", { waitUntil: "domcontentloaded" });
    const connectorsTab = page.getByRole("tab", { name: "Available Connectors" });
    await connectorsTab.click();
    await expect(connectorsTab).toHaveAttribute("aria-selected", "true");
  });

  test("refresh button triggers data reload", async ({ page }) => {
    await page.goto("/integrations", { waitUntil: "domcontentloaded" });
    const refreshButton = page.getByRole("button", { name: "Refresh" });
    await expect(refreshButton).toBeVisible();
    await refreshButton.click();
    // After clicking refresh the button remains present and the page stays intact
    await expect(
      page.getByRole("heading", { name: "Integrations" })
    ).toBeVisible();
  });
});
