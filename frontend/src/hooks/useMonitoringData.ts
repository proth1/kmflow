/**
 * Monitoring data fetching hooks.
 *
 * Provides React hooks for fetching monitoring jobs, alerts,
 * deviations, and stats from the backend API.
 */

import { useCallback, useEffect, useState } from "react";
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

export function useMonitoringStats(engagementId: string) {
  const [stats, setStats] = useState<MonitoringStats | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiGet<MonitoringStats>(
        `/api/v1/monitoring/stats/${engagementId}`,
      );
      setStats(data);
    } catch {
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, [engagementId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { stats, loading, refresh };
}

export function useMonitoringJobs(engagementId: string) {
  const [jobs, setJobs] = useState<MonitoringJob[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiGet<{ items: MonitoringJob[]; total: number }>(
        `/api/v1/monitoring/jobs?engagement_id=${engagementId}`,
      );
      setJobs(data.items);
    } catch {
      setJobs([]);
    } finally {
      setLoading(false);
    }
  }, [engagementId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { jobs, loading, refresh };
}

export function useMonitoringAlerts(engagementId: string) {
  const [alerts, setAlerts] = useState<MonitoringAlert[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiGet<{ items: MonitoringAlert[]; total: number }>(
        `/api/v1/monitoring/alerts?engagement_id=${engagementId}`,
      );
      setAlerts(data.items);
    } catch {
      setAlerts([]);
    } finally {
      setLoading(false);
    }
  }, [engagementId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { alerts, loading, refresh };
}
