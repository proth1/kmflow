import { test, expect } from "./fixtures/base";
import * as path from "path";

const authDir = path.resolve(__dirname, ".auth");

test.describe("Role-Based Access Control", () => {
  test.describe("Admin role", () => {
    test.use({ storageState: path.join(authDir, "admin.json") });

    test("admin can access admin page", async ({ page }) => {
      await page.goto("/admin");
      await expect(
        page.getByRole("heading", { name: "Platform Administration" })
      ).toBeVisible();
    });

    test("admin can access evidence page", async ({ page }) => {
      await page.goto("/evidence");
      await expect(
        page.getByRole("heading", { name: "Evidence Upload" })
      ).toBeVisible();
    });
  });

  test.describe("Viewer role", () => {
    test.use({ storageState: path.join(authDir, "viewer.json") });

    test("viewer can access portal page", async ({ page }) => {
      await page.goto("/portal");
      await expect(
        page.getByRole("heading", { name: "KMFlow Client Portal", exact: true })
      ).toBeVisible();
    });

    test("viewer navigating to admin page sees access warning", async ({ page }) => {
      await page.goto("/admin");
      await expect(page.getByText("Admin Access Required")).toBeVisible();
    });
  });

  test.describe("Analyst role", () => {
    test.use({ storageState: path.join(authDir, "analyst.json") });

    test("analyst can access evidence page", async ({ page }) => {
      await page.goto("/evidence");
      await expect(
        page.getByRole("heading", { name: "Evidence Upload" })
      ).toBeVisible();
    });

    test("analyst can access conformance page", async ({ page }) => {
      await page.goto("/conformance");
      await expect(
        page.getByText("Conformance Checking Dashboard")
      ).toBeVisible();
    });
  });

  test.describe("Lead role", () => {
    test.use({ storageState: path.join(authDir, "lead.json") });

    test("lead can access dashboard", async ({ page }) => {
      await page.goto("/");
      await expect(page.locator("main").first()).toBeVisible();
    });
  });
});
