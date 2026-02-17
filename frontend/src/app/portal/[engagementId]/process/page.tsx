"use client";

import { useParams } from "next/navigation";

export default function ProcessExplorerPage() {
  const params = useParams();
  const engagementId = params.engagementId as string;

  return (
    <div>
      <h2 className="mb-6 text-xl font-bold text-gray-900">
        Process Explorer
      </h2>
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow">
        <p className="text-sm text-gray-500">
          Interactive BPMN viewer with evidence drill-down for engagement{" "}
          {engagementId}
        </p>
        <div className="mt-4 flex h-96 items-center justify-center rounded border border-dashed border-gray-300 bg-gray-50">
          <span className="text-gray-400">BPMN Viewer Area</span>
        </div>
      </div>
    </div>
  );
}
