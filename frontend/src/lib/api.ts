/**
 * API client for communicating with the KMFlow backend.
 *
 * Wraps fetch with the base URL from environment variables
 * and provides typed response handling.
 *
 * TODO: Split into domain modules when this file exceeds 1500 lines.
 * Suggested modules: api/evidence.ts, api/governance.ts, api/monitoring.ts,
 * api/reports.ts, api/admin.ts
 */

const API_BASE_URL =
  typeof window === "undefined"
    ? process.env.API_URL || "http://localhost:8000"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

/**
 * Get the current auth token from localStorage (browser only).
 */
function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("kmflow_token");
}

/**
 * Build common headers including Authorization if a token is available.
 */
function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  const token = getAuthToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export interface ServiceHealth {
  postgres: "up" | "down";
  neo4j: "up" | "down";
  redis: "up" | "down";
  camunda?: "up" | "down";
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
    headers: authHeaders(),
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
export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: authHeaders(),
    signal,
  });

  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({ detail: `Request failed: ${response.status}`, status_code: response.status }));
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

/**
 * Generic POST request to the KMFlow API.
 */
export async function apiPost<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({ detail: `Request failed: ${response.status}`, status_code: response.status }));
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

// -- Phase 8: Auth / Metrics / Annotations ------------------------------------

export type UserRole =
  | "platform_admin"
  | "engagement_lead"
  | "process_analyst"
  | "evidence_reviewer"
  | "client_viewer";

export interface UserProfile {
  id: string;
  email: string;
  role: UserRole;
  name: string;
}

export async function fetchCurrentUser(): Promise<UserProfile> {
  return apiGet<UserProfile>("/api/v1/auth/me");
}

export async function uploadPortalEvidence(
  engagementId: string,
  file: File,
): Promise<Record<string, unknown>> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(
    `${API_BASE_URL}/api/v1/portal/${engagementId}/upload`,
    { method: "POST", headers: authHeaders(), body: formData },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || `Upload failed (${res.status})`);
  }
  return res.json();
}

// -- Camunda / Process Management types ---------------------------------------

export interface CamundaDeployment {
  id: string;
  name: string;
  deploymentTime: string;
  source: string | null;
  tenantId: string | null;
}

export interface ProcessDefinition {
  id: string;
  key: string;
  name: string | null;
  version: number;
  deploymentId: string;
  suspended: boolean;
  tenantId: string | null;
  category: string | null;
  description: string | null;
}

export interface ProcessInstance {
  id: string;
  definitionId: string;
  businessKey: string | null;
  suspended: boolean;
  ended: boolean;
  tenantId: string | null;
}

export interface CamundaTask {
  id: string;
  name: string;
  assignee: string | null;
  processDefinitionId: string;
  processInstanceId: string;
  created: string;
  taskDefinitionKey: string;
}

// -- Camunda / Process Management API functions -------------------------------

export async function fetchProcessDefinitions(): Promise<ProcessDefinition[]> {
  return apiGet<ProcessDefinition[]>("/api/v1/camunda/process-definitions");
}

export async function fetchDeployments(): Promise<CamundaDeployment[]> {
  return apiGet<CamundaDeployment[]>("/api/v1/camunda/deployments");
}

export async function fetchProcessInstances(
  active = true,
): Promise<ProcessInstance[]> {
  return apiGet<ProcessInstance[]>(
    `/api/v1/camunda/process-instances?active=${active}`,
  );
}

export async function fetchCamundaTasks(
  assignee?: string,
): Promise<CamundaTask[]> {
  const params = assignee ? `?assignee=${assignee}` : "";
  return apiGet<CamundaTask[]>(`/api/v1/camunda/tasks${params}`);
}

export async function startProcess(
  key: string,
  variables?: Record<string, string>,
): Promise<ProcessInstance> {
  return apiPost<ProcessInstance>(`/api/v1/camunda/process/${key}/start`, {
    variables: variables || null,
  });
}

// -- Governance types ---------------------------------------------------------

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

// -- Governance API functions -------------------------------------------------

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

// -- Integration types --------------------------------------------------------

export interface ConnectorType {
  type: string;
  description: string;
}

export interface IntegrationConnectionData {
  id: string;
  engagement_id: string;
  connector_type: string;
  name: string;
  status: string;
  config: Record<string, unknown>;
  field_mappings: Record<string, string> | null;
  last_sync: string | null;
  last_sync_records: number;
  error_message: string | null;
}

export interface IntegrationConnectionList {
  items: IntegrationConnectionData[];
  total: number;
}

// -- Integration API functions ------------------------------------------------

export async function fetchConnectorTypes(): Promise<ConnectorType[]> {
  return apiGet<ConnectorType[]>("/api/v1/integrations/connectors");
}

export async function fetchConnections(
  engagementId?: string,
): Promise<IntegrationConnectionList> {
  const params = engagementId ? `?engagement_id=${engagementId}` : "";
  return apiGet<IntegrationConnectionList>(
    `/api/v1/integrations/connections${params}`,
  );
}

export async function testConnection(
  connectionId: string,
): Promise<{ connection_id: string; success: boolean; message: string }> {
  return apiPost<{ connection_id: string; success: boolean; message: string }>(
    `/api/v1/integrations/connections/${connectionId}/test`,
    {},
  );
}

export async function syncConnection(
  connectionId: string,
): Promise<{ connection_id: string; records_synced: number; errors: string[] }> {
  return apiPost<{
    connection_id: string;
    records_synced: number;
    errors: string[];
  }>(`/api/v1/integrations/connections/${connectionId}/sync`, {});
}

// -- Shelf Request types ------------------------------------------------------

export interface ShelfRequestItemData {
  id: string;
  request_id: string;
  category: string;
  item_name: string;
  description: string | null;
  priority: string;
  status: string;
  matched_evidence_id: string | null;
}

export interface ShelfRequestData {
  id: string;
  engagement_id: string;
  title: string;
  description: string | null;
  status: string;
  due_date: string | null;
  items: ShelfRequestItemData[];
  fulfillment_percentage: number;
}

export interface ShelfRequestList {
  items: ShelfRequestData[];
  total: number;
}

// -- Shelf Request API functions ----------------------------------------------

export async function fetchShelfRequests(
  engagementId?: string,
): Promise<ShelfRequestList> {
  const params = engagementId ? `?engagement_id=${engagementId}` : "";
  return apiGet<ShelfRequestList>(`/api/v1/shelf-requests${params}`);
}

export async function fetchShelfRequest(
  requestId: string,
): Promise<ShelfRequestData> {
  return apiGet<ShelfRequestData>(`/api/v1/shelf-requests/${requestId}`);
}

export async function fetchShelfRequestStatus(
  requestId: string,
): Promise<{
  id: string;
  title: string;
  status: string;
  total_items: number;
  received_items: number;
  pending_items: number;
  overdue_items: number;
  fulfillment_percentage: number;
}> {
  return apiGet(`/api/v1/shelf-requests/${requestId}/status`);
}

// -- Metrics types ------------------------------------------------------------

export interface SuccessMetricData {
  id: string;
  name: string;
  unit: string;
  target_value: number;
  category: string;
  description: string | null;
  created_at: string;
}

export interface SuccessMetricList {
  items: SuccessMetricData[];
  total: number;
}

export interface MetricReadingData {
  id: string;
  metric_id: string;
  engagement_id: string;
  value: number;
  recorded_at: string;
  notes: string | null;
}

export interface MetricReadingList {
  items: MetricReadingData[];
  total: number;
}

export interface MetricSummaryEntry {
  metric_id: string;
  metric_name: string;
  unit: string;
  target_value: number;
  category: string;
  reading_count: number;
  latest_value: number | null;
  avg_value: number | null;
  min_value: number | null;
  max_value: number | null;
  on_target: boolean;
}

export interface MetricSummaryData {
  engagement_id: string;
  metrics: MetricSummaryEntry[];
  total: number;
  on_target_count: number;
}

// -- Metrics API functions ----------------------------------------------------

export async function fetchMetricDefinitions(
  category?: string,
): Promise<SuccessMetricList> {
  const params = category ? `?category=${category}` : "";
  return apiGet<SuccessMetricList>(`/api/v1/metrics/definitions${params}`);
}

export async function fetchMetricReadings(
  engagementId: string,
  metricId?: string,
): Promise<MetricReadingList> {
  const params = metricId ? `&metric_id=${metricId}` : "";
  return apiGet<MetricReadingList>(
    `/api/v1/metrics/readings?engagement_id=${engagementId}${params}`,
  );
}

export async function fetchMetricSummary(
  engagementId: string,
): Promise<MetricSummaryData> {
  return apiGet<MetricSummaryData>(
    `/api/v1/metrics/summary/${engagementId}`,
  );
}

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

// -- Generic API helpers for PUT/PATCH/DELETE ---------------------------------

export async function apiPut<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({ detail: `Request failed: ${response.status}`, status_code: response.status }));
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function apiDelete(path: string, signal?: AbortSignal): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "DELETE",
    headers: authHeaders(),
    signal,
  });
  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({ detail: `Request failed: ${response.status}`, status_code: response.status }));
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }
}
