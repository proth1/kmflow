import { test, expect } from "@playwright/test";

test.describe("Copilot Chat", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/copilot");
  });

  test("send button is disabled without engagement ID", async ({ page }) => {
    const sendButton = page.getByRole("button", { name: /send/i });
    await expect(sendButton).toBeDisabled();
  });

  test("send button is disabled without query text", async ({ page }) => {
    await page.getByPlaceholder("Enter engagement UUID").fill(
      "00000000-0000-0000-0000-000000000001"
    );
    const sendButton = page.getByRole("button", { name: /send/i });
    await expect(sendButton).toBeDisabled();
  });

  test("query type selector has all options", async ({ page }) => {
    const select = page.locator("select");
    const options = await select.locator("option").allTextContents();
    expect(options).toContain("General");
    expect(options).toContain("Process Discovery");
    expect(options).toContain("Evidence Traceability");
    expect(options).toContain("Gap Analysis");
    expect(options).toContain("Regulatory");
  });

  test("shows placeholder text when no messages", async ({ page }) => {
    await expect(
      page.getByText("Enter an engagement ID and start asking questions")
    ).toBeVisible();
  });
});
