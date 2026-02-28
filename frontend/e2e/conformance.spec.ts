import { test, expect } from "./fixtures/base";
import { ENGAGEMENT_ID } from "./fixtures/seed-data";

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

  test("entering seeded engagement ID in check form", async ({ page }) => {
    const engagementInput = page.getByLabel("Engagement ID");
    await engagementInput.fill(ENGAGEMENT_ID);
    await expect(engagementInput).toHaveValue(ENGAGEMENT_ID);
  });

  test("BPMN XML textarea accepts input", async ({ page }) => {
    const sampleXml =
      '<?xml version="1.0" encoding="UTF-8"?><definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"></definitions>';
    // "Observed BPMN XML" is the textarea in the check form.
    const bpmnTextarea = page.getByLabel("Observed BPMN XML");
    await bpmnTextarea.fill(sampleXml);
    await expect(bpmnTextarea).toHaveValue(sampleXml);
  });
});
