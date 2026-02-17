/**
 * Regulatory governance overlay visualization.
 *
 * Displays compliance state, policy coverage gauge, and
 * lists ungoverned processes requiring attention.
 */
"use client";

import { useEffect, useState } from "react";
import type { ComplianceStateData, UngovernedProcess } from "@/lib/api";
import { fetchComplianceState, fetchUngovernedProcesses } from "@/lib/api";

interface RegulatoryOverlayProps {
  engagementId: string;
}

const COMPLIANCE_COLORS: Record<string, { bg: string; text: string }> = {
  fully_compliant: { bg: "#f0fdf4", text: "#15803d" },
  partially_compliant: { bg: "#fefce8", text: "#a16207" },
  non_compliant: { bg: "#fef2f2", text: "#dc2626" },
  not_assessed: { bg: "#f3f4f6", text: "#6b7280" },
};

export default function RegulatoryOverlay({
  engagementId,
}: RegulatoryOverlayProps) {
  const [compliance, setCompliance] = useState<ComplianceStateData | null>(
    null,
  );
  const [ungoverned, setUngoverned] = useState<UngovernedProcess[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [compData, ungovData] = await Promise.allSettled([
          fetchComplianceState(engagementId),
          fetchUngovernedProcesses(engagementId),
        ]);

        if (compData.status === "fulfilled") setCompliance(compData.value);
        if (ungovData.status === "fulfilled")
          setUngoverned(ungovData.value.ungoverned);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load overlay",
        );
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [engagementId]);

  if (loading) {
    return (
      <div
        style={{ padding: "24px", color: "#6b7280", textAlign: "center" }}
        data-testid="regulatory-overlay-loading"
      >
        Loading regulatory overlay...
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          padding: "24px",
          color: "#dc2626",
          backgroundColor: "#fef2f2",
          borderRadius: "12px",
          textAlign: "center",
        }}
        data-testid="regulatory-overlay-error"
      >
        {error}
      </div>
    );
  }

  const level = compliance?.level ?? "not_assessed";
  const colors = COMPLIANCE_COLORS[level] ?? COMPLIANCE_COLORS.not_assessed;
  const coverage = compliance?.policy_coverage ?? 0;

  return (
    <div data-testid="regulatory-overlay">
      {/* Compliance Status */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "16px",
          marginBottom: "24px",
        }}
      >
        {/* Level Badge */}
        <div
          style={{
            backgroundColor: colors.bg,
            border: `1px solid ${colors.text}20`,
            borderRadius: "12px",
            padding: "20px",
            textAlign: "center",
          }}
        >
          <div
            style={{
              fontSize: "12px",
              color: "#6b7280",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginBottom: "8px",
            }}
          >
            Compliance Level
          </div>
          <div
            style={{
              fontSize: "18px",
              fontWeight: 700,
              color: colors.text,
              textTransform: "uppercase",
            }}
          >
            {level.replace(/_/g, " ")}
          </div>
        </div>

        {/* Coverage Gauge */}
        <div
          style={{
            backgroundColor: "#ffffff",
            border: "1px solid #e5e7eb",
            borderRadius: "12px",
            padding: "20px",
            textAlign: "center",
          }}
        >
          <div
            style={{
              fontSize: "12px",
              color: "#6b7280",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginBottom: "8px",
            }}
          >
            Policy Coverage
          </div>
          <div
            style={{
              fontSize: "28px",
              fontWeight: 700,
              color: coverage >= 90 ? "#15803d" : coverage >= 50 ? "#a16207" : "#dc2626",
            }}
          >
            {coverage.toFixed(1)}%
          </div>
          <div
            style={{
              height: "8px",
              backgroundColor: "#f3f4f6",
              borderRadius: "4px",
              marginTop: "8px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${Math.min(coverage, 100)}%`,
                backgroundColor:
                  coverage >= 90
                    ? "#22c55e"
                    : coverage >= 50
                      ? "#eab308"
                      : "#ef4444",
                borderRadius: "4px",
                transition: "width 0.3s ease",
              }}
            />
          </div>
        </div>
      </div>

      {/* Process Counts */}
      {compliance && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr 1fr",
            gap: "12px",
            marginBottom: "24px",
          }}
        >
          <div
            style={{
              textAlign: "center",
              padding: "12px",
              backgroundColor: "#f9fafb",
              borderRadius: "8px",
            }}
          >
            <div style={{ fontSize: "24px", fontWeight: 700, color: "#111827" }}>
              {compliance.total_processes}
            </div>
            <div style={{ fontSize: "12px", color: "#6b7280" }}>
              Total Processes
            </div>
          </div>
          <div
            style={{
              textAlign: "center",
              padding: "12px",
              backgroundColor: "#f0fdf4",
              borderRadius: "8px",
            }}
          >
            <div style={{ fontSize: "24px", fontWeight: 700, color: "#15803d" }}>
              {compliance.governed_count}
            </div>
            <div style={{ fontSize: "12px", color: "#6b7280" }}>Governed</div>
          </div>
          <div
            style={{
              textAlign: "center",
              padding: "12px",
              backgroundColor: "#fef2f2",
              borderRadius: "8px",
            }}
          >
            <div style={{ fontSize: "24px", fontWeight: 700, color: "#dc2626" }}>
              {compliance.ungoverned_count}
            </div>
            <div style={{ fontSize: "12px", color: "#6b7280" }}>Ungoverned</div>
          </div>
        </div>
      )}

      {/* Ungoverned Processes List */}
      {ungoverned.length > 0 && (
        <div>
          <h3
            style={{
              fontSize: "14px",
              fontWeight: 600,
              color: "#dc2626",
              margin: "0 0 12px 0",
            }}
          >
            Ungoverned Processes ({ungoverned.length})
          </h3>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "6px",
            }}
          >
            {ungoverned.map((proc) => (
              <div
                key={proc.process_id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "8px 12px",
                  backgroundColor: "#fef2f2",
                  borderRadius: "8px",
                  fontSize: "13px",
                }}
              >
                <span
                  style={{
                    width: "6px",
                    height: "6px",
                    borderRadius: "50%",
                    backgroundColor: "#dc2626",
                    flexShrink: 0,
                  }}
                />
                <span style={{ color: "#374151" }}>
                  {proc.process_name || proc.process_id}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
