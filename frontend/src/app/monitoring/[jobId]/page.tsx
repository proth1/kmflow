"use client";

import { useParams } from "next/navigation";

export default function MonitoringJobDetail() {
  const params = useParams();
  const jobId = params.jobId as string;

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="mx-auto max-w-7xl">
        <h1 className="mb-6 text-2xl font-bold text-gray-900">
          Monitoring Job: {jobId}
        </h1>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <section className="rounded-lg bg-white p-6 shadow">
            <h2 className="mb-4 text-lg font-semibold">Job Configuration</h2>
            <div className="space-y-2 text-sm text-gray-600">
              <p>
                <strong>Status:</strong> Loading...
              </p>
              <p>
                <strong>Source Type:</strong> Loading...
              </p>
              <p>
                <strong>Schedule:</strong> Loading...
              </p>
              <p>
                <strong>Last Run:</strong> Loading...
              </p>
            </div>
          </section>

          <section className="rounded-lg bg-white p-6 shadow">
            <h2 className="mb-4 text-lg font-semibold">Baseline Drift</h2>
            <div className="flex h-48 items-center justify-center rounded border border-dashed border-gray-300 bg-gray-50">
              <span className="text-gray-400">Drift Chart</span>
            </div>
          </section>
        </div>

        <section className="mt-6 rounded-lg bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold">Recent Deviations</h2>
          <p className="text-sm text-gray-500">
            No deviations detected for this job yet.
          </p>
        </section>
      </div>
    </main>
  );
}
