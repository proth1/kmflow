import { defineConfig, devices } from "@playwright/test";

/**
 * KMFlow E2E Test Configuration
 *
 * Usage:
 *   Against Docker (default):   npm run test:e2e
 *   Against local dev server:   npm run test:e2e:local
 *   Interactive UI mode:        npm run test:e2e:ui
 *   Custom URL:                 E2E_BASE_URL=http://... npm run test:e2e
 */

const baseURL =
  process.env.E2E_BASE_URL ||
  (process.env.E2E_LOCAL === "true"
    ? "http://localhost:3000"
    : "http://localhost:3002");

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report" }],
    ["json", { outputFile: "playwright-report/results.json" }],
  ],
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        storageState: "e2e/.auth/admin.json",
      },
    },
    {
      name: "unauthenticated",
      use: {
        ...devices["Desktop Chrome"],
      },
      testMatch: /auth\.spec\.ts/,
    },
  ],
  ...(process.env.E2E_LOCAL === "true"
    ? {
        webServer: {
          command: "npm run dev",
          url: "http://localhost:3000",
          reuseExistingServer: true,
          timeout: 30_000,
        },
      }
    : {}),
});
