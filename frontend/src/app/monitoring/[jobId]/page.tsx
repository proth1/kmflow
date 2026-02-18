"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  fetchMonitoringJob,
  fetchDeviations,
  type MonitoringJobData,
  type DeviationData,
} from "@/lib/api";

export default function MonitoringJobDetail() {
  const params = useParams();
  const jobId = params.jobId as string;
  const [job, setJob] = useState<MonitoringJobData | null>(null);
  const [deviations, setDeviations] = useState<DeviationData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const jobData = await fetchMonitoringJob(jobId);
        const devResult = await fetchDeviations(jobData.engagement_id);
        if (!cancelled) {
          setJob(jobData);
          setDeviations(devResult.items.filter((d) => d.monitoring_job_id === jobId));
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load job details");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [jobId]);

  if (loading) {
    return (
      <main className="min-h-screen bg-gray-50 p-8">
        <div className="mx-auto max-w-7xl">
          <p className="text-sm text-gray-500">Loading job details...</p>
        </div>
      </main>
    );
  }

  if (error || !job) {
    return (
      <main className="min-h-screen bg-gray-50 p-8">
        <div className="mx-auto max-w-7xl">
          <div className="rounded-lg border border-red-200 bg-red-50 p-6">
            <p className="text-sm text-red-600">{error ?? "Job not found"}</p>
          </div>
        </div>
      </main>
    );
  }

  const statusColor = job.status === "active" ? "text-green-600" :
    job.status === "error" ? "text-red-600" : "text-gray-600";

  // Build drift data from deviations for chart
  const driftData = deviations
    .sort((a, b) => new Date(a.detected_at).getTime() - new Date(b.detected_at).getTime())
    .map((d) => ({
      date: new Date(d.detected_at).toLocaleDateString(),
      magnitude: d.magnitude,
    }));

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="mx-auto max-w-7xl">
        <h1 className="mb-6 text-2xl font-bold text-gray-900">
          Monitoring Job: {job.name}
        </h1>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <section className="rounded-lg bg-white p-6 shadow">
            <h2 className="mb-4 text-lg font-semibold">Job Configuration</h2>
            <div className="space-y-2 text-sm text-gray-600">
              <p>
                <strong>Status:</strong>{" "}
                <span className={statusColor}>{job.status}</span>
              </p>
              <p><strong>Source Type:</strong> {job.source_type}</p>
              <p><strong>Schedule:</strong> {job.schedule_cron}</p>
              <p><strong>Last Run:</strong> {job.last_run_at ? new Date(job.last_run_at).toLocaleString() : "Never"}</p>
              <p><strong>Next Run:</strong> {job.next_run_at ? new Date(job.next_run_at).toLocaleString() : "Not scheduled"}</p>
              {job.error_message && (
                <p className="text-red-600"><strong>Error:</strong> {job.error_message}</p>
              )}
            </div>
          </section>

          <section className="rounded-lg bg-white p-6 shadow">
            <h2 className="mb-4 text-lg font-semibold">Baseline Drift</h2>
            {driftData.length === 0 ? (
              <div className="flex h-48 items-center justify-center rounded border border-dashed border-gray-300 bg-gray-50">
                <span className="text-gray-400">No drift data available</span>
              </div>
            ) : (
              <div className="space-y-2">
                {driftData.map((d, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="w-24 text-xs text-gray-500">{d.date}</span>
                    <div className="h-3 flex-1 rounded bg-gray-200">
                      <div
                        className="h-3 rounded bg-orange-500"
                        style={{ width: `${Math.min(d.magnitude * 100, 100)}%` }}
                      />
                    </div>
                    <span className="w-12 text-right text-xs text-gray-500">
                      {(d.magnitude * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>

        <section className="mt-6 rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold">
            Recent Deviations ({deviations.length})
          </h2>
          {deviations.length === 0 ? (
            <p className="text-sm text-gray-500">
              No deviations detected for this job yet.
            </p>
          ) : (
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">Category</th>
                  <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">Description</th>
                  <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">Element</th>
                  <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">Magnitude</th>
                  <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">Detected</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {deviations.map((d) => (
                  <tr key={d.id}>
                    <td className="px-4 py-2 text-sm text-gray-900">{d.category}</td>
                    <td className="px-4 py-2 text-sm text-gray-600">{d.description}</td>
                    <td className="px-4 py-2 text-sm text-gray-500">{d.affected_element ?? "-"}</td>
                    <td className="px-4 py-2 text-sm text-gray-500">{(d.magnitude * 100).toFixed(0)}%</td>
                    <td className="px-4 py-2 text-sm text-gray-400">{new Date(d.detected_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </main>
  );
}
