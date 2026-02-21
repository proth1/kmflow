/**
 * Metrics API: success metric definitions, readings, and summary.
 */

import { apiGet } from "./client";

// -- Types --------------------------------------------------------------------

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

// -- API functions ------------------------------------------------------------

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
