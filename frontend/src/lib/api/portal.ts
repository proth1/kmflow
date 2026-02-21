/**
 * Portal API: client-facing overview, findings, evidence status,
 * process views, and evidence upload.
 */

import { apiGet, authHeaders, API_BASE_URL } from "./client";

// -- Types --------------------------------------------------------------------

export interface PortalOverview {
  engagement_id: string;
  engagement_name: string;
  client: string;
  status: string;
  evidence_count: number;
  process_model_count: number;
  open_alerts: number;
  overall_confidence: number;
}

export interface PortalFinding {
  id: string;
  dimension: string;
  gap_type: string;
  severity: number;
  recommendation: string | null;
}

export interface PortalFindingsList {
  items: PortalFinding[];
  total: number;
}

export interface PortalEvidenceCategory {
  category: string;
  count: number;
  avg_quality: number;
}

export interface PortalEvidenceSummary {
  total_items: number;
  categories: PortalEvidenceCategory[];
}

// -- API functions ------------------------------------------------------------

export async function fetchPortalOverview(
  engagementId: string,
): Promise<PortalOverview> {
  return apiGet<PortalOverview>(
    `/api/v1/portal/${engagementId}/overview`,
  );
}

export async function fetchPortalFindings(
  engagementId: string,
): Promise<PortalFindingsList> {
  return apiGet<PortalFindingsList>(
    `/api/v1/portal/${engagementId}/findings`,
  );
}

export async function fetchPortalEvidenceStatus(
  engagementId: string,
): Promise<PortalEvidenceSummary> {
  return apiGet<PortalEvidenceSummary>(
    `/api/v1/portal/${engagementId}/evidence-status`,
  );
}

export async function fetchPortalProcess(
  engagementId: string,
): Promise<Record<string, unknown>> {
  return apiGet<Record<string, unknown>>(
    `/api/v1/portal/${engagementId}/process`,
  );
}

export async function uploadPortalEvidence(
  engagementId: string,
  file: File,
): Promise<Record<string, unknown>> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(
    `${API_BASE_URL}/api/v1/portal/${engagementId}/upload`,
    { method: "POST", headers: authHeaders(), credentials: "include", body: formData },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || `Upload failed (${res.status})`);
  }
  return res.json();
}
