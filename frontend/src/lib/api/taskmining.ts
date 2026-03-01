/**
 * Task mining API client — agent management, quarantine, dashboard stats.
 *
 * Consumed by the admin/task-mining/* pages (Epic #215).
 */

import { apiGet, apiPost, apiPut } from "./client";

// -- Types -------------------------------------------------------------------

export interface TaskMiningAgent {
  id: string;
  engagement_id: string;
  hostname: string;
  os_version: string;
  agent_version: string;
  machine_id: string;
  status: "pending_approval" | "approved" | "revoked" | "consent_revoked";
  deployment_mode: string;
  capture_granularity: string;
  last_heartbeat_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface AgentListResponse {
  agents: TaskMiningAgent[];
  total: number;
}

export interface QuarantineItem {
  id: string;
  engagement_id: string;
  pii_type: string;
  pii_field: string;
  detection_confidence: number;
  status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  auto_delete_at: string;
  created_at: string;
}

export interface QuarantineListResponse {
  items: QuarantineItem[];
  total: number;
}

export interface DashboardStats {
  active_agents: number;
  events_today?: number;
  actions_today?: number;
  events_last_24h?: number;
  total_actions?: number;
  quarantine_pending: number;
  total_sessions: number;
}

export interface AppUsageEntry {
  application_name: string;
  session_count: number;
  total_duration_seconds: number;
  avg_event_count: number;
}

export interface CaptureConfig {
  engagement_id: string;
  allowed_apps: string[];
  blocked_apps: string[];
  capture_granularity: string;
  keystroke_mode: string;
  screenshot_enabled: boolean;
  pii_patterns_version: string;
}

// -- Agent Management --------------------------------------------------------

export async function fetchAgents(engagementId?: string): Promise<AgentListResponse> {
  const params = engagementId ? `?engagement_id=${engagementId}` : "";
  const data = await apiGet<{ items?: TaskMiningAgent[]; agents?: TaskMiningAgent[]; total: number }>(
    `/api/v1/taskmining/agents${params}`,
  );
  return { agents: data.agents ?? data.items ?? [], total: data.total };
}

export function approveAgent(agentId: string): Promise<TaskMiningAgent> {
  return apiPost<TaskMiningAgent>(`/api/v1/taskmining/agents/${agentId}/approve`, {
    action: "approve",
  });
}

export function revokeAgent(agentId: string): Promise<TaskMiningAgent> {
  return apiPost<TaskMiningAgent>(`/api/v1/taskmining/agents/${agentId}/approve`, {
    action: "revoke",
  });
}

// -- Quarantine --------------------------------------------------------------

export function fetchQuarantine(engagementId?: string): Promise<QuarantineListResponse> {
  const params = engagementId ? `?engagement_id=${engagementId}` : "";
  return apiGet<QuarantineListResponse>(`/api/v1/taskmining/quarantine${params}`);
}

export function quarantineAction(
  itemId: string,
  action: "release" | "delete",
  reason?: string,
): Promise<{ status: string }> {
  return apiPost<{ status: string }>(`/api/v1/taskmining/quarantine/${itemId}/action`, {
    action,
    reason,
  });
}

// -- Dashboard ---------------------------------------------------------------

export function fetchDashboardStats(engagementId?: string): Promise<DashboardStats> {
  const params = engagementId ? `?engagement_id=${engagementId}` : "";
  return apiGet<DashboardStats>(`/api/v1/taskmining/dashboard/stats${params}`);
}

export function fetchAppUsage(
  engagementId: string,
  days: number = 7,
): Promise<AppUsageEntry[]> {
  return apiGet<AppUsageEntry[]>(
    `/api/v1/taskmining/dashboard/app-usage?engagement_id=${engagementId}&days=${days}`,
  );
}

// -- Config ------------------------------------------------------------------

export function fetchCaptureConfig(engagementId: string): Promise<CaptureConfig> {
  const params = `?engagement_id=${engagementId}`;
  return apiGet<CaptureConfig>(`/api/v1/taskmining/config${params}`);
}

export function updateCaptureConfig(
  engagementId: string,
  config: Partial<CaptureConfig>,
): Promise<CaptureConfig> {
  return apiPut<CaptureConfig>(`/api/v1/taskmining/config`, {
    engagement_id: engagementId,
    ...config,
  });
}
