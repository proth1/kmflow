/**
 * Extended Playwright test fixtures for KMFlow E2E tests.
 *
 * All spec files should import { test, expect } from this module
 * instead of from "@playwright/test" directly.
 */

import { test as base, expect } from "@playwright/test";
import { ApiHelper } from "./api-helper";
import { ENGAGEMENT_ID } from "./seed-data";

/**
 * Custom fixture types available in all tests.
 */
interface KMFlowFixtures {
  /** Pre-computed engagement ID from seeded demo data. */
  seedEngagementId: string;
  /** API helper for programmatic test setup/teardown. */
  apiHelper: ApiHelper;
}

/**
 * Extended test function with KMFlow-specific fixtures.
 */
export const test = base.extend<KMFlowFixtures>({
  seedEngagementId: async ({}, use) => {
    await use(ENGAGEMENT_ID);
  },

  apiHelper: async ({ request }, use) => {
    const helper = new ApiHelper(request);
    await use(helper);
  },
});

export { expect };
