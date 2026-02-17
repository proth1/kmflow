"use client";

export default function PortalHome() {
  return (
    <div>
      <h2 className="mb-4 text-xl font-bold text-gray-900">
        Welcome to KMFlow Client Portal
      </h2>
      <p className="mb-6 text-gray-600">
        Select an engagement to view process intelligence findings, evidence
        status, and monitoring data.
      </p>
      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <p className="text-sm text-gray-500">
          Navigate to /portal/[engagementId] to view engagement details
        </p>
      </div>
    </div>
  );
}
