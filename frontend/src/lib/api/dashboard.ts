/**
 * Dashboard API: aggregated engagement metrics, evidence coverage,
 * confidence distribution, BPMN views, process elements, and gaps.
 */

import { apiGet } from "./client";

// -- Types --------------------------------------------------------------------

export interface GapCountBySeverity {
  high: number;
  medium: number;
  low: number;
}

export interface RecentActivityEntry {
  id: string;
  action: string;
  actor: string;
  details: string | null;
  created_at: string | null;
}

export interface DashboardData {
  engagement_id: string;
  engagement_name: string;
  evidence_coverage_pct: number;
  overall_confidence: number;
  gap_counts: GapCountBySeverity;
  evidence_item_count: number;
  process_model_count: number;
  recent_activity: RecentActivityEntry[];
}

export interface CategoryCoverage {
  category: string;
  requested_count: number;
  received_count: number;
  coverage_pct: number;
  below_threshold: boolean;
}

export interface EvidenceCoverageData {
  engagement_id: string;
  overall_coverage_pct: number;
  categories: CategoryCoverage[];
}

export interface ConfidenceBucket {
  level: string;
  min_score: number;
  max_score: number;
  count: number;
}

export interface WeakElement {
  id: string;
  name: string;
  element_type: string;
  confidence_score: number;
}

export interface ConfidenceDistributionData {
  engagement_id: string;
  model_id: string | null;
  overall_confidence: number;
  distribution: ConfidenceBucket[];
  weakest_elements: WeakElement[];
}

export interface BPMNData {
  model_id: string;
  bpmn_xml: string;
  element_confidences: Record<string, number>;
}

export interface ProcessElementData {
  id: string;
  model_id: string;
  element_type: string;
  name: string;
  confidence_score: number;
  triangulation_score: number;
  corroboration_level: string;
  evidence_count: number;
  evidence_ids: string[] | null;
  metadata_json: Record<string, unknown> | null;
}

export interface ProcessElementList {
  items: ProcessElementData[];
  total: number;
}

export interface EvidenceMapEntry {
  evidence_id: string;
  element_names: string[];
  element_ids: string[];
}

export interface GapData {
  id: string;
  model_id: string;
  gap_type: string;
  description: string;
  severity: string;
  recommendation: string | null;
  related_element_id: string | null;
}

// -- Confidence Heatmap types -------------------------------------------------

export type BrightnessLevel = "bright" | "dim" | "dark";
export type EvidenceGrade = "A" | "B" | "C" | "D" | "F";

export interface ElementConfidenceEntry {
  score: number;
  brightness: BrightnessLevel;
  grade: EvidenceGrade;
}

export interface ConfidenceMapData {
  engagement_id: string;
  model_version: number;
  elements: Record<string, ElementConfidenceEntry>;
  total_elements: number;
}

export interface ConfidenceSummaryData {
  engagement_id: string;
  model_version: number;
  total_elements: number;
  bright_count: number;
  bright_percentage: number;
  dim_count: number;
  dim_percentage: number;
  dark_count: number;
  dark_percentage: number;
  overall_confidence: number;
}

// -- API functions ------------------------------------------------------------

/**
 * Fetch aggregated dashboard data for an engagement.
 */
export async function fetchDashboard(
  engagementId: string,
): Promise<DashboardData> {
  return apiGet<DashboardData>(`/api/v1/dashboard/${engagementId}`);
}

/**
 * Fetch detailed evidence coverage by category.
 */
export async function fetchEvidenceCoverage(
  engagementId: string,
): Promise<EvidenceCoverageData> {
  return apiGet<EvidenceCoverageData>(
    `/api/v1/dashboard/${engagementId}/evidence-coverage`,
  );
}

/**
 * Fetch confidence distribution across process elements.
 */
export async function fetchConfidenceDistribution(
  engagementId: string,
): Promise<ConfidenceDistributionData> {
  return apiGet<ConfidenceDistributionData>(
    `/api/v1/dashboard/${engagementId}/confidence-distribution`,
  );
}

/**
 * Fetch BPMN XML with element confidence metadata.
 */
export async function fetchBPMNXml(modelId: string): Promise<BPMNData> {
  return apiGet<BPMNData>(`/api/v1/pov/${modelId}/bpmn`);
}

/**
 * Fetch process elements for a model.
 */
export async function fetchProcessElements(
  modelId: string,
  limit = 50,
  offset = 0,
): Promise<ProcessElementList> {
  return apiGet<ProcessElementList>(
    `/api/v1/pov/${modelId}/elements?limit=${limit}&offset=${offset}`,
  );
}

/**
 * Fetch evidence-to-element map for a model.
 */
export async function fetchEvidenceMap(
  modelId: string,
): Promise<EvidenceMapEntry[]> {
  return apiGet<EvidenceMapEntry[]>(`/api/v1/pov/${modelId}/evidence-map`);
}

/**
 * Fetch evidence gaps for a model.
 */
export async function fetchGaps(modelId: string): Promise<GapData[]> {
  return apiGet<GapData[]>(`/api/v1/pov/${modelId}/gaps`);
}

/**
 * Fetch per-element confidence map for heatmap rendering.
 */
export async function fetchConfidenceMap(
  engagementId: string,
): Promise<ConfidenceMapData> {
  return apiGet<ConfidenceMapData>(
    `/api/v1/pov/engagement/${engagementId}/confidence`,
  );
}

/**
 * Fetch confidence summary for export (JSON).
 */
export async function fetchConfidenceSummary(
  engagementId: string,
): Promise<ConfidenceSummaryData> {
  return apiGet<ConfidenceSummaryData>(
    `/api/v1/pov/engagement/${engagementId}/confidence/summary`,
  );
}

/**
 * Build the URL for confidence summary CSV download.
 */
export function getConfidenceSummaryCSVUrl(engagementId: string): string {
  return `/api/v1/pov/engagement/${engagementId}/confidence/summary?format=csv`;
}
