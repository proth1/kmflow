import { type Page, type Locator } from "@playwright/test";

export class EvidencePage {
  readonly page: Page;
  readonly heading: Locator;
  readonly engagementIdInput: Locator;
  readonly dropZone: Locator;
  readonly fileInput: Locator;
  readonly disabledUploadMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading", { name: "Evidence Upload" });
    this.engagementIdInput = page.getByPlaceholder("Enter engagement UUID");
    this.dropZone = page.getByText("Drag & drop files or click to browse");
    this.fileInput = page.locator('input[type="file"]');
    this.disabledUploadMessage = page.getByText(
      "Enter a valid engagement ID above to enable file uploads"
    );
  }

  async goto(): Promise<void> {
    await this.page.goto("/evidence");
  }

  async enterEngagementId(id: string): Promise<void> {
    await this.engagementIdInput.fill(id);
  }

  async uploadFile(filePath: string): Promise<void> {
    await this.fileInput.setInputFiles(filePath);
  }
}
