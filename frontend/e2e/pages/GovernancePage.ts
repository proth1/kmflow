import { type Page, type Locator } from "@playwright/test";

export class GovernancePage {
  readonly page: Page;
  readonly heading: Locator;
  readonly engagementIdInput: Locator;
  readonly catalogTab: Locator;
  readonly slaTab: Locator;
  readonly policiesTab: Locator;
  readonly emptyCatalogMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading", { name: "Data Governance" });
    this.engagementIdInput = page.getByPlaceholder(/550e8400/);
    this.catalogTab = page.getByRole("tab", { name: "Data Catalog" });
    this.slaTab = page.getByRole("tab", { name: "SLA Health" });
    this.policiesTab = page.getByRole("tab", { name: "Policies" });
    this.emptyCatalogMessage = page.getByText(
      "Enter an engagement ID to view catalog"
    );
  }

  async goto(): Promise<void> {
    await this.page.goto("/governance");
  }

  async enterEngagementId(id: string): Promise<void> {
    await this.engagementIdInput.fill(id);
  }

  async clickCatalogTab(): Promise<void> {
    await this.catalogTab.click();
  }

  async clickSlaTab(): Promise<void> {
    await this.slaTab.click();
  }

  async clickPoliciesTab(): Promise<void> {
    await this.policiesTab.click();
  }
}
