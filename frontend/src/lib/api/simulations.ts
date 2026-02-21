/**
 * Simulations API: scenarios, results, modifications, coverage, comparisons,
 * epistemic action planning, financial assumptions / impact, alternative
 * suggestions, and scenario ranking.
 */

import { apiGet, apiPost, apiPatch, apiDelete } from "./client";

// -- Scenario types -----------------------------------------------------------

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

// -- Scenario Comparison Workbench types --------------------------------------

export type CoverageClassification = "bright" | "dim" | "dark";

export interface ElementCoverageData {
  element_id: string;
  element_name: string;
  classification: CoverageClassification;
  evidence_count: number;
  confidence: number;
  is_added: boolean;
  is_removed: boolean;
  is_modified: boolean;
}

export interface ScenarioCoverageData {
  scenario_id: string;
  elements: ElementCoverageData[];
  bright_count: number;
  dim_count: number;
  dark_count: number;
  aggregate_confidence: number;
}

export interface ScenarioComparisonEntry {
  scenario_id: string;
  scenario_name: string;
  deltas: Record<string, {
    baseline: number;
    simulated: number;
    delta: number;
    pct_change: number;
  }> | null;
  assessment: string | null;
  coverage_summary: {
    bright: number;
    dim: number;
    dark: number;
  } | null;
}

export interface ScenarioComparisonData {
  baseline_id: string;
  baseline_name: string;
  comparisons: ScenarioComparisonEntry[];
}

export type ModificationType =
  | "task_add"
  | "task_remove"
  | "task_modify"
  | "role_reassign"
  | "gateway_restructure"
  | "control_add"
  | "control_remove";

export interface ModificationData {
  id: string;
  scenario_id: string;
  modification_type: ModificationType;
  element_id: string;
  element_name: string;
  change_data: Record<string, unknown> | null;
  template_key: string | null;
  applied_at: string;
}

export interface ModificationList {
  items: ModificationData[];
  total: number;
}

// -- Epistemic Action Planner types -------------------------------------------

export interface EpistemicActionData {
  target_element_id: string;
  target_element_name: string;
  evidence_gap_description: string;
  current_confidence: number;
  estimated_confidence_uplift: number;
  projected_confidence: number;
  information_gain_score: number;
  recommended_evidence_category: string;
  priority: string;
}

export interface EpistemicPlanAggregates {
  total: number;
  high_priority_count: number;
  estimated_aggregate_uplift: number;
}

export interface EpistemicPlanData {
  scenario_id: string;
  actions: EpistemicActionData[];
  aggregated_view: EpistemicPlanAggregates;
}

// -- Financial Assumption types -----------------------------------------------

export type FinancialAssumptionType =
  | "cost_per_role"
  | "technology_cost"
  | "volume_forecast"
  | "implementation_cost";

export interface FinancialAssumptionData {
  id: string;
  engagement_id: string;
  assumption_type: string;
  name: string;
  value: number;
  unit: string;
  confidence: number;
  source_evidence_id: string | null;
  notes: string | null;
  created_at: string;
}

export interface FinancialAssumptionList {
  items: FinancialAssumptionData[];
  total: number;
}

// -- Alternative Suggestion types ---------------------------------------------

export type SuggestionDispositionType =
  | "pending"
  | "accepted"
  | "modified"
  | "rejected";

export interface AlternativeSuggestionData {
  id: string;
  scenario_id: string;
  suggestion_text: string;
  rationale: string;
  governance_flags: Record<string, unknown> | null;
  evidence_gaps: Record<string, unknown> | null;
  disposition: SuggestionDispositionType;
  disposition_notes: string | null;
  created_at: string;
}

export interface AlternativeSuggestionList {
  items: AlternativeSuggestionData[];
  total: number;
}

// -- Financial Impact types ---------------------------------------------------

export interface CostRangeData {
  optimistic: number;
  expected: number;
  pessimistic: number;
}

export interface SensitivityEntryData {
  assumption_name: string;
  base_value: number;
  impact_range: CostRangeData;
}

export interface FinancialImpactData {
  scenario_id: string;
  cost_range: CostRangeData;
  sensitivity_analysis: SensitivityEntryData[];
  assumption_count: number;
  delta_vs_baseline: number | null;
}

// -- Scenario Ranking types ---------------------------------------------------

export interface ScenarioRankEntry {
  scenario_id: string;
  scenario_name: string;
  composite_score: number;
  evidence_score: number;
  simulation_score: number;
  financial_score: number;
  governance_score: number;
}

export interface ScenarioRankingData {
  engagement_id: string;
  rankings: ScenarioRankEntry[];
  weights: Record<string, number>;
}

// -- Scenario API functions ---------------------------------------------------

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

// -- Scenario Comparison API functions ----------------------------------------

export async function fetchScenarioComparison(
  baselineId: string,
  compareIds: string[],
): Promise<ScenarioComparisonData> {
  return apiGet<ScenarioComparisonData>(
    `/api/v1/simulations/scenarios/${baselineId}/compare?ids=${compareIds.join(",")}`,
  );
}

export async function fetchScenarioCoverage(
  scenarioId: string,
): Promise<ScenarioCoverageData> {
  return apiGet<ScenarioCoverageData>(
    `/api/v1/simulations/scenarios/${scenarioId}/evidence-coverage`,
  );
}

export async function fetchModifications(
  scenarioId: string,
): Promise<ModificationList> {
  return apiGet<ModificationList>(
    `/api/v1/simulations/scenarios/${scenarioId}/modifications`,
  );
}

export async function addModification(
  scenarioId: string,
  body: {
    modification_type: ModificationType;
    element_id: string;
    element_name: string;
    change_data?: Record<string, unknown>;
    template_key?: string;
  },
): Promise<ModificationData> {
  return apiPost<ModificationData>(
    `/api/v1/simulations/scenarios/${scenarioId}/modifications`,
    body,
  );
}

export async function deleteModification(
  scenarioId: string,
  modificationId: string,
): Promise<void> {
  return apiDelete(
    `/api/v1/simulations/scenarios/${scenarioId}/modifications/${modificationId}`,
  );
}

// -- Epistemic Action Planner API ---------------------------------------------

export async function fetchEpistemicPlan(
  scenarioId: string,
  limit = 10,
  createShelfRequest = false,
): Promise<EpistemicPlanData> {
  return apiPost<EpistemicPlanData>(
    `/api/v1/simulations/scenarios/${scenarioId}/epistemic-plan?limit=${limit}&create_shelf_request=${createShelfRequest}`,
    {},
  );
}

// -- Financial Assumptions API ------------------------------------------------

export async function createFinancialAssumption(
  scenarioId: string,
  body: {
    engagement_id: string;
    assumption_type: FinancialAssumptionType;
    name: string;
    value: number;
    unit: string;
    confidence: number;
    source_evidence_id?: string;
    notes?: string;
  },
): Promise<FinancialAssumptionData> {
  return apiPost<FinancialAssumptionData>(
    `/api/v1/simulations/scenarios/${scenarioId}/financial-assumptions`,
    body,
  );
}

export async function fetchFinancialAssumptions(
  scenarioId: string,
): Promise<FinancialAssumptionList> {
  return apiGet<FinancialAssumptionList>(
    `/api/v1/simulations/scenarios/${scenarioId}/financial-assumptions`,
  );
}

export async function deleteFinancialAssumption(
  scenarioId: string,
  assumptionId: string,
): Promise<void> {
  return apiDelete(
    `/api/v1/simulations/scenarios/${scenarioId}/financial-assumptions/${assumptionId}`,
  );
}

// -- Alternative Suggestions API ----------------------------------------------

export async function requestSuggestions(
  scenarioId: string,
  contextNotes?: string,
): Promise<AlternativeSuggestionList> {
  return apiPost<AlternativeSuggestionList>(
    `/api/v1/simulations/scenarios/${scenarioId}/suggestions`,
    { context_notes: contextNotes || null },
  );
}

export async function fetchSuggestions(
  scenarioId: string,
): Promise<AlternativeSuggestionList> {
  return apiGet<AlternativeSuggestionList>(
    `/api/v1/simulations/scenarios/${scenarioId}/suggestions`,
  );
}

export async function updateSuggestionDisposition(
  scenarioId: string,
  suggestionId: string,
  disposition: SuggestionDispositionType,
  dispositionNotes?: string,
): Promise<AlternativeSuggestionData> {
  return apiPatch<AlternativeSuggestionData>(
    `/api/v1/simulations/scenarios/${scenarioId}/suggestions/${suggestionId}`,
    { disposition, disposition_notes: dispositionNotes || null },
  );
}

// -- Financial Impact API -----------------------------------------------------

export async function fetchFinancialImpact(
  scenarioId: string,
): Promise<FinancialImpactData> {
  return apiGet<FinancialImpactData>(
    `/api/v1/simulations/scenarios/${scenarioId}/financial-impact`,
  );
}

// -- Scenario Ranking API -----------------------------------------------------

export async function fetchScenarioRanking(
  engagementId: string,
  weights?: { evidence?: number; simulation?: number; financial?: number; governance?: number },
): Promise<ScenarioRankingData> {
  const params = new URLSearchParams({ engagement_id: engagementId });
  if (weights?.evidence !== undefined) params.set("w_evidence", String(weights.evidence));
  if (weights?.simulation !== undefined) params.set("w_simulation", String(weights.simulation));
  if (weights?.financial !== undefined) params.set("w_financial", String(weights.financial));
  if (weights?.governance !== undefined) params.set("w_governance", String(weights.governance));
  return apiGet<ScenarioRankingData>(
    `/api/v1/simulations/scenarios/rank?${params.toString()}`,
  );
}
