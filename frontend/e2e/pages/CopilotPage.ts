import { type Page, type Locator } from "@playwright/test";

export class CopilotPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly engagementIdInput: Locator;
  readonly queryInput: Locator;
  readonly sendButton: Locator;
  readonly queryTypeSelect: Locator;
  readonly emptyStateMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading", { name: "KMFlow Copilot" });
    this.engagementIdInput = page.getByPlaceholder("Enter engagement UUID");
    this.queryInput = page.getByPlaceholder("Ask a question...");
    this.sendButton = page.getByRole("button", { name: /send/i });
    this.queryTypeSelect = page.locator("select");
    this.emptyStateMessage = page.getByText(
      "Enter an engagement ID and start asking questions"
    );
  }

  async goto(): Promise<void> {
    await this.page.goto("/copilot");
  }

  async enterEngagementId(id: string): Promise<void> {
    await this.engagementIdInput.fill(id);
  }

  async typeQuery(text: string): Promise<void> {
    await this.queryInput.fill(text);
  }

  async sendQuery(text: string): Promise<void> {
    await this.typeQuery(text);
    await this.sendButton.click();
  }

  async selectQueryType(
    value:
      | "general"
      | "process_discovery"
      | "evidence_traceability"
      | "gap_analysis"
      | "regulatory"
  ): Promise<void> {
    await this.queryTypeSelect.selectOption(value);
  }
}
