/**
 * Engagement Dashboard Page.
 *
 * Shows key metrics, evidence coverage, confidence distribution,
 * gap summary, and recent activity for an engagement.
 */
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import KPICard, { type KPIStatus } from "@/components/KPICard";
import GapTable, { type GapEntry } from "@/components/GapTable";
import ConfidenceBadge from "@/components/ConfidenceBadge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  fetchDashboard,
  fetchEvidenceCoverage,
  fetchConfidenceDistribution,
  fetchCurrentUser,
  type DashboardData,
  type EvidenceCoverageData,
  type ConfidenceDistributionData,
  type UserRole,
} from "@/lib/api";

// Confidence level colors for the bar chart
const CONFIDENCE_LEVEL_COLORS: Record<string, string> = {
  VERY_HIGH: "bg-green-700",
  HIGH: "bg-green-500",
  MEDIUM: "bg-yellow-400",
  LOW: "bg-orange-400",
  VERY_LOW: "bg-red-500",
};

function getKPIStatus(value: number, good: number, warn: number): KPIStatus {
  if (value >= good) return "good";
  if (value >= warn) return "warning";
  return "critical";
}

export default function DashboardPage() {
  const params = useParams();
  const engagementId = params.engagementId as string;

  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [coverage, setCoverage] = useState<EvidenceCoverageData | null>(null);
  const [confidence, setConfidence] =
    useState<ConfidenceDistributionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [userRole, setUserRole] = useState<UserRole>("platform_admin");

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        const [dashData, covData, confData, userData] = await Promise.allSettled([
          fetchDashboard(engagementId),
          fetchEvidenceCoverage(engagementId),
          fetchConfidenceDistribution(engagementId),
          fetchCurrentUser(),
        ]);

        if (dashData.status === "fulfilled") {
          setDashboard(dashData.value);
        } else {
          setError(dashData.reason?.message ?? "Failed to load dashboard");
          return;
        }

        if (covData.status === "fulfilled") setCoverage(covData.value);
        if (confData.status === "fulfilled") setConfidence(confData.value);
        if (userData.status === "fulfilled") setUserRole(userData.value.role);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load dashboard",
        );
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [engagementId]);

  // Persona visibility rules
  const showFullDashboard = userRole !== "client_viewer";

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto p-8">
        <div className="text-center text-[hsl(var(--muted-foreground))] py-12">
          Loading dashboard...
        </div>
      </div>
    );
  }

  if (error || !dashboard) {
    return (
      <div className="max-w-6xl mx-auto p-8">
        <div className="text-center text-red-600 py-12 bg-red-50 rounded-xl border border-red-200">
          <h2 className="text-xl font-semibold mb-2">Error</h2>
          <p>{error ?? "Dashboard data unavailable"}</p>
        </div>
      </div>
    );
  }

  const totalGaps =
    dashboard.gap_counts.high +
    dashboard.gap_counts.medium +
    dashboard.gap_counts.low;

  // Build gap entries for the table from dashboard gap_counts
  const gapEntries: GapEntry[] = [];
  if (dashboard.gap_counts.high > 0) {
    gapEntries.push({
      id: "high-summary",
      gap_type: "mixed",
      description: `${dashboard.gap_counts.high} high-severity gap${dashboard.gap_counts.high !== 1 ? "s" : ""} detected`,
      severity: "high",
      recommendation: "Prioritize evidence collection for these gaps",
    });
  }
  if (dashboard.gap_counts.medium > 0) {
    gapEntries.push({
      id: "medium-summary",
      gap_type: "mixed",
      description: `${dashboard.gap_counts.medium} medium-severity gap${dashboard.gap_counts.medium !== 1 ? "s" : ""} detected`,
      severity: "medium",
      recommendation: "Schedule evidence collection",
    });
  }
  if (dashboard.gap_counts.low > 0) {
    gapEntries.push({
      id: "low-summary",
      gap_type: "mixed",
      description: `${dashboard.gap_counts.low} low-severity gap${dashboard.gap_counts.low !== 1 ? "s" : ""} detected`,
      severity: "low",
      recommendation: "Address when convenient",
    });
  }

  return (
    <div className="max-w-6xl mx-auto p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-1">{dashboard.engagement_name}</h1>
        <p className="text-[hsl(var(--muted-foreground))] text-sm">
          Engagement Dashboard
        </p>
      </div>

      {/* KPI Cards Row */}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-4 mb-8">
        <KPICard
          label="Evidence Coverage"
          value={`${Math.round(dashboard.evidence_coverage_pct)}%`}
          status={getKPIStatus(dashboard.evidence_coverage_pct, 75, 50)}
          subtitle="of requested evidence received"
        />
        <KPICard
          label="Confidence"
          value={`${Math.round(dashboard.overall_confidence * 100)}%`}
          status={getKPIStatus(dashboard.overall_confidence * 100, 75, 50)}
          subtitle="overall model confidence"
        />
        <KPICard
          label="Gaps"
          value={totalGaps}
          status={
            dashboard.gap_counts.high > 0
              ? "critical"
              : totalGaps > 0
                ? "warning"
                : "good"
          }
          subtitle={`${dashboard.gap_counts.high} high severity`}
        />
        <KPICard
          label="Evidence Items"
          value={dashboard.evidence_item_count}
          status="neutral"
          subtitle="uploaded items"
        />
        <KPICard
          label="Process Models"
          value={dashboard.process_model_count}
          status="neutral"
          subtitle="generated POVs"
        />
      </div>

      {/* Two-column layout for charts */}
      <div
        className={`grid gap-6 mb-8 ${showFullDashboard ? "grid-cols-2" : "grid-cols-1"}`}
      >
        {/* Evidence Coverage Chart */}
        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="text-base">Evidence Coverage by Category</CardTitle>
          </CardHeader>
          <CardContent>
            {coverage && coverage.categories.length > 0 ? (
              <div className="flex flex-col gap-2.5">
                {coverage.categories.map((cat) => (
                  <div key={cat.category}>
                    <div className="flex justify-between text-sm mb-1">
                      <span
                        className={cat.below_threshold ? "text-red-600 font-semibold" : "text-[hsl(var(--foreground))]"}
                      >
                        {cat.category.replace(/_/g, " ")}
                      </span>
                      <span className="text-[hsl(var(--muted-foreground))]">
                        {cat.received_count}/{cat.requested_count} (
                        {Math.round(cat.coverage_pct)}%)
                      </span>
                    </div>
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-[width] duration-300 ${
                          cat.below_threshold
                            ? "bg-red-500"
                            : cat.coverage_pct >= 75
                              ? "bg-green-500"
                              : "bg-yellow-400"
                        }`}
                        style={{ width: `${Math.min(cat.coverage_pct, 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-[hsl(var(--muted-foreground))] text-center py-6 text-sm">
                No evidence coverage data available.
              </div>
            )}
          </CardContent>
        </Card>

        {/* Confidence Distribution - hidden for client_viewer */}
        {showFullDashboard && (
          <Card>
            <CardHeader className="pb-4">
              <CardTitle className="text-base">Confidence Distribution</CardTitle>
            </CardHeader>
            <CardContent>
              {confidence && confidence.distribution.length > 0 ? (
                <div>
                  {/* Simple bar chart representation */}
                  <div className="flex flex-col gap-2 mb-4">
                    {confidence.distribution.map((bucket) => {
                      const totalElements = confidence.distribution.reduce(
                        (sum, b) => sum + b.count,
                        0,
                      );
                      const pct =
                        totalElements > 0
                          ? Math.round((bucket.count / totalElements) * 100)
                          : 0;
                      return (
                        <div key={bucket.level}>
                          <div className="flex justify-between text-sm mb-1">
                            <span className="text-[hsl(var(--foreground))]">
                              {bucket.level.replace(/_/g, " ")}
                            </span>
                            <span className="text-[hsl(var(--muted-foreground))]">
                              {bucket.count} ({pct}%)
                            </span>
                          </div>
                          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-[width] duration-300 ${CONFIDENCE_LEVEL_COLORS[bucket.level] ?? "bg-gray-400"}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Weakest elements */}
                  {confidence.weakest_elements.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase tracking-wide mt-4 mb-2">
                        Weakest Elements
                      </h3>
                      <div className="flex flex-col gap-1.5">
                        {confidence.weakest_elements.map((elem) => (
                          <div
                            key={elem.id}
                            className="flex justify-between items-center text-sm px-2 py-1.5 bg-gray-50 rounded-md"
                          >
                            <span className="text-[hsl(var(--foreground))]">{elem.name}</span>
                            <ConfidenceBadge
                              score={elem.confidence_score}
                              showLabel={false}
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-[hsl(var(--muted-foreground))] text-center py-6 text-sm">
                  No confidence data available. Generate a POV first.
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Gaps Summary */}
      <Card className="mb-8">
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Gaps Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <GapTable gaps={gapEntries} />
        </CardContent>
      </Card>

      {/* Recent Activity - hidden for client_viewer */}
      {showFullDashboard && (
        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="text-base">Recent Activity</CardTitle>
          </CardHeader>
          <CardContent>
            {dashboard.recent_activity.length > 0 ? (
              <div className="flex flex-col">
                {dashboard.recent_activity.map((entry, idx) => (
                  <div
                    key={entry.id}
                    className={`flex items-start gap-3 py-3 ${
                      idx < dashboard.recent_activity.length - 1
                        ? "border-b border-gray-100"
                        : ""
                    }`}
                  >
                    {/* Timeline dot */}
                    <div className="w-2 h-2 rounded-full bg-blue-500 mt-1.5 shrink-0" />
                    <div className="flex-1">
                      <div className="text-sm text-[hsl(var(--foreground))] font-medium">
                        {entry.action.replace(/_/g, " ")}
                      </div>
                      {entry.details && (
                        <div className="text-sm text-[hsl(var(--muted-foreground))] mt-0.5">
                          {entry.details}
                        </div>
                      )}
                      <div className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
                        by {entry.actor}
                        {entry.created_at && ` \u2022 ${entry.created_at}`}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-[hsl(var(--muted-foreground))] text-center py-6 text-sm">
                No recent activity.
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
