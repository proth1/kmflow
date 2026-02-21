/**
 * Tests for the API client auth strategy.
 *
 * After the HttpOnly JWT cookie migration (PR #177), browser auth is handled
 * exclusively via the `kmflow_access` HttpOnly cookie — the client sets
 * `credentials: "include"` on every fetch, and `authHeaders()` no longer
 * injects an Authorization header from localStorage.
 */

// Mock fetch globally before importing the module
const mockFetch = jest.fn();
global.fetch = mockFetch;

import { fetchHealth, apiPost } from "@/lib/api";

describe("API client auth", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    localStorage.clear();
  });

  it("uses credentials: include for cookie-based auth", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        status: "healthy",
        services: { postgres: "up", neo4j: "up", redis: "up" },
        version: "1.0.0",
      }),
    });

    await fetchHealth();

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [, options] = mockFetch.mock.calls[0];
    expect(options.credentials).toBe("include");
  });

  it("does not inject Authorization header from localStorage", async () => {
    localStorage.setItem("kmflow_token", "test-jwt-token");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        status: "healthy",
        services: { postgres: "up", neo4j: "up", redis: "up" },
        version: "1.0.0",
      }),
    });

    await fetchHealth();

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers["Authorization"]).toBeUndefined();
  });

  it("does not throw when token is absent", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        status: "healthy",
        services: { postgres: "up", neo4j: "up", redis: "up" },
        version: "1.0.0",
      }),
    });

    await expect(fetchHealth()).resolves.toBeDefined();
  });

  it("includes Content-Type header and credentials on POST", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "1" }),
    });

    await apiPost("/api/v1/test", { data: true });

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers["Content-Type"]).toBe("application/json");
    expect(options.credentials).toBe("include");
    // No Authorization header injected — auth is cookie-based
    expect(options.headers["Authorization"]).toBeUndefined();
  });
});
