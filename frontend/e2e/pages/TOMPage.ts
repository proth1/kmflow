import { type Page, type Locator } from "@playwright/test";

export class TOMPage {
  readonly page: Page;
  readonly mainContent: Locator;
  readonly dimensionCards: Locator;
  readonly gapTable: Locator;
  readonly heading: Locator;

  constructor(page: Page) {
    this.page = page;
    this.mainContent = page.locator("main");
    this.dimensionCards = page.getByTestId("tom-dimension-card");
    this.gapTable = page.getByTestId("gap-table");
    this.heading = page.getByRole("heading", {
      name: /TOM Alignment Dashboard/i,
    });
  }

  async goto(engagementId: string): Promise<void> {
    await this.page.goto(`/tom/${engagementId}`);
  }
}
