import { chromium, FullConfig } from "@playwright/test";
import { execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";

const BACKEND_URL =
  process.env.E2E_BACKEND_URL || "http://localhost:8000";

const ROLES = [
  { role: "admin", email: "admin@acme-demo.com", password: "demo" },
  { role: "lead", email: "lead@acme-demo.com", password: "demo" },
  { role: "analyst", email: "analyst@acme-demo.com", password: "demo" },
  { role: "viewer", email: "viewer@acme-demo.com", password: "demo" },
];

function normalizeSameSite(value?: string): "Strict" | "Lax" | "None" {
  if (!value) return "Lax";
  const lower = value.toLowerCase();
  if (lower === "strict") return "Strict";
  if (lower === "none") return "None";
  return "Lax";
}

async function globalSetup(_config: FullConfig): Promise<void> {
  // Seed test data unless explicitly skipped
  if (process.env.E2E_SKIP_SEED !== "true") {
    const projectRoot = path.resolve(__dirname, "../..");
    console.log("[E2E Setup] Running seed_e2e...");
    try {
      execSync("python -m scripts.seed_e2e", {
        cwd: projectRoot,
        stdio: "inherit",
      });
      console.log("[E2E Setup] Seeding complete.");
    } catch (err) {
      console.error("[E2E Setup] Seeding failed:", err);
      throw err;
    }
  } else {
    console.log("[E2E Setup] E2E_SKIP_SEED=true — skipping seed.");
  }

  // Ensure .auth directory exists
  const authDir = path.resolve(__dirname, ".auth");
  fs.mkdirSync(authDir, { recursive: true });

  const browser = await chromium.launch();

  for (const { role, email, password } of ROLES) {
    console.log(`[E2E Setup] Logging in as ${role} (${email})...`);

    // POST to backend login endpoint, retry on rate limiting
    let response: Response | undefined;
    for (let attempt = 0; attempt < 5; attempt++) {
      response = await fetch(`${BACKEND_URL}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
        redirect: "manual",
      });
      if (response.status !== 429) break;
      const backoff = (attempt + 1) * 3000;
      console.log(`[E2E Setup] Rate limited for ${role}, retrying in ${backoff}ms...`);
      await new Promise((r) => setTimeout(r, backoff));
    }

    if (!response || !response.ok) {
      throw new Error(
        `[E2E Setup] Login failed for ${role}: ${response?.status} ${response?.statusText}`
      );
    }

    // Extract Set-Cookie headers
    const setCookieHeaders = response.headers.getSetCookie
      ? response.headers.getSetCookie()
      : [response.headers.get("set-cookie") ?? ""].filter(Boolean);

    // Parse cookies into Playwright cookie format
    const cookies = setCookieHeaders.flatMap((header) => {
      const parts = header.split(";").map((p) => p.trim());
      const [nameValue, ...attrs] = parts;
      const eqIdx = nameValue.indexOf("=");
      if (eqIdx === -1) return [];

      const name = nameValue.slice(0, eqIdx);
      const value = nameValue.slice(eqIdx + 1);

      const attrMap: Record<string, string> = {};
      for (const attr of attrs) {
        const [k, v] = attr.split("=").map((s) => s.trim());
        attrMap[k.toLowerCase()] = v ?? "";
      }

      return [
        {
          name,
          value,
          domain: new URL(BACKEND_URL).hostname,
          path: attrMap["path"] || "/",
          httpOnly: "httponly" in attrMap || attrMap["httponly"] !== undefined,
          secure: "secure" in attrMap || attrMap["secure"] !== undefined,
          sameSite: normalizeSameSite(attrMap["samesite"]),
        },
      ];
    });

    // Create a browser context, add cookies, and save storage state
    const context = await browser.newContext();
    await context.addCookies(cookies);

    const storageStatePath = path.join(authDir, `${role}.json`);
    await context.storageState({ path: storageStatePath });
    await context.close();

    console.log(`[E2E Setup] Saved storage state for ${role} to ${storageStatePath}`);

    // Delay between logins to avoid rate limiting
    await new Promise((r) => setTimeout(r, 1500));
  }

  await browser.close();
  console.log("[E2E Setup] All roles authenticated.");
}

export default globalSetup;
