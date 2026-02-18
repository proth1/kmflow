"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { fetchPortalOverview, type PortalOverview } from "@/lib/api";

export default function PortalOverview() {
  const params = useParams();
  const engagementId = params.engagementId as string;

  const [overview, setOverview] = useState<PortalOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!engagementId) return;
    fetchPortalOverview(engagementId)
      .then((data) => {
        setOverview(data);
        setLoading(false);
      })
      .catch((err: Error) => {
        setError(err.message || "Failed to load overview");
        setLoading(false);
      });
  }, [engagementId]);

  return (
    <div>
      <h2 className="mb-6 text-xl font-bold text-gray-900">
        Engagement Overview
      </h2>

      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-sm font-medium text-gray-500">Evidence Items</p>
          <p className="mt-1 text-2xl font-bold text-gray-900">
            {loading ? "-" : (overview?.evidence_count ?? "-")}
          </p>
        </div>
        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-sm font-medium text-gray-500">Process Models</p>
          <p className="mt-1 text-2xl font-bold text-gray-900">
            {loading ? "-" : (overview?.process_model_count ?? "-")}
          </p>
        </div>
        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-sm font-medium text-gray-500">Open Alerts</p>
          <p className="mt-1 text-2xl font-bold text-gray-900">
            {loading ? "-" : (overview?.open_alerts ?? "-")}
          </p>
        </div>
        <div className="rounded-lg bg-white p-4 shadow">
          <p className="text-sm font-medium text-gray-500">Confidence</p>
          <p className="mt-1 text-2xl font-bold text-gray-900">
            {loading
              ? "-"
              : overview?.overall_confidence != null
                ? `${(overview.overall_confidence * 100).toFixed(0)}%`
                : "-"}
          </p>
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
