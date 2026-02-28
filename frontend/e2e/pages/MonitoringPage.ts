import { type Page, type Locator } from "@playwright/test";

export class MonitoringPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly engagementIdInput: Locator;
  readonly deviationsHeading: Locator;
  readonly alertFeedHeading: Locator;
  readonly mainContent: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading", { name: "Monitoring Dashboard" });
    this.engagementIdInput = page.getByPlaceholder(/550e8400/);
    this.deviationsHeading = page.getByRole("heading", {
      name: "Recent Deviations",
    });
    this.alertFeedHeading = page.getByRole("heading", { name: "Alert Feed" });
    this.mainContent = page.locator("main").first();
  }

  async goto(): Promise<void> {
    await this.page.goto("/monitoring");
  }

  async gotoJob(jobId: string): Promise<void> {
    await this.page.goto(`/monitoring/${jobId}`);
  }

  async enterEngagementId(id: string): Promise<void> {
    await this.engagementIdInput.fill(id);
  }
}
