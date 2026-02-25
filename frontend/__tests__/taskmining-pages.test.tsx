/**
 * Unit tests for task mining admin page utilities and components.
 *
 * Tests exported utility functions from each page without rendering full pages
 * (since pages depend on API calls that require deeper mocking).
 */

import { render, screen } from "@testing-library/react";

// -- Agent Management utilities (#216) ----------------------------------------

describe("AgentStatusBadge", () => {
  // We import after describe to ensure module mocks are set up
  let AgentStatusBadge: React.ComponentType<{ status: string }>;
  let formatTimeAgo: (dateStr: string | null) => string;

  beforeAll(async () => {
    // Dynamic import to avoid issues with page-level hooks
    const mod = await import("@/app/admin/task-mining/agents/page");
    AgentStatusBadge = mod.AgentStatusBadge;
    formatTimeAgo = mod.formatTimeAgo;
  });

  it("renders Pending badge for pending_approval", () => {
    render(<AgentStatusBadge status="pending_approval" />);
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("renders Approved badge for approved", () => {
    render(<AgentStatusBadge status="approved" />);
    expect(screen.getByText("Approved")).toBeInTheDocument();
  });

  it("renders Revoked badge for revoked", () => {
    render(<AgentStatusBadge status="revoked" />);
    expect(screen.getByText("Revoked")).toBeInTheDocument();
  });

  it("renders Consent Revoked badge", () => {
    render(<AgentStatusBadge status="consent_revoked" />);
    expect(screen.getByText("Consent Revoked")).toBeInTheDocument();
  });

  it("renders raw status for unknown values", () => {
    render(<AgentStatusBadge status="unknown_status" />);
    expect(screen.getByText("unknown_status")).toBeInTheDocument();
  });
});

describe("formatTimeAgo", () => {
  let formatTimeAgo: (dateStr: string | null) => string;

  beforeAll(async () => {
    const mod = await import("@/app/admin/task-mining/agents/page");
    formatTimeAgo = mod.formatTimeAgo;
  });

  it('returns "Never" for null', () => {
    expect(formatTimeAgo(null)).toBe("Never");
  });

  it('returns "Just now" for recent timestamps', () => {
    const now = new Date().toISOString();
    expect(formatTimeAgo(now)).toBe("Just now");
  });

  it("returns minutes for timestamps within an hour", () => {
    const thirtyMinAgo = new Date(Date.now() - 30 * 60000).toISOString();
    expect(formatTimeAgo(thirtyMinAgo)).toBe("30m ago");
  });

  it("returns hours for timestamps within a day", () => {
    const fiveHoursAgo = new Date(Date.now() - 5 * 3600000).toISOString();
    expect(formatTimeAgo(fiveHoursAgo)).toBe("5h ago");
  });

  it("returns days for older timestamps", () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 86400000).toISOString();
    expect(formatTimeAgo(threeDaysAgo)).toBe("3d ago");
  });
});

// -- Capture Policy utilities (#217) ------------------------------------------

describe("isValidBundleId", () => {
  let isValidBundleId: (id: string) => boolean;

  beforeAll(async () => {
    const mod = await import("@/app/admin/task-mining/policy/page");
    isValidBundleId = mod.isValidBundleId;
  });

  it("accepts valid reverse-domain bundle IDs", () => {
    expect(isValidBundleId("com.apple.Safari")).toBe(true);
    expect(isValidBundleId("com.salesforce.Salesforce")).toBe(true);
    expect(isValidBundleId("com.1password.1password")).toBe(true);
    expect(isValidBundleId("org.mozilla.firefox")).toBe(true);
  });

  it("rejects single segment", () => {
    expect(isValidBundleId("Safari")).toBe(false);
  });

  it("rejects empty string", () => {
    expect(isValidBundleId("")).toBe(false);
  });

  it("rejects strings starting with a number", () => {
    expect(isValidBundleId("123.apple.Safari")).toBe(false);
  });

  it("rejects strings with spaces", () => {
    expect(isValidBundleId("com.apple.My App")).toBe(false);
  });
});

// -- Dashboard utilities (#218) -----------------------------------------------

describe("getAgentHealth", () => {
  let getAgentHealth: (lastHeartbeat: string | null) => string;
  let formatDuration: (seconds: number) => string;

  beforeAll(async () => {
    const mod = await import("@/app/admin/task-mining/dashboard/page");
    getAgentHealth = mod.getAgentHealth;
    formatDuration = mod.formatDuration;
  });

  it('returns "critical" for null heartbeat', () => {
    expect(getAgentHealth(null)).toBe("critical");
  });

  it('returns "healthy" for recent heartbeat', () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60000).toISOString();
    expect(getAgentHealth(fiveMinAgo)).toBe("healthy");
  });

  it('returns "warning" for 15-60 minute old heartbeat', () => {
    const twentyMinAgo = new Date(Date.now() - 20 * 60000).toISOString();
    expect(getAgentHealth(twentyMinAgo)).toBe("warning");
  });

  it('returns "critical" for >60 minute old heartbeat', () => {
    const twoHoursAgo = new Date(Date.now() - 120 * 60000).toISOString();
    expect(getAgentHealth(twoHoursAgo)).toBe("critical");
  });
});

describe("formatDuration", () => {
  let formatDuration: (seconds: number) => string;

  beforeAll(async () => {
    const mod = await import("@/app/admin/task-mining/dashboard/page");
    formatDuration = mod.formatDuration;
  });

  it("formats seconds", () => {
    expect(formatDuration(45)).toBe("45s");
  });

  it("formats minutes", () => {
    expect(formatDuration(300)).toBe("5m");
  });

  it("formats hours", () => {
    expect(formatDuration(7200)).toBe("2.0h");
  });
});

// -- Quarantine utilities (#219) ----------------------------------------------

describe("getTimeRemaining", () => {
  let getTimeRemaining: (autoDeleteAt: string) => {
    text: string;
    urgent: boolean;
    expired: boolean;
  };

  beforeAll(async () => {
    const mod = await import("@/app/admin/task-mining/quarantine/page");
    getTimeRemaining = mod.getTimeRemaining;
  });

  it("marks past dates as expired", () => {
    const past = new Date(Date.now() - 10000).toISOString();
    const result = getTimeRemaining(past);
    expect(result.expired).toBe(true);
    expect(result.text).toBe("Expired");
  });

  it("marks < 2 hours as urgent", () => {
    const oneHourOut = new Date(Date.now() + 60 * 60000).toISOString();
    const result = getTimeRemaining(oneHourOut);
    expect(result.urgent).toBe(true);
    expect(result.expired).toBe(false);
  });

  it("marks > 2 hours as not urgent", () => {
    const fiveHoursOut = new Date(Date.now() + 5 * 3600000).toISOString();
    const result = getTimeRemaining(fiveHoursOut);
    expect(result.urgent).toBe(false);
    expect(result.expired).toBe(false);
  });

  it("shows days for far future", () => {
    const threeDaysOut = new Date(Date.now() + 3 * 86400000).toISOString();
    const result = getTimeRemaining(threeDaysOut);
    expect(result.text).toContain("d remaining");
  });
});
