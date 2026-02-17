"use client";

import { useParams } from "next/navigation";

export default function PortalOverview() {
  const params = useParams();
  const engagementId = params.engagementId as string;

  return (
    <div>
      <h2 className="mb-6 text-xl font-bold text-gray-900">
        Engagement Overview
      </h2>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-sm font-medium text-gray-500">Evidence Items</p>
          <p className="mt-1 text-2xl font-bold text-gray-900">-</p>
        </div>
        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-sm font-medium text-gray-500">Process Models</p>
          <p className="mt-1 text-2xl font-bold text-gray-900">-</p>
        </div>
        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-sm font-medium text-gray-500">Open Alerts</p>
          <p className="mt-1 text-2xl font-bold text-gray-900">-</p>
        </div>
        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-sm font-medium text-gray-500">Confidence</p>
          <p className="mt-1 text-2xl font-bold text-gray-900">-</p>
        </div>
      </div>

      <div className="mt-6 text-sm text-gray-500">
        Engagement: {engagementId}
      </div>

      <nav className="mt-8 flex gap-4">
        <a
          href={`/portal/${engagementId}/process`}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Process Explorer
        </a>
        <a
          href={`/portal/${engagementId}/findings`}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Findings
        </a>
        <a
          href={`/portal/${engagementId}/evidence`}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Evidence Status
        </a>
      </nav>
    </div>
  );
}
