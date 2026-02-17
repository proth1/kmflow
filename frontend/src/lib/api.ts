/**
 * API client for communicating with the KMFlow backend.
 *
 * Wraps fetch with the base URL from environment variables
 * and provides typed response handling.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ServiceHealth {
  postgres: "up" | "down";
  neo4j: "up" | "down";
  redis: "up" | "down";
}

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  services: ServiceHealth;
  version: string;
}

export interface ApiError {
  detail: string;
  status_code: number;
}

// -- Dashboard types ----------------------------------------------------------

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

/**
 * Fetch the health status of the KMFlow backend.
 */
export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }

  return response.json() as Promise<HealthResponse>;
}

/**
 * Generic GET request to the KMFlow API.
 */
export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    const error: ApiError = await response.json();
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

/**
 * Generic POST request to the KMFlow API.
 */
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error: ApiError = await response.json();
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

// -- Dashboard API functions --------------------------------------------------

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
