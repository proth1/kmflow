/**
 * Annotations API: per-target commentary and lineage records.
 */

import { apiGet, apiPost } from "./client";

// -- Annotation types ---------------------------------------------------------

export interface AnnotationData {
  id: string;
  engagement_id: string;
  target_type: string;
  target_id: string;
  author_id: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface AnnotationList {
  items: AnnotationData[];
  total: number;
}

// -- Lineage types ------------------------------------------------------------

export interface LineageRecord {
  id: string;
  evidence_item_id: string;
  source_system: string;
  source_url: string | null;
  source_identifier: string | null;
  transformation_chain: Record<string, unknown>[] | null;
  version: number;
  version_hash: string | null;
  parent_version_id: string | null;
  refresh_schedule: string | null;
  last_refreshed_at: string | null;
  created_at: string;
}

export interface LineageChainData {
  evidence_item_id: string;
  evidence_name: string;
  source_system: string | null;
  total_versions: number;
  lineage: LineageRecord[];
}

// -- Annotation API functions -------------------------------------------------

export async function fetchAnnotations(
  engagementId: string,
  targetType?: string,
  targetId?: string,
): Promise<AnnotationList> {
  let params = `?engagement_id=${engagementId}`;
  if (targetType) params += `&target_type=${targetType}`;
  if (targetId) params += `&target_id=${targetId}`;
  return apiGet<AnnotationList>(`/api/v1/annotations${params}`);
}

export async function createAnnotation(
  body: {
    engagement_id: string;
    target_type: string;
    target_id: string;
    content: string;
  },
): Promise<AnnotationData> {
  return apiPost<AnnotationData>("/api/v1/annotations", body);
}

// -- Lineage API functions ----------------------------------------------------

export async function fetchLineageChain(
  engagementId: string,
  evidenceId: string,
): Promise<LineageChainData> {
  return apiGet<LineageChainData>(
    `/api/v1/engagements/${engagementId}/evidence/${evidenceId}/lineage`,
  );
}

export async function fetchLineageRecord(
  engagementId: string,
  evidenceId: string,
  lineageId: string,
): Promise<LineageRecord> {
  return apiGet<LineageRecord>(
    `/api/v1/engagements/${engagementId}/evidence/${evidenceId}/lineage/${lineageId}`,
  );
}
