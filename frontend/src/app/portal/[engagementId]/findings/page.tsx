"use client";

import { useParams } from "next/navigation";

export default function FindingsPage() {
  const params = useParams();
  const engagementId = params.engagementId as string;

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
            <tr>
              <td
                colSpan={4}
                className="px-6 py-8 text-center text-sm text-gray-500"
              >
                Loading findings for {engagementId}...
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
