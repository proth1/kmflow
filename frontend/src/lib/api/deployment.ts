/**
 * Deployment capabilities API client (KMFLOW-7).
 *
 * Fetches deployment configuration to adapt the UI based on
 * which features are available (cloud vs on-prem vs air-gapped).
 */

import { apiGet } from "./client";

export interface DeploymentCapabilities {
  llm_available: boolean;
  llm_provider: string;
  llm_is_local: boolean;
  embeddings_local: boolean;
  data_residency_default: string;
  copilot_enabled: boolean;
  scenario_suggestions_enabled: boolean;
  gap_rationale_enabled: boolean;
}

/**
 * Fetch deployment capabilities from the API.
 * Used to conditionally render LLM-dependent features.
 */
export async function getDeploymentCapabilities(): Promise<DeploymentCapabilities> {
  return apiGet<DeploymentCapabilities>("/api/v1/deployment/capabilities");
}
