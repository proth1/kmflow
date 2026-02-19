/**
 * Tests for authHeaders() and getAuthToken() in the API client.
 *
 * Since authHeaders and getAuthToken are not exported, we test them
 * indirectly through the exported fetch functions that use them.
 * We also test the module-level behavior via localStorage.
 */

// Mock fetch globally before importing the module
const mockFetch = jest.fn();
global.fetch = mockFetch;

// We need to test authHeaders behavior via the exported functions
import { fetchHealth, apiPost } from "@/lib/api";

describe("authHeaders via fetchHealth", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    localStorage.clear();
  });

  it("includes Authorization header when token is in localStorage", async () => {
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
    expect(options.headers["Authorization"]).toBe("Bearer test-jwt-token");
  });

  it("omits Authorization header when no token in localStorage", async () => {
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

  it("includes extra headers alongside Authorization", async () => {
    localStorage.setItem("kmflow_token", "my-token");
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "1" }),
    });

    await apiPost("/api/v1/test", { data: true });

    const [, options] = mockFetch.mock.calls[0];
    expect(options.headers["Authorization"]).toBe("Bearer my-token");
    expect(options.headers["Content-Type"]).toBe("application/json");
  });
});
