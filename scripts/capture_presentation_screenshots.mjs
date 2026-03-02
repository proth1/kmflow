/**
 * Capture presentation screenshots with seeded demo data.
 *
 * Navigates to 4 task-mining/conformance pages and captures at 2 viewport
 * sizes:  1440x900  (app-walkthrough)  and  1280x800  (narrative sidebar).
 *
 * Prerequisites:
 *   1. `docker compose up -d` (backend + frontend on port 3002)
 *   2. `python -m scripts.seed_demo --reset` (populate demo data)
 *
 * Usage:
 *   node scripts/capture_presentation_screenshots.mjs
 *   node scripts/capture_presentation_screenshots.mjs --base-url http://localhost:3000
 */

import { chromium } from "playwright";
import { mkdirSync, copyFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");

const BASE_URL = process.argv.includes("--base-url")
  ? process.argv[process.argv.indexOf("--base-url") + 1]
  : "http://localhost:3002";

const SCREENSHOT_DIR = resolve(ROOT, "docs/presentations/screenshots");
const WALKTHROUGH_DIR = resolve(ROOT, "docs/presentations/app-walkthrough");

mkdirSync(SCREENSHOT_DIR, { recursive: true });
mkdirSync(WALKTHROUGH_DIR, { recursive: true });

// Engagement ID from seed_demo.py deterministic UUID
const ENG_ID = "1db9aa11-c73b-5867-82a3-864dd695cf23";

// Pages to capture — path relative to BASE_URL
const PAGES = [
  {
    path: "/admin/task-mining/agents",
    screenshotName: "tm-agents",
    walkthroughName: "20-admin-admin-task-mining-agents",
    waitForSelector: "table tbody tr",
  },
  {
    path: "/admin/task-mining/dashboard",
    screenshotName: "tm-dashboard",
    walkthroughName: "22-admin-admin-task-mining-dashboard",
    waitForSelector: "[class*='CardContent']",
    patchWsBadge: true,
  },
  {
    path: "/admin/task-mining/quarantine",
    screenshotName: "tm-quarantine",
    walkthroughName: "23-admin-admin-task-mining-quarantine",
    waitForSelector: "table tbody tr",
  },
  {
    path: "/conformance",
    screenshotName: null, // no narrative screenshot
    walkthroughName: "07-admin-conformance",
    waitForSelector: "table tbody tr",
    // Copy across persona slots
    copyTo: ["30-lead-conformance", "46-analyst-conformance"],
  },
];

async function patchWebSocketBadge(page) {
  // Force the WS connection badge to show "Live" (green) instead of
  // "Reconnecting..." for clean screenshots.
  await page.evaluate(() => {
    const badges = document.querySelectorAll("[class*='Badge']");
    for (const badge of badges) {
      if (badge.textContent?.includes("Reconnecting")) {
        badge.className = badge.className
          .replace(/bg-yellow-50/g, "bg-green-50")
          .replace(/text-yellow-700/g, "text-green-700")
          .replace(/border-yellow-200/g, "border-green-200");
        // Find the icon + text and swap
        const svg = badge.querySelector("svg");
        if (svg) {
          // Keep the SVG but change sibling text
          const textNode = [...badge.childNodes].find(
            (n) => n.nodeType === 3 || (n.nodeType === 1 && n.tagName !== "svg")
          );
          // Replace entire innerHTML with Live state
          badge.innerHTML = "";
          const icon = document.createElementNS(
            "http://www.w3.org/2000/svg",
            "svg"
          );
          icon.setAttribute("class", "h-3 w-3 mr-1");
          icon.setAttribute("viewBox", "0 0 24 24");
          icon.setAttribute("fill", "none");
          icon.setAttribute("stroke", "currentColor");
          icon.setAttribute("stroke-width", "2");
          const path = document.createElementNS(
            "http://www.w3.org/2000/svg",
            "path"
          );
          // Wifi icon path (simplified)
          path.setAttribute(
            "d",
            "M5 12.55a11 11 0 0 1 14.08 0M1.42 9a16 16 0 0 1 21.16 0M8.53 16.11a6 6 0 0 1 6.95 0M12 20h.01"
          );
          path.setAttribute("stroke-linecap", "round");
          path.setAttribute("stroke-linejoin", "round");
          icon.appendChild(path);
          badge.appendChild(icon);
          badge.appendChild(document.createTextNode(" Live"));
        }
      }
    }
  });
}

async function main() {
  console.log(`Capturing screenshots from ${BASE_URL}...\n`);

  const browser = await chromium.launch({ headless: true });

  try {
    // ── Walkthrough viewport (1440x900) ──
    const walkthroughCtx = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 2,
    });
    const wPage = await walkthroughCtx.newPage();

    for (const spec of PAGES) {
      const url = `${BASE_URL}${spec.path}`;
      console.log(`  [walkthrough] ${url}`);
      await wPage.goto(url, { waitUntil: "networkidle", timeout: 30000 });

      // Wait for data to appear
      try {
        await wPage.waitForSelector(spec.waitForSelector, { timeout: 10000 });
      } catch {
        console.warn(
          `    ⚠ selector "${spec.waitForSelector}" not found — capturing anyway`
        );
      }

      // Settle any animations
      await wPage.waitForTimeout(500);

      if (spec.patchWsBadge) {
        await patchWebSocketBadge(wPage);
        await wPage.waitForTimeout(200);
      }

      const outPath = resolve(
        WALKTHROUGH_DIR,
        `${spec.walkthroughName}.png`
      );
      await wPage.screenshot({ path: outPath, fullPage: false });
      console.log(`    → ${outPath}`);

      // Copy to other persona slots if needed
      if (spec.copyTo) {
        for (const alias of spec.copyTo) {
          const dest = resolve(WALKTHROUGH_DIR, `${alias}.png`);
          copyFileSync(outPath, dest);
          console.log(`    → ${dest} (copy)`);
        }
      }
    }

    await walkthroughCtx.close();

    // ── Narrative viewport (1280x800, sidebar collapsed) ──
    const narrativeCtx = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      deviceScaleFactor: 2,
    });
    const nPage = await narrativeCtx.newPage();

    for (const spec of PAGES) {
      if (!spec.screenshotName) continue; // skip pages without narrative screenshot

      const url = `${BASE_URL}${spec.path}`;
      console.log(`  [narrative]   ${url}`);
      await nPage.goto(url, { waitUntil: "networkidle", timeout: 30000 });

      try {
        await nPage.waitForSelector(spec.waitForSelector, { timeout: 10000 });
      } catch {
        console.warn(
          `    ⚠ selector "${spec.waitForSelector}" not found — capturing anyway`
        );
      }

      await nPage.waitForTimeout(500);

      if (spec.patchWsBadge) {
        await patchWebSocketBadge(nPage);
        await nPage.waitForTimeout(200);
      }

      const outPath = resolve(
        SCREENSHOT_DIR,
        `${spec.screenshotName}.png`
      );
      await nPage.screenshot({ path: outPath, fullPage: false });
      console.log(`    → ${outPath}`);
    }

    await narrativeCtx.close();
  } finally {
    await browser.close();
  }

  console.log("\nAll screenshots captured.");
}

main().catch((err) => {
  console.error("Screenshot capture failed:", err);
  process.exit(1);
});
