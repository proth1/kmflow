"use client";

import { useState, useEffect } from "react";
import {
  fetchMonitoringStats,
  fetchDeviations,
  fetchAlerts,
  type MonitoringStats,
  type DeviationData,
  type AlertData,
} from "@/lib/api";

function StatCard({ title, value, highlight }: { title: string; value: string | number; highlight?: boolean }) {
  return (
    <div className="rounded-lg bg-white p-4 shadow">
      <p className="text-sm font-medium text-gray-500">{title}</p>
      <p className={`mt-1 text-2xl font-bold ${highlight ? "text-red-600" : "text-gray-900"}`}>
        {value}
      </p>
    </div>
  );
}

export default function MonitoringDashboard() {
  const [engagementId, setEngagementId] = useState("");
  const [stats, setStats] = useState<MonitoringStats | null>(null);
  const [deviations, setDeviations] = useState<DeviationData[]>([]);
  const [alerts, setAlerts] = useState<AlertData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!engagementId || engagementId.length < 8) return;

    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [statsResult, devResult, alertResult] = await Promise.all([
          fetchMonitoringStats(engagementId),
          fetchDeviations(engagementId),
          fetchAlerts(engagementId),
        ]);
        if (!cancelled) {
          setStats(statsResult);
          setDeviations(devResult.items.slice(0, 10));
          setAlerts(alertResult.items.slice(0, 10));
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load monitoring data");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [engagementId]);

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="mx-auto max-w-7xl">
        <h1 className="mb-6 text-2xl font-bold text-gray-900">
          Monitoring Dashboard
        </h1>

        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700">
            Engagement ID
          </label>
          <input
            type="text"
            value={engagementId}
            onChange={(e) => setEngagementId(e.target.value)}
            placeholder="Enter engagement UUID"
            className="mt-1 block w-full max-w-md rounded-md border border-gray-300 p-2 text-sm"
          />
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        )}

        {loading && (
          <p className="mb-6 text-sm text-gray-500">Loading monitoring data...</p>
        )}

        {stats && (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
            <StatCard title="Active Jobs" value={stats.active_jobs} />
            <StatCard title="Total Deviations" value={stats.total_deviations} />
            <StatCard title="Open Alerts" value={stats.open_alerts} />
            <StatCard title="Critical Alerts" value={stats.critical_alerts} highlight={stats.critical_alerts > 0} />
          </div>
        )}

        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <section className="rounded-lg bg-white p-6 shadow">
            <h2 className="mb-4 text-lg font-semibold">Recent Deviations</h2>
            {deviations.length === 0 ? (
              <p className="text-sm text-gray-500">
                {engagementId ? "No deviations detected" : "Connect to an engagement to view deviations"}
              </p>
            ) : (
              <ul className="space-y-3">
                {deviations.map((d) => (
                  <li key={d.id} className="border-b border-gray-100 pb-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-gray-800">
                        {d.category}
                      </span>
                      <span className="text-xs text-gray-400">
                        {new Date(d.detected_at).toLocaleDateString()}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500">{d.description}</p>
                    {d.affected_element && (
                      <p className="text-xs text-gray-400">Element: {d.affected_element}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="rounded-lg bg-white p-6 shadow">
            <h2 className="mb-4 text-lg font-semibold">Alert Feed</h2>
            {alerts.length === 0 ? (
              <p className="text-sm text-gray-500">
                {engagementId ? "No alerts" : "Connect to an engagement to view alerts"}
              </p>
            ) : (
              <ul className="space-y-3">
                {alerts.map((a) => (
                  <li key={a.id} className="border-b border-gray-100 pb-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-gray-800">{a.title}</span>
                      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                        a.severity === "critical" ? "bg-red-100 text-red-700" :
                        a.severity === "high" ? "bg-orange-100 text-orange-700" :
                        a.severity === "warning" ? "bg-yellow-100 text-yellow-700" :
                        "bg-blue-100 text-blue-700"
                      }`}>
                        {a.severity}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500">{a.description}</p>
                    <p className="text-xs text-gray-400">
                      Status: {a.status} | {new Date(a.created_at).toLocaleDateString()}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
