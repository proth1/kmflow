import { type Page, type Locator } from "@playwright/test";

export class PortalPage {
  readonly page: Page;
  readonly portalHeading: Locator;
  readonly mainContent: Locator;
  readonly processExplorer: Locator;
  readonly findings: Locator;
  readonly evidenceStatus: Locator;

  constructor(page: Page) {
    this.page = page;
    this.portalHeading = page.getByRole("heading", {
      name: "KMFlow Client Portal",
      exact: true,
    });
    this.mainContent = page.locator("main").first();
    this.processExplorer = page.getByText("Process Explorer");
    this.findings = page.getByText("Findings");
    this.evidenceStatus = page.getByText("Evidence Status");
  }

  async goto(engagementId: string): Promise<void> {
    await this.page.goto(`/portal/${engagementId}`);
  }

  async gotoLanding(): Promise<void> {
    await this.page.goto("/portal");
  }

  async gotoProcess(engagementId: string): Promise<void> {
    await this.page.goto(`/portal/${engagementId}/process`);
  }

  async gotoFindings(engagementId: string): Promise<void> {
    await this.page.goto(`/portal/${engagementId}/findings`);
  }

  async gotoEvidence(engagementId: string): Promise<void> {
    await this.page.goto(`/portal/${engagementId}/evidence`);
  }

  async clickProcessExplorer(): Promise<void> {
    await this.processExplorer.click();
  }

  async clickFindings(): Promise<void> {
    await this.findings.click();
  }

  async clickEvidenceStatus(): Promise<void> {
    await this.evidenceStatus.click();
  }
}
