/**
 * Monitoring data fetching hooks.
 *
 * Provides React hooks for fetching monitoring jobs, alerts,
 * deviations, and stats from the backend API.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet } from "@/lib/api";

export interface MonitoringJob {
  id: string;
  engagement_id: string;
  name: string;
  source_type: string;
  status: string;
  schedule_cron: string;
  last_run_at: string | null;
}

export interface MonitoringAlert {
  id: string;
  engagement_id: string;
  severity: string;
  status: string;
  title: string;
  description: string;
  created_at: string;
}

export interface ProcessDeviation {
  id: string;
  category: string;
  description: string;
  magnitude: number;
  affected_element: string | null;
  detected_at: string;
}

export interface MonitoringStats {
  active_jobs: number;
  total_deviations: number;
  open_alerts: number;
  critical_alerts: number;
}

function useMonitoringFetch<T>(
  url: string,
  engagementId: string,
  extract: (data: T) => T extends { items: infer U } ? U : T,
  initialValue: T extends { items: infer U } ? U : T,
) {
  type V = T extends { items: infer U } ? U : T;
  const [data, setData] = useState<V>(initialValue);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const result = await apiGet<T>(url);
      if (!controller.signal.aborted) {
        setData(extract(result));
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setData(initialValue);
        setError(err instanceof Error ? err.message : "Failed to load data");
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [url, extract, initialValue]);

  useEffect(() => {
    refresh();
    return () => controllerRef.current?.abort();
  }, [refresh]);

  return { data, loading, error, refresh };
}

const extractIdentity = <T,>(d: T) => d;
const extractItems = <T,>(d: { items: T }) => d.items;

export function useMonitoringStats(engagementId: string) {
  const { data: stats, loading, error, refresh } = useMonitoringFetch<MonitoringStats>(
    `/api/v1/monitoring/stats/${engagementId}`,
    engagementId,
    extractIdentity as (data: MonitoringStats) => MonitoringStats,
    null as unknown as MonitoringStats,
  );
  return { stats, loading, error, refresh };
}

export function useMonitoringJobs(engagementId: string) {
  const { data: jobs, loading, error, refresh } = useMonitoringFetch<{
    items: MonitoringJob[];
    total: number;
  }>(
    `/api/v1/monitoring/jobs?engagement_id=${engagementId}`,
    engagementId,
    extractItems as (data: { items: MonitoringJob[]; total: number }) => MonitoringJob[],
    [] as MonitoringJob[],
  );
  return { jobs, loading, error, refresh };
}

export function useMonitoringAlerts(engagementId: string) {
  const { data: alerts, loading, error, refresh } = useMonitoringFetch<{
    items: MonitoringAlert[];
    total: number;
  }>(
    `/api/v1/monitoring/alerts?engagement_id=${engagementId}`,
    engagementId,
    extractItems as (data: { items: MonitoringAlert[]; total: number }) => MonitoringAlert[],
    [] as MonitoringAlert[],
  );
  return { alerts, loading, error, refresh };
}
