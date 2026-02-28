import { type Page, type Locator } from "@playwright/test";

export class ProcessesPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly mainContent: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading", { name: "Process Management" });
    this.mainContent = page.locator("main").first();
  }

  async goto(): Promise<void> {
    await this.page.goto("/processes");
  }
}
