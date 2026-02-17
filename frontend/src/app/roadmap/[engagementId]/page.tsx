/**
 * Transformation Roadmap Page.
 *
 * Displays a 4-phase transformation roadmap generated from TOM gap
 * analysis, with timeline visualization and initiative details.
 */
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import RoadmapTimeline from "@/components/RoadmapTimeline";
import KPICard from "@/components/KPICard";
import { fetchRoadmap, type TransformationRoadmap } from "@/lib/api";

export default function RoadmapPage() {
  const params = useParams();
  const engagementId = params.engagementId as string;

  const [roadmap, setRoadmap] = useState<TransformationRoadmap | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tomId, setTomId] = useState<string>("");

  useEffect(() => {
    async function loadData() {
      if (!tomId) {
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const data = await fetchRoadmap(engagementId, tomId);
        setRoadmap(data);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load roadmap",
        );
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [engagementId, tomId]);

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
            Transformation Roadmap
          </h1>
          <p style={{ margin: 0, color: "#6b7280", fontSize: "14px" }}>
            Phased improvement plan based on TOM gap analysis
          </p>
        </div>
        <a
          href={`/tom/${engagementId}`}
          style={{
            padding: "8px 16px",
            backgroundColor: "#ffffff",
            color: "#374151",
            border: "1px solid #d1d5db",
            borderRadius: "8px",
            cursor: "pointer",
            fontSize: "13px",
            fontWeight: 500,
            textDecoration: "none",
          }}
        >
          Back to TOM Dashboard
        </a>
      </div>

      {/* TOM ID input (for selecting which TOM to view roadmap for) */}
      {!roadmap && !loading && (
        <div
          style={{
            backgroundColor: "#ffffff",
            border: "1px solid #e5e7eb",
            borderRadius: "12px",
            padding: "32px",
            textAlign: "center",
            marginBottom: "32px",
          }}
        >
          <h2 style={{ fontSize: "18px", fontWeight: 600, margin: "0 0 16px 0" }}>
            Select Target Operating Model
          </h2>
          <p style={{ color: "#6b7280", marginBottom: "16px" }}>
            Enter a TOM ID to view the transformation roadmap
          </p>
          <div
            style={{ display: "flex", gap: "8px", justifyContent: "center" }}
          >
            <input
              type="text"
              placeholder="TOM ID (UUID)"
              value={tomId}
              onChange={(e) => setTomId(e.target.value)}
              style={{
                padding: "8px 16px",
                border: "1px solid #d1d5db",
                borderRadius: "8px",
                fontSize: "14px",
                width: "320px",
              }}
            />
          </div>
        </div>
      )}

      {loading && (
        <div
          style={{ textAlign: "center", color: "#6b7280", padding: "48px" }}
        >
          Loading roadmap...
        </div>
      )}

      {error && (
        <div
          style={{
            textAlign: "center",
            color: "#dc2626",
            padding: "24px",
            backgroundColor: "#fef2f2",
            borderRadius: "12px",
            border: "1px solid #fecaca",
            marginBottom: "24px",
          }}
        >
          {error}
        </div>
      )}

      {roadmap && (
        <>
          {/* KPI Summary */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
              gap: "16px",
              marginBottom: "32px",
            }}
          >
            <KPICard
              label="Total Initiatives"
              value={roadmap.total_initiatives}
              status={
                roadmap.total_initiatives > 10
                  ? "warning"
                  : roadmap.total_initiatives > 0
                    ? "neutral"
                    : "good"
              }
              subtitle="across all phases"
            />
            <KPICard
              label="Duration"
              value={`${roadmap.estimated_duration_months}mo`}
              status="neutral"
              subtitle="estimated total"
            />
            <KPICard
              label="Quick Wins"
              value={roadmap.phases[0]?.initiatives.length ?? 0}
              status="good"
              subtitle="Phase 1 items"
            />
            <KPICard
              label="Critical Items"
              value={
                roadmap.phases[2]?.initiatives.length ?? 0
              }
              status={
                (roadmap.phases[2]?.initiatives.length ?? 0) > 0
                  ? "critical"
                  : "good"
              }
              subtitle="Phase 3 transformation"
            />
          </div>

          {/* Roadmap Timeline */}
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
                margin: "0 0 20px 0",
                color: "#111827",
              }}
            >
              Implementation Timeline
            </h2>
            <RoadmapTimeline
              phases={roadmap.phases}
              totalInitiatives={roadmap.total_initiatives}
              estimatedMonths={roadmap.estimated_duration_months}
            />
          </div>
        </>
      )}
    </main>
  );
}
