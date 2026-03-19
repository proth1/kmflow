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
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet<MonitoringStats>(
        `/api/v1/monitoring/stats/${engagementId}`,
      );
      if (!controller.signal.aborted) {
        setStats(data);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setStats(null);
        setError(err instanceof Error ? err.message : "Failed to load data");
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
    return () => controller.abort();
  }, [engagementId]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    apiGet<MonitoringStats>(`/api/v1/monitoring/stats/${engagementId}`)
      .then((data) => {
        if (!controller.signal.aborted) {
          setStats(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setStats(null);
          setError(err instanceof Error ? err.message : "Failed to load data");
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [engagementId]);

  return { stats, loading, error, refresh };
}

export function useMonitoringJobs(engagementId: string) {
  const [jobs, setJobs] = useState<MonitoringJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet<{ items: MonitoringJob[]; total: number }>(
        `/api/v1/monitoring/jobs?engagement_id=${engagementId}`,
      );
      if (!controller.signal.aborted) {
        setJobs(data.items);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setJobs([]);
        setError(err instanceof Error ? err.message : "Failed to load data");
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
    return () => controller.abort();
  }, [engagementId]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    apiGet<{ items: MonitoringJob[]; total: number }>(
      `/api/v1/monitoring/jobs?engagement_id=${engagementId}`,
    )
      .then((data) => {
        if (!controller.signal.aborted) {
          setJobs(data.items);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setJobs([]);
          setError(err instanceof Error ? err.message : "Failed to load data");
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [engagementId]);

  return { jobs, loading, error, refresh };
}

export function useMonitoringAlerts(engagementId: string) {
  const [alerts, setAlerts] = useState<MonitoringAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet<{ items: MonitoringAlert[]; total: number }>(
        `/api/v1/monitoring/alerts?engagement_id=${engagementId}`,
      );
      if (!controller.signal.aborted) {
        setAlerts(data.items);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setAlerts([]);
        setError(err instanceof Error ? err.message : "Failed to load data");
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
    return () => controller.abort();
  }, [engagementId]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    apiGet<{ items: MonitoringAlert[]; total: number }>(
      `/api/v1/monitoring/alerts?engagement_id=${engagementId}`,
    )
      .then((data) => {
        if (!controller.signal.aborted) {
          setAlerts(data.items);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setAlerts([]);
          setError(err instanceof Error ? err.message : "Failed to load data");
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [engagementId]);

  return { alerts, loading, error, refresh };
}
