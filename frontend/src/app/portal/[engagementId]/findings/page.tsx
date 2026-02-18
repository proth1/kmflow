"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchPortalFindings, type PortalFinding } from "@/lib/api";

const SEVERITY_COLORS: Record<number, { bg: string; text: string; label: string }> = {
  1: { bg: "bg-green-100", text: "text-green-700", label: "Low" },
  2: { bg: "bg-yellow-100", text: "text-yellow-700", label: "Medium" },
  3: { bg: "bg-orange-100", text: "text-orange-700", label: "High" },
  4: { bg: "bg-red-100", text: "text-red-700", label: "Critical" },
};

function SeverityBadge({ severity }: { severity: number }) {
  const config = SEVERITY_COLORS[severity] ?? SEVERITY_COLORS[1];
  return (
    <span className={`inline-block rounded-full px-3 py-0.5 text-xs font-semibold ${config.bg} ${config.text}`}>
      {config.label}
    </span>
  );
}

export default function FindingsPage() {
  const params = useParams();
  const engagementId = params.engagementId as string;
  const [findings, setFindings] = useState<PortalFinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const result = await fetchPortalFindings(engagementId);
        if (!cancelled) {
          setFindings(result.items);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load findings");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [engagementId]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-gray-500">Loading findings...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6">
        <p className="text-sm text-red-600">{error}</p>
      </div>
    );
  }

  return (
    <div>
      <h2 className="mb-6 text-xl font-bold text-gray-900">
        Gap Analysis Findings
      </h2>
      <div className="rounded-lg bg-white shadow">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Dimension
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Gap Type
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Severity
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Recommendation
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200 bg-white">
            {findings.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-6 py-8 text-center text-sm text-gray-500">
                  No findings for this engagement.
                </td>
              </tr>
            ) : (
              findings.map((f) => (
                <tr key={f.id}>
                  <td className="px-6 py-4 text-sm text-gray-900">{f.dimension}</td>
                  <td className="px-6 py-4 text-sm text-gray-600">{f.gap_type.replace(/_/g, " ")}</td>
                  <td className="px-6 py-4">
                    <SeverityBadge severity={f.severity} />
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">{f.recommendation ?? "-"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
