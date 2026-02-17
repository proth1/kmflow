/**
 * Transformation roadmap timeline visualization.
 *
 * Displays a 4-phase roadmap with initiatives grouped by phase,
 * showing dependencies, durations, and priority indicators.
 */
"use client";

import { useState } from "react";
import type { RoadmapPhase, RoadmapInitiative } from "@/lib/api";

interface RoadmapTimelineProps {
  phases: RoadmapPhase[];
  totalInitiatives: number;
  estimatedMonths: number;
}

const PHASE_COLORS: Record<number, { bg: string; accent: string; text: string }> = {
  1: { bg: "#f0fdf4", accent: "#22c55e", text: "#15803d" },
  2: { bg: "#eff6ff", accent: "#3b82f6", text: "#1d4ed8" },
  3: { bg: "#faf5ff", accent: "#a855f7", text: "#7e22ce" },
  4: { bg: "#fff7ed", accent: "#f97316", text: "#c2410c" },
};

function PriorityIndicator({ score }: { score: number }) {
  const color =
    score > 0.7 ? "#dc2626" : score > 0.4 ? "#f59e0b" : "#22c55e";
  return (
    <span
      style={{
        display: "inline-block",
        width: "8px",
        height: "8px",
        borderRadius: "50%",
        backgroundColor: color,
        marginRight: "6px",
      }}
    />
  );
}

function InitiativeRow({ initiative }: { initiative: RoadmapInitiative }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: "8px",
        padding: "8px 12px",
        backgroundColor: "#f9fafb",
        borderRadius: "8px",
        fontSize: "13px",
      }}
    >
      <PriorityIndicator score={initiative.priority_score} />
      <div style={{ flex: 1 }}>
        <div style={{ color: "#374151", fontWeight: 500 }}>
          {initiative.dimension.replace(/_/g, " ")}
        </div>
        <div style={{ color: "#6b7280", marginTop: "2px" }}>
          {initiative.recommendation}
        </div>
      </div>
      <div
        style={{
          fontSize: "11px",
          color: "#9ca3af",
          whiteSpace: "nowrap",
        }}
      >
        {initiative.gap_type.replace(/_/g, " ")}
      </div>
    </div>
  );
}

export default function RoadmapTimeline({
  phases,
  totalInitiatives,
  estimatedMonths,
}: RoadmapTimelineProps) {
  const [expandedPhase, setExpandedPhase] = useState<number | null>(1);

  return (
    <div data-testid="roadmap-timeline">
      {/* Summary bar */}
      <div
        style={{
          display: "flex",
          gap: "24px",
          marginBottom: "24px",
          fontSize: "14px",
          color: "#6b7280",
        }}
      >
        <span>
          <strong style={{ color: "#111827" }}>{totalInitiatives}</strong>{" "}
          initiatives
        </span>
        <span>
          <strong style={{ color: "#111827" }}>{estimatedMonths}</strong> months
          estimated
        </span>
        <span>
          <strong style={{ color: "#111827" }}>{phases.length}</strong> phases
        </span>
      </div>

      {/* Timeline */}
      <div style={{ display: "flex", flexDirection: "column", gap: "0" }}>
        {phases.map((phase) => {
          const colors = PHASE_COLORS[phase.phase_number] ?? PHASE_COLORS[1];
          const isExpanded = expandedPhase === phase.phase_number;

          return (
            <div key={phase.phase_number}>
              {/* Phase header */}
              <button
                onClick={() =>
                  setExpandedPhase(isExpanded ? null : phase.phase_number)
                }
                style={{
                  width: "100%",
                  display: "flex",
                  alignItems: "center",
                  gap: "16px",
                  padding: "16px 20px",
                  backgroundColor: colors.bg,
                  border: "none",
                  borderLeft: `4px solid ${colors.accent}`,
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                {/* Phase number circle */}
                <div
                  style={{
                    width: "32px",
                    height: "32px",
                    borderRadius: "50%",
                    backgroundColor: colors.accent,
                    color: "#ffffff",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 700,
                    fontSize: "14px",
                    flexShrink: 0,
                  }}
                >
                  {phase.phase_number}
                </div>
                <div style={{ flex: 1 }}>
                  <div
                    style={{
                      fontSize: "15px",
                      fontWeight: 600,
                      color: colors.text,
                    }}
                  >
                    {phase.name}
                  </div>
                  <div style={{ fontSize: "12px", color: "#6b7280" }}>
                    {phase.duration_months} months &middot;{" "}
                    {phase.initiatives.length} initiative
                    {phase.initiatives.length !== 1 ? "s" : ""}
                  </div>
                </div>
                <span
                  style={{
                    fontSize: "18px",
                    color: "#9ca3af",
                    transform: isExpanded ? "rotate(180deg)" : "none",
                    transition: "transform 0.2s",
                  }}
                >
                  &#9660;
                </span>
              </button>

              {/* Phase initiatives */}
              {isExpanded && (
                <div
                  style={{
                    borderLeft: `4px solid ${colors.accent}`,
                    padding: "12px 20px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "8px",
                    backgroundColor: "#ffffff",
                  }}
                >
                  {phase.initiatives.length > 0 ? (
                    phase.initiatives.map((init, idx) => (
                      <InitiativeRow key={idx} initiative={init} />
                    ))
                  ) : (
                    <div
                      style={{
                        padding: "16px",
                        color: "#9ca3af",
                        textAlign: "center",
                        fontSize: "13px",
                      }}
                    >
                      No initiatives in this phase.
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
