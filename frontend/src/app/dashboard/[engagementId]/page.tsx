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
import {
  fetchDashboard,
  fetchEvidenceCoverage,
  fetchConfidenceDistribution,
  type DashboardData,
  type EvidenceCoverageData,
  type ConfidenceDistributionData,
} from "@/lib/api";

// Confidence level colors for the donut chart
const CONFIDENCE_LEVEL_COLORS: Record<string, string> = {
  VERY_HIGH: "#15803d",
  HIGH: "#22c55e",
  MEDIUM: "#eab308",
  LOW: "#f97316",
  VERY_LOW: "#ef4444",
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

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        const [dashData, covData, confData] = await Promise.allSettled([
          fetchDashboard(engagementId),
          fetchEvidenceCoverage(engagementId),
          fetchConfidenceDistribution(engagementId),
        ]);

        if (dashData.status === "fulfilled") {
          setDashboard(dashData.value);
        } else {
          setError(dashData.reason?.message ?? "Failed to load dashboard");
          return;
        }

        if (covData.status === "fulfilled") setCoverage(covData.value);
        if (confData.status === "fulfilled") setConfidence(confData.value);
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

  if (loading) {
    return (
      <main
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          padding: "32px 24px",
        }}
      >
        <div style={{ textAlign: "center", color: "#6b7280", padding: "48px" }}>
          Loading dashboard...
        </div>
      </main>
    );
  }

  if (error || !dashboard) {
    return (
      <main
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          padding: "32px 24px",
        }}
      >
        <div
          style={{
            textAlign: "center",
            color: "#dc2626",
            padding: "48px",
            backgroundColor: "#fef2f2",
            borderRadius: "12px",
            border: "1px solid #fecaca",
          }}
        >
          <h2 style={{ margin: "0 0 8px 0" }}>Error</h2>
          <p>{error ?? "Dashboard data unavailable"}</p>
        </div>
      </main>
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
    <main
      style={{
        maxWidth: "1200px",
        margin: "0 auto",
        padding: "32px 24px",
      }}
    >
      {/* Header */}
      <div style={{ marginBottom: "32px" }}>
        <h1 style={{ fontSize: "28px", fontWeight: 700, margin: "0 0 4px 0" }}>
          {dashboard.engagement_name}
        </h1>
        <p style={{ margin: 0, color: "#6b7280", fontSize: "14px" }}>
          Engagement Dashboard
        </p>
      </div>

      {/* KPI Cards Row */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: "16px",
          marginBottom: "32px",
        }}
      >
        <KPICard
          label="Evidence Coverage"
          value={`${Math.round(dashboard.evidence_coverage_pct)}%`}
          status={getKPIStatus(dashboard.evidence_coverage_pct, 75, 50)}
          subtitle="of requested evidence received"
        />
        <KPICard
          label="Confidence"
          value={`${Math.round(dashboard.overall_confidence * 100)}%`}
          status={getKPIStatus(
            dashboard.overall_confidence * 100,
            75,
            50,
          )}
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
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "24px",
          marginBottom: "32px",
        }}
      >
        {/* Evidence Coverage Chart */}
        <div
          style={{
            backgroundColor: "#ffffff",
            border: "1px solid #e5e7eb",
            borderRadius: "12px",
            padding: "24px",
          }}
        >
          <h2
            style={{
              fontSize: "16px",
              fontWeight: 600,
              margin: "0 0 16px 0",
              color: "#111827",
            }}
          >
            Evidence Coverage by Category
          </h2>
          {coverage && coverage.categories.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {coverage.categories.map((cat) => (
                <div key={cat.category}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: "13px",
                      marginBottom: "4px",
                    }}
                  >
                    <span
                      style={{
                        color: cat.below_threshold ? "#dc2626" : "#374151",
                        fontWeight: cat.below_threshold ? 600 : 400,
                      }}
                    >
                      {cat.category.replace(/_/g, " ")}
                    </span>
                    <span style={{ color: "#6b7280" }}>
                      {cat.received_count}/{cat.requested_count} (
                      {Math.round(cat.coverage_pct)}%)
                    </span>
                  </div>
                  <div
                    style={{
                      height: "8px",
                      backgroundColor: "#f3f4f6",
                      borderRadius: "4px",
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        height: "100%",
                        width: `${Math.min(cat.coverage_pct, 100)}%`,
                        backgroundColor: cat.below_threshold
                          ? "#ef4444"
                          : cat.coverage_pct >= 75
                            ? "#22c55e"
                            : "#eab308",
                        borderRadius: "4px",
                        transition: "width 0.3s ease",
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: "#9ca3af", textAlign: "center", padding: "24px" }}>
              No evidence coverage data available.
            </div>
          )}
        </div>

        {/* Confidence Distribution */}
        <div
          style={{
            backgroundColor: "#ffffff",
            border: "1px solid #e5e7eb",
            borderRadius: "12px",
            padding: "24px",
          }}
        >
          <h2
            style={{
              fontSize: "16px",
              fontWeight: 600,
              margin: "0 0 16px 0",
              color: "#111827",
            }}
          >
            Confidence Distribution
          </h2>
          {confidence && confidence.distribution.length > 0 ? (
            <div>
              {/* Simple bar chart representation */}
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "8px",
                  marginBottom: "16px",
                }}
              >
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
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          fontSize: "13px",
                          marginBottom: "4px",
                        }}
                      >
                        <span style={{ color: "#374151" }}>
                          {bucket.level.replace(/_/g, " ")}
                        </span>
                        <span style={{ color: "#6b7280" }}>
                          {bucket.count} ({pct}%)
                        </span>
                      </div>
                      <div
                        style={{
                          height: "8px",
                          backgroundColor: "#f3f4f6",
                          borderRadius: "4px",
                          overflow: "hidden",
                        }}
                      >
                        <div
                          style={{
                            height: "100%",
                            width: `${pct}%`,
                            backgroundColor:
                              CONFIDENCE_LEVEL_COLORS[bucket.level] ?? "#6b7280",
                            borderRadius: "4px",
                            transition: "width 0.3s ease",
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Weakest elements */}
              {confidence.weakest_elements.length > 0 && (
                <div>
                  <h3
                    style={{
                      fontSize: "13px",
                      fontWeight: 600,
                      color: "#6b7280",
                      margin: "16px 0 8px 0",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                    }}
                  >
                    Weakest Elements
                  </h3>
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "6px",
                    }}
                  >
                    {confidence.weakest_elements.map((elem) => (
                      <div
                        key={elem.id}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          fontSize: "13px",
                          padding: "6px 8px",
                          backgroundColor: "#f9fafb",
                          borderRadius: "6px",
                        }}
                      >
                        <span style={{ color: "#374151" }}>{elem.name}</span>
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
            <div style={{ color: "#9ca3af", textAlign: "center", padding: "24px" }}>
              No confidence data available. Generate a POV first.
            </div>
          )}
        </div>
      </div>

      {/* Gaps Summary */}
      <div
        style={{
          backgroundColor: "#ffffff",
          border: "1px solid #e5e7eb",
          borderRadius: "12px",
          padding: "24px",
          marginBottom: "32px",
        }}
      >
        <h2
          style={{
            fontSize: "16px",
            fontWeight: 600,
            margin: "0 0 16px 0",
            color: "#111827",
          }}
        >
          Gaps Summary
        </h2>
        <GapTable gaps={gapEntries} />
      </div>

      {/* Recent Activity */}
      <div
        style={{
          backgroundColor: "#ffffff",
          border: "1px solid #e5e7eb",
          borderRadius: "12px",
          padding: "24px",
        }}
      >
        <h2
          style={{
            fontSize: "16px",
            fontWeight: 600,
            margin: "0 0 16px 0",
            color: "#111827",
          }}
        >
          Recent Activity
        </h2>
        {dashboard.recent_activity.length > 0 ? (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "0",
            }}
          >
            {dashboard.recent_activity.map((entry, idx) => (
              <div
                key={entry.id}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "12px",
                  padding: "12px 0",
                  borderBottom:
                    idx < dashboard.recent_activity.length - 1
                      ? "1px solid #f3f4f6"
                      : "none",
                }}
              >
                {/* Timeline dot */}
                <div
                  style={{
                    width: "8px",
                    height: "8px",
                    borderRadius: "50%",
                    backgroundColor: "#3b82f6",
                    marginTop: "6px",
                    flexShrink: 0,
                  }}
                />
                <div style={{ flex: 1 }}>
                  <div
                    style={{
                      fontSize: "14px",
                      color: "#111827",
                      fontWeight: 500,
                    }}
                  >
                    {entry.action.replace(/_/g, " ")}
                  </div>
                  {entry.details && (
                    <div
                      style={{
                        fontSize: "13px",
                        color: "#6b7280",
                        marginTop: "2px",
                      }}
                    >
                      {entry.details}
                    </div>
                  )}
                  <div
                    style={{
                      fontSize: "12px",
                      color: "#9ca3af",
                      marginTop: "4px",
                    }}
                  >
                    by {entry.actor}
                    {entry.created_at && ` \u2022 ${entry.created_at}`}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ color: "#9ca3af", textAlign: "center", padding: "24px" }}>
            No recent activity.
          </div>
        )}
      </div>
    </main>
  );
}
