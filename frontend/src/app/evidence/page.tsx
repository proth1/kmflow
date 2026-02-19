"use client";

import { useState } from "react";
import EvidenceUploader from "@/components/EvidenceUploader";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export default function EvidenceUploadPage() {
  const [engagementId, setEngagementId] = useState("");

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight mb-1">
          Evidence Upload
        </h1>
        <p className="text-[hsl(var(--muted-foreground))] text-base">
          Ingest client evidence across 12 categories for processing and analysis
        </p>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-lg">Engagement</CardTitle>
          <CardDescription>
            Enter the engagement ID to upload evidence against
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Input
            type="text"
            value={engagementId}
            onChange={(e) => setEngagementId(e.target.value)}
            placeholder="Enter engagement UUID"
            className="max-w-md"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Upload Files</CardTitle>
          <CardDescription>
            Drag and drop files or click to browse. Accepted formats: PDF, DOCX,
            XLSX, CSV, PNG, JPG.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {engagementId.length >= 8 ? (
            <EvidenceUploader engagementId={engagementId} />
          ) : (
            <div className="border-2 border-dashed border-[hsl(var(--border))] rounded-xl p-12 text-center">
              <p className="text-[hsl(var(--muted-foreground))] text-sm">
                Enter a valid engagement ID above to enable file uploads
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
