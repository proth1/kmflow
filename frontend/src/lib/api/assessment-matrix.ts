/**
 * Assessment Overlay Matrix API client.
 */

import { apiGet, apiPost } from "./client";

export interface MatrixEntry {
  id: string;
  process_area_name: string;
  process_area_description: string | null;
  value_score: number;
  ability_to_execute: number;
  quadrant: "transform" | "invest" | "maintain" | "deprioritize";
  value_components: Record<string, number>;
  ability_components: Record<string, number>;
  element_count: number;
  notes: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface MatrixResponse {
  engagement_id: string;
  entries: MatrixEntry[];
  total: number;
  quadrant_summary: Record<string, number>;
}

export interface MatrixExportResponse {
  engagement_id: string;
  entries: MatrixEntry[];
  quadrant_analysis: Record<
    string,
    Array<{ process_area: string; value_score: number; ability_to_execute: number }>
  >;
  recommendations: Array<{
    priority: string;
    action: string;
    areas: string[];
    rationale: string;
  }>;
  total: number;
}

export function fetchAssessmentMatrix(
  engagementId: string,
  signal?: AbortSignal,
): Promise<MatrixResponse> {
  return apiGet<MatrixResponse>(
    `/api/v1/engagements/${engagementId}/assessment-matrix`,
    signal,
  );
}

export function computeAssessmentMatrix(
  engagementId: string,
  signal?: AbortSignal,
): Promise<MatrixResponse> {
  return apiPost<MatrixResponse>(
    `/api/v1/engagements/${engagementId}/assessment-matrix/compute`,
    {},
    signal,
  );
}

export function exportAssessmentMatrix(
  engagementId: string,
  signal?: AbortSignal,
): Promise<MatrixExportResponse> {
  return apiPost<MatrixExportResponse>(
    `/api/v1/engagements/${engagementId}/assessment-matrix/export`,
    {},
    signal,
  );
}
