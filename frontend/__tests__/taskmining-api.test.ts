/**
 * Unit tests for the task mining API client module.
 *
 * Story #216-#219 — Epic #215 (Admin Dashboard).
 */

const mockFetch = jest.fn();
global.fetch = mockFetch;

import {
  fetchAgents,
  approveAgent,
  revokeAgent,
  fetchQuarantine,
  quarantineAction,
  fetchDashboardStats,
  fetchAppUsage,
  fetchCaptureConfig,
  updateCaptureConfig,
} from "@/lib/api/taskmining";

beforeEach(() => {
  mockFetch.mockClear();
});

function okResponse(data: unknown) {
  return { ok: true, json: () => Promise.resolve(data) };
}

function errorResponse(status: number, detail: string) {
  return {
    ok: false,
    status,
    json: () => Promise.resolve({ detail, status_code: status }),
  };
}

describe("fetchAgents", () => {
  it("calls GET /api/v1/taskmining/agents without params", async () => {
    mockFetch.mockResolvedValue(okResponse({ agents: [], total: 0 }));
    const result = await fetchAgents();
    expect(result).toEqual({ agents: [], total: 0 });
    expect(mockFetch.mock.calls[0][0]).toContain("/api/v1/taskmining/agents");
    expect(mockFetch.mock.calls[0][0]).not.toContain("engagement_id");
  });

  it("includes engagement_id query param when provided", async () => {
    mockFetch.mockResolvedValue(okResponse({ agents: [], total: 0 }));
    await fetchAgents("abc-123");
    expect(mockFetch.mock.calls[0][0]).toContain("engagement_id=abc-123");
  });
});

describe("approveAgent", () => {
  it("POSTs to approve endpoint", async () => {
    mockFetch.mockResolvedValue(okResponse({ id: "a1", status: "approved" }));
    const result = await approveAgent("a1");
    expect(result.status).toBe("approved");
    expect(mockFetch.mock.calls[0][0]).toContain("/agents/a1/approve");
    expect(mockFetch.mock.calls[0][1].method).toBe("POST");
  });
});

describe("revokeAgent", () => {
  it("POSTs revoke action", async () => {
    mockFetch.mockResolvedValue(okResponse({ id: "a1", status: "revoked" }));
    const result = await revokeAgent("a1");
    expect(result.status).toBe("revoked");
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.action).toBe("revoke");
  });
});

describe("fetchQuarantine", () => {
  it("calls GET /api/v1/taskmining/quarantine", async () => {
    mockFetch.mockResolvedValue(okResponse({ items: [], total: 0 }));
    const result = await fetchQuarantine();
    expect(result).toEqual({ items: [], total: 0 });
  });
});

describe("quarantineAction", () => {
  it("POSTs delete action", async () => {
    mockFetch.mockResolvedValue(okResponse({ status: "deleted" }));
    const result = await quarantineAction("q1", "delete");
    expect(result.status).toBe("deleted");
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.action).toBe("delete");
  });

  it("POSTs release action with reason", async () => {
    mockFetch.mockResolvedValue(okResponse({ status: "released" }));
    await quarantineAction("q1", "release", "False positive — date format");
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.action).toBe("release");
    expect(body.reason).toBe("False positive — date format");
  });
});

describe("fetchDashboardStats", () => {
  it("returns stats object", async () => {
    const stats = {
      active_agents: 3,
      events_today: 1500,
      actions_today: 200,
      quarantine_pending: 2,
      total_sessions: 45,
    };
    mockFetch.mockResolvedValue(okResponse(stats));
    const result = await fetchDashboardStats();
    expect(result.active_agents).toBe(3);
    expect(result.events_today).toBe(1500);
  });
});

describe("fetchAppUsage", () => {
  it("includes engagement_id and days params", async () => {
    mockFetch.mockResolvedValue(okResponse([]));
    await fetchAppUsage("eng-1", 30);
    expect(mockFetch.mock.calls[0][0]).toContain("engagement_id=eng-1");
    expect(mockFetch.mock.calls[0][0]).toContain("days=30");
  });
});

describe("fetchCaptureConfig", () => {
  it("returns config object", async () => {
    const config = {
      engagement_id: "eng-1",
      allowed_apps: ["com.test.App"],
      blocked_apps: [],
      capture_granularity: "full",
      keystroke_mode: "action_level",
      screenshot_enabled: false,
      pii_patterns_version: "1.2.0",
    };
    mockFetch.mockResolvedValue(okResponse(config));
    const result = await fetchCaptureConfig("eng-1");
    expect(result.allowed_apps).toEqual(["com.test.App"]);
  });
});

describe("updateCaptureConfig", () => {
  it("PUTs updated config", async () => {
    mockFetch.mockResolvedValue(
      okResponse({ engagement_id: "eng-1", keystroke_mode: "content_level" }),
    );
    await updateCaptureConfig("eng-1", { keystroke_mode: "content_level" });
    expect(mockFetch.mock.calls[0][1].method).toBe("PUT");
    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.engagement_id).toBe("eng-1");
    expect(body.keystroke_mode).toBe("content_level");
  });
});

describe("error handling", () => {
  it("throws on non-ok response", async () => {
    mockFetch.mockResolvedValue(errorResponse(403, "Forbidden"));
    await expect(fetchAgents()).rejects.toThrow("Forbidden");
  });
});
