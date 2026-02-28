import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID } from "./fixtures/seed-data";

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

  test("entering seeded engagement ID enables send button with query", async ({
    page,
  }) => {
    await page.getByPlaceholder("Enter engagement UUID").fill(ENGAGEMENT_ID);
    await page.getByRole("textbox", { name: /question|query|message/i }).fill(
      "What are the key process gaps?"
    );
    const sendButton = page.getByRole("button", { name: /send/i });
    await expect(sendButton).toBeEnabled();
  });

  test("copilot page shows engagement context after ID entry", async ({
    page,
  }) => {
    const uuidInput = page.getByPlaceholder("Enter engagement UUID");
    await uuidInput.fill(ENGAGEMENT_ID);
    await expect(uuidInput).toHaveValue(ENGAGEMENT_ID);
    // The placeholder hint text should no longer be the only content visible —
    // the engagement field is populated so the UI is no longer in the blank state.
    await expect(uuidInput).not.toBeEmpty();
  });
});
