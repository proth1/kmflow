/**
 * Governance API: data catalog, policy management, policy evaluation,
 * and governance health.
 */

import { apiGet, apiPost } from "./client";

// -- Types --------------------------------------------------------------------

export interface CatalogEntryData {
  id: string;
  dataset_name: string;
  dataset_type: string;
  layer: string;
  engagement_id: string | null;
  schema_definition: Record<string, unknown> | null;
  owner: string | null;
  classification: string;
  quality_sla: Record<string, unknown> | null;
  retention_days: number | null;
  description: string | null;
  row_count: number | null;
  size_bytes: number | null;
  delta_table_path: string | null;
  created_at: string;
  updated_at: string;
}

export interface PolicyData {
  policy_file: string;
  policies: Record<string, unknown>;
}

export interface PolicyEvaluationResult {
  entry_id: string;
  compliant: boolean;
  violation_count: number;
  violations: {
    policy_name: string;
    severity: string;
    message: string;
    entry_id: string;
  }[];
}

export interface GovernanceHealthData {
  engagement_id: string;
  total_entries: number;
  passing_count: number;
  failing_count: number;
  compliance_percentage: number;
  entries: {
    entry_id: string;
    name: string;
    classification: string;
    sla_passing: boolean;
    violation_count: number;
  }[];
}

// -- API functions ------------------------------------------------------------

export async function fetchCatalogEntries(
  engagementId?: string,
): Promise<CatalogEntryData[]> {
  const params = engagementId ? `?engagement_id=${engagementId}` : "";
  return apiGet<CatalogEntryData[]>(`/api/v1/governance/catalog${params}`);
}

export async function fetchPolicies(): Promise<PolicyData> {
  return apiGet<PolicyData>("/api/v1/governance/policies");
}

export async function evaluatePolicy(
  entryId: string,
): Promise<PolicyEvaluationResult> {
  return apiPost<PolicyEvaluationResult>("/api/v1/governance/policies/evaluate", {
    entry_id: entryId,
  });
}

export async function fetchGovernanceHealth(
  engagementId: string,
): Promise<GovernanceHealthData> {
  return apiGet<GovernanceHealthData>(
    `/api/v1/governance/health/${engagementId}`,
  );
}
