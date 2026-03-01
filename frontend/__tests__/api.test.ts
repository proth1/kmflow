/**
 * Tests for the API client module.
 */

import { fetchHealth, apiGet, apiPost } from "@/lib/api";

// Mock global fetch
const mockFetch = jest.fn();
global.fetch = mockFetch;

describe("API Client", () => {
  beforeEach(() => {
    mockFetch.mockClear();
  });

  describe("fetchHealth", () => {
    it("should return health data on success", async () => {
      const mockHealth = {
        status: "healthy",
        services: { postgres: "up", neo4j: "up", redis: "up" },
        version: "0.1.0",
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockHealth),
      });

      const result = await fetchHealth();
      expect(result).toEqual(mockHealth);
      expect(mockFetch).toHaveBeenCalledWith(
        "/health",
        expect.objectContaining({ cache: "no-store" })
      );
    });

    it("should throw on non-OK response", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      await expect(fetchHealth()).rejects.toThrow("Health check failed: 500");
    });
  });

  describe("apiGet", () => {
    it("should fetch from the correct URL", async () => {
      const mockData = { items: [], total: 0 };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

      const result = await apiGet("/api/v1/engagements");
      expect(result).toEqual(mockData);
      // GET requests should NOT include Content-Type header (CQ-3 fix)
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/v1/engagements",
        expect.objectContaining({ signal: undefined })
      );
    });

    it("should throw with error detail on failure", async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: () =>
          Promise.resolve({ detail: "Not found", status_code: 404 }),
      });

      await expect(apiGet("/api/v1/nothing")).rejects.toThrow("Not found");
    });
  });

  describe("apiPost", () => {
    it("should send POST with JSON body", async () => {
      const mockResponse = { id: "123", name: "Test" };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResponse),
      });

      const result = await apiPost("/api/v1/engagements", {
        name: "Test",
      });

      expect(result).toEqual(mockResponse);
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/v1/engagements",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ name: "Test" }),
        })
      );
    });
  });
});
