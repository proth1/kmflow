/**
 * TOM Dashboard Page.
 *
 * Displays TOM alignment analysis with dimension maturity cards,
 * gap prioritization, and regulatory overlay for an engagement.
 */
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import KPICard from "@/components/KPICard";
import TOMDimensionCard from "@/components/TOMDimensionCard";
import RegulatoryOverlay from "@/components/RegulatoryOverlay";
import {
  fetchMaturityScores,
  fetchTOMGaps,
  type TOMAlignmentData,
  type TOMGapList,
} from "@/lib/api";

export default function TOMDashboardPage() {
  const params = useParams();
  const engagementId = params.engagementId as string;

  const [alignment, setAlignment] = useState<TOMAlignmentData | null>(null);
  const [gaps, setGaps] = useState<TOMGapList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showOverlay, setShowOverlay] = useState(false);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        const gapData = await fetchTOMGaps(engagementId);
        setGaps(gapData);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load TOM data",
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
        style={{ maxWidth: "1200px", margin: "0 auto", padding: "32px 24px" }}
      >
        <div
          style={{ textAlign: "center", color: "#6b7280", padding: "48px" }}
        >
          Loading TOM dashboard...
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main
        style={{ maxWidth: "1200px", margin: "0 auto", padding: "32px 24px" }}
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
          <p>{error}</p>
        </div>
      </main>
    );
  }

  const totalGaps = gaps?.total ?? 0;
  const criticalGaps =
    gaps?.items.filter((g) => g.severity > 0.7).length ?? 0;
  const highPriorityGaps =
    gaps?.items.filter((g) => g.priority_score > 0.5).length ?? 0;

  return (
    <main
      style={{ maxWidth: "1200px", margin: "0 auto", padding: "32px 24px" }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "32px",
        }}
      >
        <div>
          <h1
            style={{
              fontSize: "28px",
              fontWeight: 700,
              margin: "0 0 4px 0",
            }}
          >
            TOM Alignment Dashboard
          </h1>
          <p style={{ margin: 0, color: "#6b7280", fontSize: "14px" }}>
            Target Operating Model gap analysis and maturity assessment
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            onClick={() => setShowOverlay(!showOverlay)}
            style={{
              padding: "8px 16px",
              backgroundColor: showOverlay ? "#7e22ce" : "#ffffff",
              color: showOverlay ? "#ffffff" : "#374151",
              border: "1px solid #d1d5db",
              borderRadius: "8px",
              cursor: "pointer",
              fontSize: "13px",
              fontWeight: 500,
            }}
          >
            {showOverlay ? "Hide" : "Show"} Regulatory Overlay
          </button>
          <a
            href={`/roadmap/${engagementId}`}
            style={{
              padding: "8px 16px",
              backgroundColor: "#3b82f6",
              color: "#ffffff",
              border: "none",
              borderRadius: "8px",
              cursor: "pointer",
              fontSize: "13px",
              fontWeight: 500,
              textDecoration: "none",
              display: "inline-flex",
              alignItems: "center",
            }}
          >
            View Roadmap
          </a>
        </div>
      </div>

      {/* KPI Cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: "16px",
          marginBottom: "32px",
        }}
      >
        <KPICard
          label="Total Gaps"
          value={totalGaps}
          status={totalGaps > 5 ? "critical" : totalGaps > 0 ? "warning" : "good"}
          subtitle="across all dimensions"
        />
        <KPICard
          label="Critical Gaps"
          value={criticalGaps}
          status={criticalGaps > 0 ? "critical" : "good"}
          subtitle="severity > 70%"
        />
        <KPICard
          label="High Priority"
          value={highPriorityGaps}
          status={highPriorityGaps > 3 ? "critical" : highPriorityGaps > 0 ? "warning" : "good"}
          subtitle="priority score > 0.5"
        />
        <KPICard
          label="Overall Alignment"
          value={alignment ? `${alignment.overall_alignment.toFixed(0)}%` : "N/A"}
          status={
            alignment
              ? alignment.overall_alignment >= 80
                ? "good"
                : alignment.overall_alignment >= 50
                  ? "warning"
                  : "critical"
              : "neutral"
          }
          subtitle="current vs target"
        />
      </div>

      {/* Dimension Cards */}
      {alignment && (
        <div style={{ marginBottom: "32px" }}>
          <h2
            style={{
              fontSize: "16px",
              fontWeight: 600,
              margin: "0 0 16px 0",
              color: "#111827",
            }}
          >
            Dimension Maturity
          </h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: "16px",
            }}
          >
            {alignment.gaps.map((gap) => (
              <TOMDimensionCard
                key={gap.dimension}
                dimension={gap.dimension}
                currentMaturity={gap.current_maturity}
                targetMaturity={gap.target_maturity}
                gapType={gap.gap_type}
                severity={gap.severity}
              />
            ))}
          </div>
        </div>
      )}

      {/* Gaps Table */}
      {gaps && gaps.items.length > 0 && (
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
            Gap Analysis Results
          </h2>
          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "13px",
              }}
            >
              <thead>
                <tr
                  style={{
                    borderBottom: "2px solid #e5e7eb",
                    textAlign: "left",
                  }}
                >
                  <th style={{ padding: "8px 12px" }}>Dimension</th>
                  <th style={{ padding: "8px 12px" }}>Gap Type</th>
                  <th style={{ padding: "8px 12px" }}>Severity</th>
                  <th style={{ padding: "8px 12px" }}>Priority</th>
                  <th style={{ padding: "8px 12px" }}>Recommendation</th>
                </tr>
              </thead>
              <tbody>
                {gaps.items
                  .sort((a, b) => b.priority_score - a.priority_score)
                  .map((gap) => (
                    <tr
                      key={gap.id}
                      style={{ borderBottom: "1px solid #f3f4f6" }}
                    >
                      <td
                        style={{
                          padding: "10px 12px",
                          color: "#374151",
                          textTransform: "capitalize",
                        }}
                      >
                        {gap.dimension.replace(/_/g, " ")}
                      </td>
                      <td style={{ padding: "10px 12px" }}>
                        <span
                          style={{
                            padding: "2px 8px",
                            borderRadius: "9999px",
                            fontSize: "11px",
                            fontWeight: 600,
                            backgroundColor:
                              gap.gap_type === "full_gap"
                                ? "#fef2f2"
                                : gap.gap_type === "partial_gap"
                                  ? "#fff7ed"
                                  : "#fefce8",
                            color:
                              gap.gap_type === "full_gap"
                                ? "#dc2626"
                                : gap.gap_type === "partial_gap"
                                  ? "#c2410c"
                                  : "#a16207",
                          }}
                        >
                          {gap.gap_type.replace(/_/g, " ")}
                        </span>
                      </td>
                      <td style={{ padding: "10px 12px", color: "#4b5563" }}>
                        {(gap.severity * 100).toFixed(0)}%
                      </td>
                      <td style={{ padding: "10px 12px", color: "#4b5563" }}>
                        {gap.priority_score.toFixed(3)}
                      </td>
                      <td
                        style={{
                          padding: "10px 12px",
                          color: "#6b7280",
                          maxWidth: "300px",
                        }}
                      >
                        {gap.recommendation ?? "-"}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Regulatory Overlay Toggle */}
      {showOverlay && (
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
            Regulatory Governance Overlay
          </h2>
          <RegulatoryOverlay engagementId={engagementId} />
        </div>
      )}
    </main>
  );
}
