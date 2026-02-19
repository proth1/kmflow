"use client";

import { useState } from "react";
import {
  fetchEngagementReport,
  fetchGapReport,
  fetchGovernanceReport,
  API_BASE_URL,
  type ReportResponse,
} from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { FileText, Download, RefreshCw, AlertCircle } from "lucide-react";

type ReportType = "summary" | "gap-analysis" | "governance" | "executive-summary";

const reportOptions: { type: ReportType; label: string; description: string }[] = [
  {
    type: "summary",
    label: "Engagement Summary",
    description: "Overview of evidence, processes, and confidence scores",
  },
  {
    type: "gap-analysis",
    label: "Gap Analysis",
    description: "TOM gaps, severity breakdown, and recommendations",
  },
  {
    type: "governance",
    label: "Governance Overlay",
    description: "Regulatory compliance and policy coverage",
  },
  {
    type: "executive-summary",
    label: "Executive Summary",
    description: "Combined report with all three sections",
  },
];

export default function ReportsPage() {
  const [engagementId, setEngagementId] = useState("");
  const [loading, setLoading] = useState<ReportType | null>(null);
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [activeType, setActiveType] = useState<ReportType | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function generateReport(type: ReportType) {
    if (!engagementId || engagementId.length < 8) return;

    setLoading(type);
    setError(null);
    setReport(null);

    try {
      let result: ReportResponse;
      switch (type) {
        case "summary":
          result = await fetchEngagementReport(engagementId);
          break;
        case "gap-analysis":
          result = await fetchGapReport(engagementId);
          break;
        case "governance":
          result = await fetchGovernanceReport(engagementId);
          break;
        case "executive-summary":
          result = await fetchEngagementReport(engagementId);
          break;
        default:
          return;
      }
      setReport(result);
      setActiveType(type);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to generate report",
      );
    } finally {
      setLoading(null);
    }
  }

  function downloadPdf(type: ReportType) {
    if (!engagementId) return;
    window.open(
      `${API_BASE_URL}/api/v1/reports/${engagementId}/${type}?format=pdf`,
      "_blank",
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Reports</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Generate and export engagement reports in JSON, HTML, or PDF
          </p>
        </div>
        <FileText className="h-8 w-8 text-muted-foreground" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Engagement</CardTitle>
          <CardDescription>
            Select an engagement to generate reports for
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

      {error && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-destructive mt-0.5" />
              <p className="text-sm text-destructive">{error}</p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {reportOptions.map((opt) => (
          <Card key={opt.type}>
            <CardHeader>
              <CardTitle className="text-lg">{opt.label}</CardTitle>
              <CardDescription>{opt.description}</CardDescription>
            </CardHeader>
            <CardContent className="flex gap-2">
              <Button
                size="sm"
                onClick={() => generateReport(opt.type)}
                disabled={
                  !engagementId ||
                  engagementId.length < 8 ||
                  loading !== null
                }
              >
                {loading === opt.type ? (
                  <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" />
                ) : (
                  <FileText className="h-3 w-3 mr-1.5" />
                )}
                Generate JSON
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => downloadPdf(opt.type)}
                disabled={!engagementId || engagementId.length < 8}
              >
                <Download className="h-3 w-3 mr-1.5" />
                PDF
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      {report && activeType && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>
                  {reportOptions.find((r) => r.type === activeType)?.label} Report
                </CardTitle>
                <CardDescription>
                  Generated at {report.generated_at}
                </CardDescription>
              </div>
              <Badge variant="outline">{report.report_type}</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <pre className="bg-muted rounded-lg p-4 text-xs overflow-auto max-h-[600px]">
              {JSON.stringify(report.data, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
