/**
 * KMFlow Application Walkthrough — Automated Screenshot Capture
 *
 * Logs in as each persona and captures screenshots of every page they can access.
 * Outputs PNG files to docs/presentations/app-walkthrough/
 */

import { chromium } from "playwright";
import { mkdirSync, existsSync } from "fs";
import { join } from "path";

const BASE_URL = "http://localhost:3000";
const API_URL = "http://localhost:8000";
const OUTPUT_DIR = join(
  import.meta.dirname,
  "..",
  "docs",
  "presentations",
  "app-walkthrough"
);

// Demo engagement ID from seed data
const ENG_ID = "1db9aa11-c73b-5867-82a3-864dd695cf23";

// Personas and their accessible pages
const PERSONAS = [
  {
    name: "Platform Admin",
    email: "admin@acme-demo.com",
    slug: "admin",
    pages: [
      { path: "/", title: "Home Dashboard" },
      { path: `/dashboard/${ENG_ID}`, title: "Engagement Dashboard" },
      { path: "/evidence", title: "Evidence Upload" },
      { path: `/graph/${ENG_ID}`, title: "Knowledge Graph" },
      { path: "/lineage", title: "Data Lineage" },
      { path: `/tom/${ENG_ID}`, title: "TOM Alignment" },
      { path: "/conformance", title: "Conformance Checking" },
      { path: "/processes", title: "Process Library" },
      { path: "/monitoring", title: "Monitoring Dashboard" },
      { path: `/roadmap/${ENG_ID}`, title: "Engagement Roadmap" },
      { path: "/simulations", title: "Simulations" },
      { path: "/governance", title: "Governance" },
      { path: "/reports", title: "Reports" },
      { path: "/analytics", title: "Analytics" },
      { path: "/integrations", title: "Connectors" },
      { path: "/shelf-requests", title: "Shelf Requests" },
      { path: "/patterns", title: "Pattern Library" },
      { path: "/copilot", title: "AI Copilot" },
      { path: "/admin", title: "Admin Panel" },
      { path: "/admin/task-mining/agents", title: "Task Mining Agents" },
      { path: "/admin/task-mining/policy", title: "Task Mining Policy" },
      { path: "/admin/task-mining/dashboard", title: "Task Mining Dashboard" },
      { path: "/admin/task-mining/quarantine", title: "Task Mining Quarantine" },
    ],
  },
  {
    name: "Engagement Lead",
    email: "lead@acme-demo.com",
    slug: "lead",
    pages: [
      { path: "/", title: "Home Dashboard" },
      { path: `/dashboard/${ENG_ID}`, title: "Engagement Dashboard" },
      { path: "/evidence", title: "Evidence Upload" },
      { path: `/graph/${ENG_ID}`, title: "Knowledge Graph" },
      { path: "/lineage", title: "Data Lineage" },
      { path: `/tom/${ENG_ID}`, title: "TOM Alignment" },
      { path: "/conformance", title: "Conformance Checking" },
      { path: "/processes", title: "Process Library" },
      { path: "/monitoring", title: "Monitoring Dashboard" },
      { path: `/roadmap/${ENG_ID}`, title: "Engagement Roadmap" },
      { path: "/simulations", title: "Simulations" },
      { path: "/governance", title: "Governance" },
      { path: "/reports", title: "Reports" },
      { path: "/analytics", title: "Analytics" },
      { path: "/shelf-requests", title: "Shelf Requests" },
      { path: "/copilot", title: "AI Copilot" },
    ],
  },
  {
    name: "Process Analyst",
    email: "analyst@acme-demo.com",
    slug: "analyst",
    pages: [
      { path: "/", title: "Home Dashboard" },
      { path: `/dashboard/${ENG_ID}`, title: "Engagement Dashboard" },
      { path: "/evidence", title: "Evidence Upload" },
      { path: `/graph/${ENG_ID}`, title: "Knowledge Graph" },
      { path: "/lineage", title: "Data Lineage" },
      { path: `/tom/${ENG_ID}`, title: "TOM Alignment" },
      { path: "/conformance", title: "Conformance Checking" },
      { path: "/processes", title: "Process Library" },
      { path: "/monitoring", title: "Monitoring Dashboard" },
      { path: "/simulations", title: "Simulations" },
      { path: "/patterns", title: "Pattern Library" },
      { path: "/copilot", title: "AI Copilot" },
    ],
  },
  {
    name: "Client Viewer",
    email: "viewer@acme-demo.com",
    slug: "viewer",
    pages: [
      { path: "/", title: "Home Dashboard" },
      { path: `/dashboard/${ENG_ID}`, title: "Engagement Dashboard (Restricted)" },
      { path: "/portal", title: "Client Portal Home" },
      { path: `/portal/${ENG_ID}`, title: "Client Portal Overview" },
      { path: `/portal/${ENG_ID}/evidence`, title: "Evidence Status" },
      { path: `/portal/${ENG_ID}/findings`, title: "Findings" },
      { path: `/portal/${ENG_ID}/process`, title: "Process Models" },
      { path: `/portal/${ENG_ID}/upload`, title: "Client Evidence Upload" },
    ],
  },
];

async function login(page, email) {
  // Call the API directly to get auth cookies
  const resp = await page.request.post(`${API_URL}/api/v1/auth/login`, {
    data: { email, password: "demo" },
    headers: { "Content-Type": "application/json" },
  });

  if (!resp.ok()) {
    console.warn(`  Login API returned ${resp.status()} for ${email}`);
  }

  // Navigate to the app first to establish the domain (with retry)
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 15000 });
      break;
    } catch (e) {
      console.warn(`  Login nav attempt ${attempt + 1} failed: ${e.message}`);
      if (attempt < 2) await page.waitForTimeout(3000);
      else throw e;
    }
  }
  await page.waitForTimeout(1000);
}

async function captureScreenshot(page, persona, pageInfo, index) {
  const url = `${BASE_URL}${pageInfo.path}`;
  const filename = `${String(index).padStart(2, "0")}-${persona.slug}-${pageInfo.path.replace(/\//g, "-").replace(/^-/, "") || "home"}.png`;
  const filepath = join(OUTPUT_DIR, filename);

  console.log(`  [${persona.slug}] ${pageInfo.title}: ${pageInfo.path}`);

  try {
    await page.goto(url, { waitUntil: "networkidle", timeout: 15000 });
  } catch {
    // networkidle can timeout; try domcontentloaded fallback
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 10000 });
    } catch (e2) {
      console.warn(`    WARN: Could not load ${url}: ${e2.message}`);
      return null;
    }
  }

  // Wait for content to render
  await page.waitForTimeout(1500);

  // Scroll to top
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(300);

  await page.screenshot({ path: filepath, fullPage: false });

  return { filename, title: pageInfo.title, path: pageInfo.path, persona: persona.name };
}

async function main() {
  mkdirSync(OUTPUT_DIR, { recursive: true });

  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox"],
  });

  const allScreenshots = [];
  let globalIndex = 1;

  for (const persona of PERSONAS) {
    console.log(`\n--- ${persona.name} (${persona.email}) ---`);

    // Fresh context per persona (clean cookies)
    const context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      ignoreHTTPSErrors: true,
    });
    const page = await context.newPage();

    // Login
    await login(page, persona.email);

    // Capture each page
    for (const pageInfo of persona.pages) {
      const result = await captureScreenshot(page, persona, pageInfo, globalIndex);
      if (result) {
        allScreenshots.push(result);
        globalIndex++;
      }
    }

    await context.close();
    // Brief pause between personas to let the frontend recover
    await new Promise((r) => setTimeout(r, 2000));
  }

  await browser.close();

  // Write manifest
  const manifest = {
    generated: new Date().toISOString(),
    personas: PERSONAS.map((p) => ({ name: p.name, email: p.email, slug: p.slug, pageCount: p.pages.length })),
    screenshots: allScreenshots,
  };
  const { writeFileSync } = await import("fs");
  writeFileSync(join(OUTPUT_DIR, "manifest.json"), JSON.stringify(manifest, null, 2));

  console.log(`\nDone! ${allScreenshots.length} screenshots saved to ${OUTPUT_DIR}`);
  console.log("Manifest written to manifest.json");
}

main().catch((e) => {
  console.error("Fatal error:", e);
  process.exit(1);
});
