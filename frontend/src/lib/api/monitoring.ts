/**
 * Monitoring API: jobs, baselines, deviations, alerts, and stats.
 */

import { apiGet, apiPost } from "./client";

// -- Types --------------------------------------------------------------------

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

// -- API functions ------------------------------------------------------------

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
