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
    <main
      style={{
        maxWidth: "800px",
        margin: "0 auto",
        padding: "32px 24px",
      }}
    >
      <div style={{ marginBottom: "32px" }}>
        <h1
          style={{
            fontSize: "24px",
            fontWeight: 700,
            margin: "0 0 4px 0",
            color: "#111827",
          }}
        >
          Upload Evidence
        </h1>
        <p style={{ margin: 0, color: "#6b7280", fontSize: "14px" }}>
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
