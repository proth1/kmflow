import { type Page, type Locator } from "@playwright/test";

export class AdminPage {
  readonly page: Page;
  readonly heading: Locator;
  readonly accessWarning: Locator;
  readonly retentionHeading: Locator;
  readonly cleanupButton: Locator;
  readonly keyRotationHeading: Locator;
  readonly rotateKeysButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.heading = page.getByRole("heading", {
      name: "Platform Administration",
    });
    this.accessWarning = page.getByText("Admin Access Required");
    this.retentionHeading = page.getByRole("heading", {
      name: "Data Retention Cleanup",
    });
    this.cleanupButton = page.getByRole("button", { name: /Preview Cleanup/ });
    this.keyRotationHeading = page.getByRole("heading", {
      name: "Encryption Key Rotation",
    });
    this.rotateKeysButton = page.getByRole("button", { name: /Rotate Keys/ });
  }

  async goto(): Promise<void> {
    await this.page.goto("/admin");
  }
}
