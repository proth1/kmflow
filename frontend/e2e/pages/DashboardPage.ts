import { type Page, type Locator } from "@playwright/test";

export class DashboardPage {
  readonly page: Page;
  readonly kpiCards: Locator;
  readonly quickActionButtons: Locator;
  readonly heading: Locator;
  readonly platformStatus: Locator;
  readonly quickActionsSection: Locator;

  constructor(page: Page) {
    this.page = page;
    this.kpiCards = page.getByTestId("kpi-card");
    this.quickActionButtons = page.locator("main").first().getByRole("link");
    this.heading = page.getByRole("heading", {
      name: "Process Intelligence Dashboard",
    });
    this.platformStatus = page.getByText("Platform Status");
    this.quickActionsSection = page.getByText("Quick Actions");
  }

  async goto(): Promise<void> {
    await this.page.goto("/");
  }

  async gotoEngagement(engagementId: string): Promise<void> {
    await this.page.goto(`/dashboard/${engagementId}`);
  }

  getQuickActionCard(name: string): Locator {
    return this.page.locator("main").first().getByRole("heading", { name });
  }
}
