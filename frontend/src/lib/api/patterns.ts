/**
 * Patterns API: cross-engagement pattern library management and search.
 */

import { apiGet, apiPost } from "./client";

// -- Types --------------------------------------------------------------------

export interface PatternData {
  id: string;
  source_engagement_id: string | null;
  category: string;
  title: string;
  description: string;
  anonymized_data: Record<string, unknown> | null;
  industry: string | null;
  tags: string[] | null;
  usage_count: number;
  effectiveness_score: number;
  created_at: string;
}

export interface PatternList {
  items: PatternData[];
  total: number;
}

export interface AccessRuleData {
  id: string;
  pattern_id: string;
  engagement_id: string;
  granted_by: string;
  granted_at: string;
}

// -- API functions ------------------------------------------------------------

export async function fetchPatterns(
  category?: string,
): Promise<PatternList> {
  const params = category ? `?category=${category}` : "";
  return apiGet<PatternList>(`/api/v1/patterns${params}`);
}

export async function fetchPattern(patternId: string): Promise<PatternData> {
  return apiGet<PatternData>(`/api/v1/patterns/${patternId}`);
}

export async function createPattern(
  body: Record<string, unknown>,
): Promise<PatternData> {
  return apiPost<PatternData>("/api/v1/patterns", body);
}

export async function searchPatterns(
  body: Record<string, unknown>,
): Promise<PatternList> {
  return apiPost<PatternList>("/api/v1/patterns/search", body);
}
