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

// -- Regulatory Overlay API functions -----------------------------------------

export async function fetchComplianceState(
  engagementId: string,
): Promise<ComplianceStateData> {
  return apiGet<ComplianceStateData>(
    `/api/v1/regulatory/overlay/${engagementId}/compliance`,
  );
}

export async function fetchUngovernedProcesses(
  engagementId: string,
): Promise<{ ungoverned: UngovernedProcess[]; count: number }> {
  return apiGet<{ ungoverned: UngovernedProcess[]; count: number }>(
    `/api/v1/regulatory/overlay/${engagementId}/ungoverned`,
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

// -- Phase 3: Monitoring types ------------------------------------------------

export interface MonitoringJobData {
  id: string;
  engagement_id: string;
  name: string;
  source_type: string;
  status: string;
  connection_id: string | null;
  baseline_id: string | null;
  schedule_cron: string;
  config: Record<string, unknown> | null;
  last_run_at: string | null;
  next_run_at: string | null;
  error_message: string | null;
}

export interface MonitoringJobList {
  items: MonitoringJobData[];
  total: number;
}

export interface BaselineData {
  id: string;
  engagement_id: string;
  process_model_id: string | null;
  name: string;
  element_count: number;
  process_hash: string | null;
  is_active: boolean;
  created_at: string;
}

export interface BaselineList {
  items: BaselineData[];
  total: number;
}

export interface DeviationData {
  id: string;
  engagement_id: string;
  monitoring_job_id: string;
  category: string;
  description: string;
  affected_element: string | null;
  magnitude: number;
  details: Record<string, unknown> | null;
  detected_at: string;
}

export interface DeviationList {
  items: DeviationData[];
  total: number;
}

export interface AlertData {
  id: string;
  engagement_id: string;
  monitoring_job_id: string;
  severity: string;
  status: string;
  title: string;
  description: string;
  deviation_ids: string[] | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface AlertList {
  items: AlertData[];
  total: number;
}

export interface MonitoringStats {
  active_jobs: number;
  total_deviations: number;
  open_alerts: number;
  critical_alerts: number;
}

// -- Phase 3: Pattern types ---------------------------------------------------

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

// -- Phase 3: Simulation types ------------------------------------------------

export interface ScenarioData {
  id: string;
  engagement_id: string;
  process_model_id: string | null;
  name: string;
  simulation_type: string;
  parameters: Record<string, unknown> | null;
  description: string | null;
  created_at: string;
}

export interface ScenarioList {
  items: ScenarioData[];
  total: number;
}

export interface SimulationResultData {
  id: string;
  scenario_id: string;
  status: string;
  metrics: Record<string, unknown> | null;
  impact_analysis: Record<string, unknown> | null;
  recommendations: string[] | null;
  execution_time_ms: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface SimulationResultList {
  items: SimulationResultData[];
  total: number;
}

// -- Phase 3: Portal types ----------------------------------------------------

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

// -- Phase 3: Monitoring API functions ----------------------------------------

export async function fetchMonitoringJobs(
  engagementId?: string,
): Promise<MonitoringJobList> {
  const params = engagementId ? `?engagement_id=${engagementId}` : "";
  return apiGet<MonitoringJobList>(`/api/v1/monitoring/jobs${params}`);
}

export async function fetchMonitoringJob(
  jobId: string,
): Promise<MonitoringJobData> {
  return apiGet<MonitoringJobData>(`/api/v1/monitoring/jobs/${jobId}`);
}

export async function createMonitoringJob(
  body: Record<string, unknown>,
): Promise<MonitoringJobData> {
  return apiPost<MonitoringJobData>("/api/v1/monitoring/jobs", body);
}

export async function fetchMonitoringStats(
  engagementId: string,
): Promise<MonitoringStats> {
  return apiGet<MonitoringStats>(
    `/api/v1/monitoring/stats/${engagementId}`,
  );
}

export async function fetchAlerts(
  engagementId?: string,
): Promise<AlertList> {
  const params = engagementId ? `?engagement_id=${engagementId}` : "";
  return apiGet<AlertList>(`/api/v1/monitoring/alerts${params}`);
}

export async function fetchDeviations(
  engagementId?: string,
): Promise<DeviationList> {
  const params = engagementId ? `?engagement_id=${engagementId}` : "";
  return apiGet<DeviationList>(`/api/v1/monitoring/deviations${params}`);
}

export async function fetchBaselines(
  engagementId?: string,
): Promise<BaselineList> {
  const params = engagementId ? `?engagement_id=${engagementId}` : "";
  return apiGet<BaselineList>(`/api/v1/monitoring/baselines${params}`);
}

// -- Phase 3: Pattern API functions -------------------------------------------

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

// -- Phase 3: Simulation API functions ----------------------------------------

export async function fetchScenarios(
  engagementId?: string,
): Promise<ScenarioList> {
  const params = engagementId ? `?engagement_id=${engagementId}` : "";
  return apiGet<ScenarioList>(`/api/v1/simulations/scenarios${params}`);
}

export async function createScenario(
  body: Record<string, unknown>,
): Promise<ScenarioData> {
  return apiPost<ScenarioData>("/api/v1/simulations/scenarios", body);
}

export async function runScenario(
  scenarioId: string,
): Promise<SimulationResultData> {
  return apiPost<SimulationResultData>(
    `/api/v1/simulations/scenarios/${scenarioId}/run`,
    {},
  );
}

export async function fetchSimulationResults(
  scenarioId?: string,
): Promise<SimulationResultList> {
  const params = scenarioId ? `?scenario_id=${scenarioId}` : "";
  return apiGet<SimulationResultList>(
    `/api/v1/simulations/results${params}`,
  );
}

// -- Phase 3: Portal API functions --------------------------------------------

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

// -- Phase 6: Graph types -----------------------------------------------------

export interface GraphNode {
  id: string;
  label: string;
  properties: Record<string, unknown>;
}

export interface GraphRelationship {
  id: string;
  from_id: string;
  to_id: string;
  relationship_type: string;
  properties: Record<string, unknown>;
}

export interface GraphExportData {
  nodes: GraphNode[];
  relationships: GraphRelationship[];
}

// -- Phase 6: Graph API functions ---------------------------------------------

export async function fetchGraphData(
  engagementId: string,
): Promise<GraphExportData> {
  return apiGet<GraphExportData>(
    `/api/v1/graph/${engagementId}/subgraph`,
  );
}
