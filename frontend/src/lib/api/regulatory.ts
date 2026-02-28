/**
 * Regulatory Overlay API: compliance state, ungoverned processes,
 * and engagement / gap / governance reports.
 */

import { apiGet } from "./client";

// -- Regulatory Overlay types -------------------------------------------------

export interface ComplianceStateData {
  engagement_id: string;
  level: string;
  governed_count: number;
  ungoverned_count: number;
  total_processes: number;
  policy_coverage: number;
}

export interface UngovernedProcess {
  process_id: string;
  process_name: string;
}

// -- Report types -------------------------------------------------------------

export interface ReportResponse {
  engagement: Record<string, string>;
  report_type: string;
  generated_at: string;
  data: Record<string, unknown>;
}

// -- Regulatory Overlay API functions -----------------------------------------

export async function fetchComplianceState(
  engagementId: string,
  signal?: AbortSignal,
): Promise<ComplianceStateData> {
  return apiGet<ComplianceStateData>(
    `/api/v1/regulatory/overlay/${engagementId}/compliance`,
    signal,
  );
}

export async function fetchUngovernedProcesses(
  engagementId: string,
  signal?: AbortSignal,
): Promise<{ ungoverned: UngovernedProcess[]; count: number }> {
  return apiGet<{ ungoverned: UngovernedProcess[]; count: number }>(
    `/api/v1/regulatory/overlay/${engagementId}/ungoverned`,
    signal,
  );
}

// -- Report API functions -----------------------------------------------------

export async function fetchEngagementReport(
  engagementId: string,
  format: "json" | "html" = "json",
): Promise<ReportResponse> {
  return apiGet<ReportResponse>(
    `/api/v1/reports/${engagementId}/summary?format=${format}`,
  );
}

export async function fetchGapReport(
  engagementId: string,
  tomId?: string,
  format: "json" | "html" = "json",
): Promise<ReportResponse> {
  const params = tomId ? `&tom_id=${tomId}` : "";
  return apiGet<ReportResponse>(
    `/api/v1/reports/${engagementId}/gap-analysis?format=${format}${params}`,
  );
}

export async function fetchGovernanceReport(
  engagementId: string,
  format: "json" | "html" = "json",
): Promise<ReportResponse> {
  return apiGet<ReportResponse>(
    `/api/v1/reports/${engagementId}/governance?format=${format}`,
  );
}
