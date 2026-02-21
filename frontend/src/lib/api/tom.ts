/**
 * TOM (Target Operating Model) API: alignment scoring, gap analysis,
 * maturity scores, and transformation roadmaps.
 */

import { apiGet, apiPost } from "./client";

// -- TOM types ----------------------------------------------------------------

export interface TOMMaturityScore {
  dimension: string;
  current_maturity: number;
  target_maturity: number;
  gap_type: string;
  severity: number;
  confidence: number;
  priority_score: number;
}

export interface TOMAlignmentData {
  engagement_id: string;
  tom_id: string;
  gaps: TOMMaturityScore[];
  maturity_scores: Record<string, number>;
  overall_alignment: number;
}

export interface TOMGapEntry {
  id: string;
  dimension: string;
  gap_type: string;
  severity: number;
  confidence: number;
  priority_score: number;
  rationale: string | null;
  recommendation: string | null;
}

export interface TOMGapList {
  items: TOMGapEntry[];
  total: number;
}

// -- Roadmap types ------------------------------------------------------------

export interface RoadmapInitiative {
  gap_id: string;
  dimension: string;
  gap_type: string;
  severity: number;
  priority_score: number;
  recommendation: string;
}

export interface RoadmapPhase {
  phase_number: number;
  name: string;
  duration_months: number;
  initiatives: RoadmapInitiative[];
  dependencies: string[];
}

export interface TransformationRoadmap {
  engagement_id: string;
  tom_id: string;
  phases: RoadmapPhase[];
  total_initiatives: number;
  estimated_duration_months: number;
}

// -- TOM API functions --------------------------------------------------------

export async function fetchTOMAlignment(
  engagementId: string,
  tomId: string,
): Promise<TOMAlignmentData> {
  return apiPost<TOMAlignmentData>(
    `/api/v1/tom/alignment/${engagementId}/run`,
    { tom_id: tomId },
  );
}

export async function fetchTOMGaps(
  engagementId: string,
  tomId?: string,
): Promise<TOMGapList> {
  const params = tomId ? `?tom_id=${tomId}` : "";
  return apiGet<TOMGapList>(
    `/api/v1/tom/gaps?engagement_id=${engagementId}${params}`,
  );
}

export async function fetchMaturityScores(
  engagementId: string,
  tomId: string,
): Promise<TOMAlignmentData> {
  return apiGet<TOMAlignmentData>(
    `/api/v1/tom/alignment/${engagementId}/maturity?tom_id=${tomId}`,
  );
}

// -- Roadmap API functions ----------------------------------------------------

export async function fetchRoadmap(
  engagementId: string,
  tomId: string,
): Promise<TransformationRoadmap> {
  return apiGet<TransformationRoadmap>(
    `/api/v1/tom/roadmap/${engagementId}?tom_id=${tomId}`,
  );
}

export async function generateRoadmap(
  engagementId: string,
  tomId: string,
): Promise<TransformationRoadmap> {
  return apiPost<TransformationRoadmap>(
    `/api/v1/tom/roadmap/${engagementId}/generate`,
    { tom_id: tomId },
  );
}
