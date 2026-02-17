"use client";

import { useParams } from "next/navigation";

export default function EvidenceStatusPage() {
  const params = useParams();
  const engagementId = params.engagementId as string;

  return (
    <div>
      <h2 className="mb-6 text-xl font-bold text-gray-900">
        Evidence Status
      </h2>
      <div className="rounded-lg bg-white p-6 shadow">
        <p className="mb-4 text-sm text-gray-500">
          Evidence coverage by category for engagement {engagementId}
        </p>
        <div className="space-y-3">
          {[
            "Documents",
            "Structured Data",
            "BPM Process Models",
            "Controls Evidence",
            "Domain Communications",
          ].map((cat) => (
            <div key={cat} className="flex items-center gap-4">
              <span className="w-48 text-sm font-medium text-gray-700">
                {cat}
              </span>
              <div className="h-4 flex-1 rounded bg-gray-200">
                <div className="h-4 rounded bg-blue-500" style={{ width: "0%" }} />
              </div>
              <span className="w-12 text-right text-sm text-gray-500">0</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
