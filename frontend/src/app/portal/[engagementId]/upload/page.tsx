/**
 * Client Portal - Evidence Upload Page.
 *
 * Allows clients to upload evidence files via drag-and-drop
 * with validation, progress tracking, and upload history.
 */
"use client";

import { useParams } from "next/navigation";
import EvidenceUploader from "@/components/EvidenceUploader";

export default function PortalUploadPage() {
  const params = useParams();
  const engagementId = params.engagementId as string;

  return (
    <main className="mx-auto max-w-3xl px-6 py-8">
      <div className="mb-8">
        <h1 className="mb-1 text-2xl font-bold text-gray-900">
          Upload Evidence
        </h1>
        <p className="text-sm text-gray-500">
          Upload documents, spreadsheets, and images for this engagement.
          Accepted formats: PDF, DOCX, XLSX, CSV, PNG, JPG (max 50MB each).
        </p>
      </div>

      <EvidenceUploader
        engagementId={engagementId}
        onUploadComplete={() => {
          // Could trigger a toast notification or refresh evidence list
        }}
      />
    </main>
  );
}
