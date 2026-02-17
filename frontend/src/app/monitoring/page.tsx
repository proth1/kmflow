"use client";

import { useState } from "react";

export default function MonitoringDashboard() {
  const [engagementId, setEngagementId] = useState("");

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

        {engagementId && (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
            <StatCard title="Active Jobs" value="-" />
            <StatCard title="Total Deviations" value="-" />
            <StatCard title="Open Alerts" value="-" />
            <StatCard title="Critical Alerts" value="-" />
          </div>
        )}

        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <section className="rounded-lg bg-white p-6 shadow">
            <h2 className="mb-4 text-lg font-semibold">Recent Deviations</h2>
            <p className="text-sm text-gray-500">
              Connect to an engagement to view deviations
            </p>
          </section>

          <section className="rounded-lg bg-white p-6 shadow">
            <h2 className="mb-4 text-lg font-semibold">Alert Feed</h2>
            <p className="text-sm text-gray-500">
              Connect to an engagement to view alerts
            </p>
          </section>
        </div>
      </div>
    </main>
  );
}

function StatCard({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-lg bg-white p-4 shadow">
      <p className="text-sm font-medium text-gray-500">{title}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
    </div>
  );
}
