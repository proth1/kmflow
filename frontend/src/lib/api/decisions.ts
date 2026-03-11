/**
 * Decision Intelligence API client.
 *
 * Provides typed access to the decision discovery, business rules,
 * DMN export, validation, and coverage endpoints.
 */

import { apiGet, apiPost } from "./client";

// -- Types -------------------------------------------------------------------

export interface DecisionPoint {
  id: string;
  name: string;
  entity_type: string;
  confidence: number;
  rule_count: number;
  evidence_sources: number;
  brightness: "BRIGHT" | "DIM" | "DARK";
}

export interface DecisionListResponse {
  engagement_id: string;
  decisions: DecisionPoint[];
  total: number;
  limit: number;
  offset: number;
}

export interface BusinessRule {
  id: string;
  rule_text: string;
  threshold_value: string | null;
  effective_from: string | null;
  effective_to: string | null;
  source_weight: number;
  evidence_ids: string[];
}

export interface DecisionRulesResponse {
  decision_id: string;
  decision_name: string;
  rules: BusinessRule[];
  total: number;
}

export interface DMNExportResponse {
  decision_id: string;
  decision_name: string;
  dmn_xml: string;
  rule_count: number;
}

export interface ValidateRulePayload {
  action: "confirm" | "correct" | "reject" | "defer";
  corrected_text?: string;
  reasoning?: string;
  confidence_override?: number;
}

export interface ValidationResponse {
  decision_id: string;
  action: string;
  validation_count: number;
}

export interface CoverageGap {
  activity_name: string;
  has_rules: boolean;
  rule_count: number;
  gap_weight: number;
  probe_generated: boolean;
}

export interface CoverageResponse {
  engagement_id: string;
  total_activities: number;
  covered: number;
  gaps: CoverageGap[];
  coverage_percentage: number;
}

// -- API Functions -----------------------------------------------------------

/**
 * List all decision points discovered for an engagement.
 */
export function fetchDecisions(
  engagementId: string,
  params?: { limit?: number; offset?: number; min_confidence?: number },
  signal?: AbortSignal,
): Promise<DecisionListResponse> {
  const query = new URLSearchParams();
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  if (params?.min_confidence) query.set("min_confidence", String(params.min_confidence));
  const qs = query.toString();
  return apiGet<DecisionListResponse>(
    `/api/v1/engagements/${engagementId}/decisions${qs ? `?${qs}` : ""}`,
    signal,
  );
}

/**
 * Get business rules associated with a decision point.
 */
export function fetchDecisionRules(
  engagementId: string,
  decisionId: string,
  signal?: AbortSignal,
): Promise<DecisionRulesResponse> {
  return apiGet<DecisionRulesResponse>(
    `/api/v1/engagements/${engagementId}/decisions/${decisionId}/rules`,
    signal,
  );
}

/**
 * Export a decision as DMN 1.3 XML.
 */
export function exportDecisionDMN(
  engagementId: string,
  decisionId: string,
  signal?: AbortSignal,
): Promise<DMNExportResponse> {
  return apiGet<DMNExportResponse>(
    `/api/v1/engagements/${engagementId}/decisions/${decisionId}/dmn`,
    signal,
  );
}

/**
 * Record SME validation of a decision's business rules.
 */
export function validateDecisionRule(
  engagementId: string,
  decisionId: string,
  payload: ValidateRulePayload,
  signal?: AbortSignal,
): Promise<ValidationResponse> {
  return apiPost<ValidationResponse>(
    `/api/v1/engagements/${engagementId}/decisions/${decisionId}/validate`,
    payload,
    signal,
  );
}

/**
 * Get Form 5 (Rules) coverage gaps for all activities.
 */
export function fetchDecisionCoverage(
  engagementId: string,
  signal?: AbortSignal,
): Promise<CoverageResponse> {
  return apiGet<CoverageResponse>(
    `/api/v1/engagements/${engagementId}/decisions/coverage`,
    signal,
  );
}
