"use client";

import { useState, useCallback } from "react";
import {
  fetchMonitoringStats,
  fetchDeviations,
  fetchAlerts,
  type MonitoringStats,
  type DeviationData,
  type AlertData,
} from "@/lib/api";
import { isValidEngagementId } from "@/lib/validation";
import { PageLayout } from "@/components/layout/PageLayout";
import { useEngagementData } from "@/hooks/useEngagementData";
import { ComponentErrorBoundary } from "@/components/ComponentErrorBoundary";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Activity } from "lucide-react";

interface MonitoringData {
  stats: MonitoringStats;
  deviations: DeviationData[];
  alerts: AlertData[];
}

function MonitoringDashboardInner() {
  const [engagementId, setEngagementId] = useState("");

  const fetchMonitoringData = useCallback(
    async (id: string) => {
      const [statsResult, devResult, alertResult] = await Promise.all([
        fetchMonitoringStats(id),
        fetchDeviations(id),
        fetchAlerts(id),
      ]);
      return {
        stats: statsResult,
        deviations: devResult.items.slice(0, 10),
        alerts: alertResult.items.slice(0, 10),
      } as MonitoringData;
    },
    [],
  );

  const { data, loading, error } = useEngagementData<MonitoringData>(
    engagementId,
    fetchMonitoringData,
  );

  const stats = data?.stats ?? null;
  const deviations = data?.deviations ?? [];
  const alerts = data?.alerts ?? [];

  const idError =
    engagementId.length > 0 && !isValidEngagementId(engagementId)
      ? "Invalid engagement ID format"
      : null;

  return (
    <PageLayout
      title="Monitoring Dashboard"
      description="Real-time monitoring of process deviations and alerts"
      icon={<Activity className="h-8 w-8 text-muted-foreground" />}
      engagementId={engagementId}
      onEngagementIdChange={setEngagementId}
      engagementIdError={idError}
      error={error}
      loading={loading}
      loadingText="Loading monitoring data..."
    >
      {stats && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Active Jobs</CardDescription>
              <CardTitle className="text-3xl">{stats.active_jobs}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Total Deviations</CardDescription>
              <CardTitle className="text-3xl">{stats.total_deviations}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Open Alerts</CardDescription>
              <CardTitle className="text-3xl">{stats.open_alerts}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Critical Alerts</CardDescription>
              <CardTitle className={`text-3xl ${stats.critical_alerts > 0 ? "text-red-600" : ""}`}>
                {stats.critical_alerts}
              </CardTitle>
            </CardHeader>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Recent Deviations</CardTitle>
          </CardHeader>
          <CardContent>
            {deviations.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                {engagementId ? "No deviations detected" : "Enter an engagement ID to view deviations"}
              </p>
            ) : (
              <ul className="space-y-3">
                {deviations.map((d) => (
                  <li key={d.id} className="border-b pb-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">
                        {d.category}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {new Date(d.detected_at).toLocaleDateString()}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">{d.description}</p>
                    {d.affected_element && (
                      <p className="text-xs text-muted-foreground">Element: {d.affected_element}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Alert Feed</CardTitle>
          </CardHeader>
          <CardContent>
            {alerts.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                {engagementId ? "No alerts" : "Enter an engagement ID to view alerts"}
              </p>
            ) : (
              <ul className="space-y-3">
                {alerts.map((a) => (
                  <li key={a.id} className="border-b pb-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">{a.title}</span>
                      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                        a.severity === "critical" ? "bg-red-100 text-red-700" :
                        a.severity === "high" ? "bg-orange-100 text-orange-700" :
                        a.severity === "warning" ? "bg-yellow-100 text-yellow-700" :
                        "bg-blue-100 text-blue-700"
                      }`}>
                        {a.severity}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">{a.description}</p>
                    <p className="text-xs text-muted-foreground">
                      Status: {a.status} | {new Date(a.created_at).toLocaleDateString()}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </PageLayout>
  );
}

export default function MonitoringDashboard() {
  return (
    <ComponentErrorBoundary componentName="MonitoringDashboard">
      <MonitoringDashboardInner />
    </ComponentErrorBoundary>
  );
}
