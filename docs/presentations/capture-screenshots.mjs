/**
 * Capture KMFlow screenshots for presentation persona modals.
 *
 * Uses Playwright to:
 * 1. Login once per persona via the API (sets HttpOnly cookies)
 * 2. Reuse browser context across pages for the same user
 * 3. Navigate with engagement ID for data-dependent pages
 * 4. Take viewport screenshots at 2x resolution
 */

import { chromium } from 'playwright';

const BASE_URL = 'http://localhost:3000';
const API_URL = 'http://localhost:8000';
const SCREENSHOT_DIR = './screenshots';
const ENGAGEMENT_ID = 'ca1a4c95-7a4a-444e-a021-979b06174dba';

const USERS = {
  admin: { email: 'admin@acme-demo.com', password: 'password123' },
  lead: { email: 'lead@acme-demo.com', password: 'password123' },
  analyst: { email: 'analyst@acme-demo.com', password: 'password123' },
  reviewer: { email: 'reviewer@acme-demo.com', password: 'password123' },
  client: { email: 'viewer@acme-demo.com', password: 'password123' },
};

// Group screenshots by user — use engagement ID routes where available
const SCREENSHOTS_BY_USER = {
  admin: [
    { name: 'admin', path: '/admin' },
    { name: 'governance', path: '/governance' },
    { name: 'integrations', path: '/integrations' },
    { name: 'monitoring', path: '/monitoring' },
  ],
  lead: [
    { name: 'dashboard', path: `/dashboard/${ENGAGEMENT_ID}` },
    { name: 'analytics', path: '/analytics' },
    { name: 'simulations', path: '/simulations' },
  ],
  analyst: [
    { name: 'copilot', path: '/copilot' },
    { name: 'lineage', path: '/lineage' },
    { name: 'patterns', path: '/patterns' },
  ],
  reviewer: [
    { name: 'evidence', path: '/evidence' },
  ],
};

async function main() {
  console.log('Starting KMFlow screenshot capture...\n');

  const browser = await chromium.launch({ headless: true });

  for (const [userKey, screenshots] of Object.entries(SCREENSHOTS_BY_USER)) {
    const user = USERS[userKey];
    console.log(`\n=== Logging in as ${userKey} (${user.email}) ===`);

    const context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 2,
    });

    // Login once per user
    const loginRes = await context.request.post(`${API_URL}/api/v1/auth/login`, {
      data: { email: user.email, password: user.password },
      headers: { 'Content-Type': 'application/json' },
    });
    if (loginRes.status() !== 200) {
      console.error(`  Login failed: ${loginRes.status()} ${await loginRes.text()}`);
      await context.close();
      continue;
    }
    console.log(`  Logged in successfully`);

    for (const { name, path } of screenshots) {
      console.log(`  Capturing ${name}.png (${path})...`);
      const page = await context.newPage();

      try {
        await page.goto(`${BASE_URL}${path}`, { waitUntil: 'networkidle', timeout: 30000 });
        try {
          await page.waitForSelector('main', { timeout: 5000 });
        } catch {
          // Page might not have a main element
        }
        await page.waitForTimeout(2000);

        await page.screenshot({
          path: `${SCREENSHOT_DIR}/${name}.png`,
          fullPage: false,
        });
        console.log(`    Saved ${name}.png`);
      } catch (err) {
        console.error(`    Error capturing ${name}: ${err.message}`);
      } finally {
        await page.close();
      }
    }

    await context.close();
  }

  await browser.close();
  console.log('\nAll screenshots captured!');
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
