/**
 * Unit tests for the API client functions.
 */

// Mock fetch globally
const mockFetch = jest.fn();
global.fetch = mockFetch;

// Must import after setting up mock
import {
  fetchHealth,
  apiGet,
  apiPost,
  apiPut,
  apiDelete,
  uploadPortalEvidence,
} from "../api";

beforeEach(() => {
  mockFetch.mockClear();
});

describe("apiGet", () => {
  it("makes a GET request without Content-Type header", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: "test" }),
    });

    await apiGet("/test");

    const callArgs = mockFetch.mock.calls[0];
    expect(callArgs[1]).toBeDefined();
    // Should NOT have Content-Type header
    expect(callArgs[1].headers).toBeUndefined();
  });

  it("passes AbortSignal when provided", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: "test" }),
    });

    const controller = new AbortController();
    await apiGet("/test", controller.signal);

    expect(mockFetch.mock.calls[0][1].signal).toBe(controller.signal);
  });

  it("handles non-JSON error responses gracefully", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error("not json")),
    });

    await expect(apiGet("/test")).rejects.toThrow("Request failed: 500");
  });
});

describe("apiPost", () => {
  it("includes Content-Type header for POST", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: "test" }),
    });

    await apiPost("/test", { key: "value" });

    const callArgs = mockFetch.mock.calls[0];
    expect(callArgs[1].headers["Content-Type"]).toBe("application/json");
    expect(callArgs[1].method).toBe("POST");
  });

  it("passes AbortSignal when provided", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ data: "test" }),
    });

    const controller = new AbortController();
    await apiPost("/test", {}, controller.signal);

    expect(mockFetch.mock.calls[0][1].signal).toBe(controller.signal);
  });

  it("handles non-JSON error responses gracefully", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 502,
      json: () => Promise.reject(new Error("bad gateway html")),
    });

    await expect(apiPost("/test", {})).rejects.toThrow("Request failed: 502");
  });
});

describe("apiPut", () => {
  it("sends PUT with Content-Type and signal", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ updated: true }),
    });

    const controller = new AbortController();
    await apiPut("/resource/1", { name: "updated" }, controller.signal);

    const callArgs = mockFetch.mock.calls[0];
    expect(callArgs[1].method).toBe("PUT");
    expect(callArgs[1].signal).toBe(controller.signal);
  });
});

describe("apiDelete", () => {
  it("makes DELETE request without Content-Type header", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
    });

    await apiDelete("/resource/1");

    const callArgs = mockFetch.mock.calls[0];
    expect(callArgs[1].method).toBe("DELETE");
    // Should NOT have Content-Type header for DELETE
    expect(callArgs[1].headers).toBeUndefined();
  });

  it("passes AbortSignal when provided", async () => {
    mockFetch.mockResolvedValue({ ok: true });

    const controller = new AbortController();
    await apiDelete("/resource/1", controller.signal);

    expect(mockFetch.mock.calls[0][1].signal).toBe(controller.signal);
  });
});

describe("fetchHealth", () => {
  it("returns health data on success", async () => {
    const healthData = {
      status: "healthy",
      services: { postgres: "up", neo4j: "up", redis: "up" },
      version: "0.1.0",
    };
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(healthData),
    });

    const result = await fetchHealth();
    expect(result).toEqual(healthData);
    expect(mockFetch.mock.calls[0][0]).toContain("/health");
  });

  it("throws on non-ok response", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 503,
    });

    await expect(fetchHealth()).rejects.toThrow("Health check failed: 503");
  });
});

describe("uploadPortalEvidence", () => {
  it("sends FormData with file", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: "ev-1" }),
    });

    const file = new File(["content"], "test.pdf", { type: "application/pdf" });
    const result = await uploadPortalEvidence("eng-123", file);

    expect(result).toEqual({ id: "ev-1" });
    const callArgs = mockFetch.mock.calls[0];
    expect(callArgs[1].method).toBe("POST");
    expect(callArgs[1].body).toBeInstanceOf(FormData);
  });

  it("handles non-JSON error responses", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 413,
      json: () => Promise.reject(new Error("not json")),
    });

    const file = new File(["content"], "large.pdf");
    await expect(uploadPortalEvidence("eng-123", file)).rejects.toThrow("Upload failed");
  });
});
