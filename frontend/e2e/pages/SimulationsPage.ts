import { type Page, type Locator } from "@playwright/test";

export class SimulationsPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly scenariosTab: Locator;
  readonly resultsTab: Locator;
  readonly evidenceGapsTab: Locator;
  readonly suggestionsTab: Locator;
  readonly financialTab: Locator;
  readonly rankingTab: Locator;
  readonly refreshButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading", { name: "Simulations" });
    this.scenariosTab = page.getByRole("tab", { name: "Scenarios" });
    this.resultsTab = page.getByRole("tab", { name: "Results" });
    this.evidenceGapsTab = page.getByRole("tab", { name: "Evidence Gaps" });
    this.suggestionsTab = page.getByRole("tab", { name: "Suggestions" });
    this.financialTab = page.getByRole("tab", { name: "Financial" });
    this.rankingTab = page.getByRole("tab", { name: "Ranking" });
    this.refreshButton = page.getByRole("button", { name: "Refresh" });
  }

  async goto(): Promise<void> {
    await this.page.goto("/simulations");
  }

  async clickScenariosTab(): Promise<void> {
    await this.scenariosTab.click();
  }

  async clickResultsTab(): Promise<void> {
    await this.resultsTab.click();
  }

  async clickEvidenceGapsTab(): Promise<void> {
    await this.evidenceGapsTab.click();
  }

  async clickSuggestionsTab(): Promise<void> {
    await this.suggestionsTab.click();
  }

  async clickFinancialTab(): Promise<void> {
    await this.financialTab.click();
  }

  async clickRankingTab(): Promise<void> {
    await this.rankingTab.click();
  }

  async clickRefresh(): Promise<void> {
    await this.refreshButton.click();
  }
}
