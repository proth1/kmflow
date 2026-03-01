/**
 * Extended tests for the API client module — Phase 6 additions.
 * Tests domain-specific functions, apiPut, apiDelete, and lineage functions.
 */

import {
  apiPut,
  apiDelete,
  fetchCatalogEntries,
  fetchPolicies,
  fetchGovernanceHealth,
  fetchConnectorTypes,
  fetchConnections,
  testConnection,
  syncConnection,
  fetchShelfRequests,
  fetchMetricDefinitions,
  fetchMetricSummary,
  fetchAnnotations,
  createAnnotation,
  fetchLineageChain,
  fetchLineageRecord,
  fetchPatterns,
  fetchScenarios,
  fetchSimulationResults,
} from "@/lib/api";

const mockFetch = jest.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockClear();
});

function mockOk(data: unknown) {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(data),
  });
}

function mockError(status: number, detail: string) {
  mockFetch.mockResolvedValueOnce({
    ok: false,
    status,
    json: () => Promise.resolve({ detail, status_code: status }),
  });
}

// -- apiPut / apiDelete -------------------------------------------------------

describe("apiPut", () => {
  it("sends PUT with JSON body and returns parsed response", async () => {
    mockOk({ id: "1", name: "Updated" });
    const result = await apiPut("/api/v1/test/1", { name: "Updated" });
    expect(result).toEqual({ id: "1", name: "Updated" });
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/test/1",
      expect.objectContaining({
        method: "PUT",
        body: JSON.stringify({ name: "Updated" }),
      })
    );
  });

  it("throws on error response", async () => {
    mockError(400, "Bad request");
    await expect(apiPut("/api/v1/test/1", {})).rejects.toThrow("Bad request");
  });
});

describe("apiDelete", () => {
  it("sends DELETE request", async () => {
    mockFetch.mockResolvedValueOnce({ ok: true });
    await apiDelete("/api/v1/test/1");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/test/1",
      expect.objectContaining({ method: "DELETE" })
    );
  });

  it("throws on error response", async () => {
    mockError(404, "Not found");
    await expect(apiDelete("/api/v1/test/1")).rejects.toThrow("Not found");
  });
});

// -- Governance ---------------------------------------------------------------

describe("fetchCatalogEntries", () => {
  it("fetches catalog entries without engagement filter", async () => {
    mockOk([{ id: "1", dataset_name: "test" }]);
    const result = await fetchCatalogEntries();
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/governance/catalog",
      expect.any(Object)
    );
    expect(result).toHaveLength(1);
  });

  it("passes engagement_id filter when provided", async () => {
    mockOk([]);
    await fetchCatalogEntries("eng-1");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/governance/catalog?engagement_id=eng-1",
      expect.any(Object)
    );
  });
});

describe("fetchPolicies", () => {
  it("fetches policies", async () => {
    mockOk({ policy_file: "default.yaml", policies: {} });
    const result = await fetchPolicies();
    expect(result.policy_file).toBe("default.yaml");
  });
});

describe("fetchGovernanceHealth", () => {
  it("fetches health for engagement", async () => {
    mockOk({ engagement_id: "e1", total_entries: 5, passing_count: 4, failing_count: 1, compliance_percentage: 80, entries: [] });
    const result = await fetchGovernanceHealth("e1");
    expect(result.compliance_percentage).toBe(80);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/governance/health/e1",
      expect.any(Object)
    );
  });
});

// -- Integrations -------------------------------------------------------------

describe("fetchConnectorTypes", () => {
  it("fetches connector types", async () => {
    mockOk([{ type: "sharepoint", description: "SharePoint" }]);
    const result = await fetchConnectorTypes();
    expect(result).toHaveLength(1);
  });
});

describe("fetchConnections", () => {
  it("fetches connections with optional engagement filter", async () => {
    mockOk({ items: [], total: 0 });
    await fetchConnections("eng-1");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/integrations/connections?engagement_id=eng-1",
      expect.any(Object)
    );
  });
});

describe("testConnection", () => {
  it("posts test request", async () => {
    mockOk({ connection_id: "c1", success: true, message: "OK" });
    const result = await testConnection("c1");
    expect(result.success).toBe(true);
  });
});

describe("syncConnection", () => {
  it("posts sync request", async () => {
    mockOk({ connection_id: "c1", records_synced: 10, errors: [] });
    const result = await syncConnection("c1");
    expect(result.records_synced).toBe(10);
  });
});

// -- Shelf Requests -----------------------------------------------------------

describe("fetchShelfRequests", () => {
  it("fetches shelf requests", async () => {
    mockOk({ items: [], total: 0 });
    const result = await fetchShelfRequests();
    expect(result.total).toBe(0);
  });
});

// -- Metrics ------------------------------------------------------------------

describe("fetchMetricDefinitions", () => {
  it("fetches definitions with optional category", async () => {
    mockOk({ items: [{ id: "m1", name: "Test" }], total: 1 });
    await fetchMetricDefinitions("quality");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/metrics/definitions?category=quality",
      expect.any(Object)
    );
  });
});

describe("fetchMetricSummary", () => {
  it("fetches summary for engagement", async () => {
    mockOk({ engagement_id: "e1", metrics: [], total: 0, on_target_count: 0 });
    const result = await fetchMetricSummary("e1");
    expect(result.engagement_id).toBe("e1");
  });
});

// -- Annotations --------------------------------------------------------------

describe("fetchAnnotations", () => {
  it("fetches annotations with filters", async () => {
    mockOk({ items: [], total: 0 });
    await fetchAnnotations("e1", "gap", "g1");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/annotations?engagement_id=e1&target_type=gap&target_id=g1",
      expect.any(Object)
    );
  });
});

describe("createAnnotation", () => {
  it("posts annotation", async () => {
    mockOk({ id: "a1", engagement_id: "e1", target_type: "gap", target_id: "g1", author_id: "u1", content: "test", created_at: "", updated_at: "" });
    const result = await createAnnotation({
      engagement_id: "e1",
      target_type: "gap",
      target_id: "g1",
      content: "test",
    });
    expect(result.id).toBe("a1");
  });
});

// -- Lineage ------------------------------------------------------------------

describe("fetchLineageChain", () => {
  it("fetches lineage chain for evidence item", async () => {
    mockOk({ evidence_item_id: "ev1", evidence_name: "Doc", source_system: "S3", total_versions: 2, lineage: [] });
    const result = await fetchLineageChain("eng-1", "ev1");
    expect(result.total_versions).toBe(2);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/engagements/eng-1/evidence/ev1/lineage",
      expect.any(Object)
    );
  });
});

describe("fetchLineageRecord", () => {
  it("fetches specific lineage record", async () => {
    mockOk({ id: "lr1", evidence_item_id: "ev1", source_system: "S3", version: 1 });
    const result = await fetchLineageRecord("eng-1", "ev1", "lr1");
    expect(result.id).toBe("lr1");
  });
});

// -- Patterns -----------------------------------------------------------------

describe("fetchPatterns", () => {
  it("fetches patterns with optional category", async () => {
    mockOk({ items: [{ id: "p1", title: "Pattern" }], total: 1 });
    await fetchPatterns("workflow");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/patterns?category=workflow",
      expect.any(Object)
    );
  });
});

// -- Simulations --------------------------------------------------------------

describe("fetchScenarios", () => {
  it("fetches scenarios with optional engagement filter", async () => {
    mockOk({ items: [], total: 0 });
    await fetchScenarios("eng-1");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/simulations/scenarios?engagement_id=eng-1",
      expect.any(Object)
    );
  });
});

describe("fetchSimulationResults", () => {
  it("fetches results with optional scenario filter", async () => {
    mockOk({ items: [], total: 0 });
    await fetchSimulationResults("s1");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/simulations/results?scenario_id=s1",
      expect.any(Object)
    );
  });
});
