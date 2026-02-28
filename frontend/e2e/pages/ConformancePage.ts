import { type Page, type Locator } from "@playwright/test";

export class ConformancePage {
  readonly page: Page;
  readonly heading: Locator;
  // Upload form fields
  readonly nameInput: Locator;
  readonly industryInput: Locator;
  readonly processAreaInput: Locator;
  readonly bpmnXmlInput: Locator;
  readonly uploadButton: Locator;
  // Check form fields
  readonly engagementIdInput: Locator;
  readonly referenceModelSelect: Locator;
  readonly observedBpmnXmlInput: Locator;
  readonly runCheckButton: Locator;
  // Reference models list
  readonly emptyModelsMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading", {
      name: "Conformance Checking Dashboard",
    });
    // Upload form
    this.nameInput = page.getByLabel("Name");
    this.industryInput = page.getByLabel("Industry");
    this.processAreaInput = page.getByLabel("Process Area");
    this.bpmnXmlInput = page.getByLabel("BPMN XML").first();
    this.uploadButton = page.getByRole("button", {
      name: /upload reference model/i,
    });
    // Check form
    this.engagementIdInput = page.getByLabel("Engagement ID");
    this.referenceModelSelect = page.getByLabel("Reference Model");
    this.observedBpmnXmlInput = page.getByLabel("Observed BPMN XML");
    this.runCheckButton = page.getByRole("button", {
      name: /run conformance check/i,
    });
    // Reference models list
    this.emptyModelsMessage = page.getByText(
      "No reference models uploaded yet"
    );
  }

  async goto(): Promise<void> {
    await this.page.goto("/conformance");
  }

  async fillUploadForm(opts: {
    name: string;
    industry: string;
    processArea: string;
    bpmnXml: string;
  }): Promise<void> {
    await this.nameInput.fill(opts.name);
    await this.industryInput.fill(opts.industry);
    await this.processAreaInput.fill(opts.processArea);
    await this.bpmnXmlInput.fill(opts.bpmnXml);
  }

  async submitUpload(): Promise<void> {
    await this.uploadButton.click();
  }

  async fillCheckForm(opts: {
    engagementId: string;
    referenceModelId: string;
    observedBpmnXml: string;
  }): Promise<void> {
    await this.engagementIdInput.fill(opts.engagementId);
    await this.referenceModelSelect.selectOption(opts.referenceModelId);
    await this.observedBpmnXmlInput.fill(opts.observedBpmnXml);
  }

  async runCheck(): Promise<void> {
    await this.runCheckButton.click();
  }
}
