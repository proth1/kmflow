/**
 * Sortable gap list table with severity badges.
 *
 * Displays evidence gaps with color-coded severity indicators
 * (HIGH=red, MEDIUM=orange, LOW=yellow) and optional sorting.
 */
"use client";

import { useState } from "react";

export interface GapEntry {
  id: string;
  gap_type: string;
  description: string;
  severity: string;
  recommendation?: string | null;
}

interface GapTableProps {
  gaps: GapEntry[];
}

const SEVERITY_COLORS: Record<string, { bg: string; text: string }> = {
  high: { bg: "#fef2f2", text: "#dc2626" },
  medium: { bg: "#fff7ed", text: "#ea580c" },
  low: { bg: "#fefce8", text: "#ca8a04" },
};

type SortField = "severity" | "gap_type";
type SortDir = "asc" | "desc";

const SEVERITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

export default function GapTable({ gaps }: GapTableProps) {
  const [sortField, setSortField] = useState<SortField>("severity");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  if (gaps.length === 0) {
    return (
      <div
        style={{ padding: "16px", color: "#9ca3af", textAlign: "center" }}
        data-testid="gap-table-empty"
      >
        No evidence gaps found.
      </div>
    );
  }

  const sorted = [...gaps].sort((a, b) => {
    if (sortField === "severity") {
      const aOrder = SEVERITY_ORDER[a.severity.toLowerCase()] ?? 3;
      const bOrder = SEVERITY_ORDER[b.severity.toLowerCase()] ?? 3;
      return sortDir === "asc" ? aOrder - bOrder : bOrder - aOrder;
    }
    const cmp = a.gap_type.localeCompare(b.gap_type);
    return sortDir === "asc" ? cmp : -cmp;
  });

  function toggleSort(field: SortField) {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  }

  return (
    <div style={{ overflowX: "auto" }} data-testid="gap-table">
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "14px",
        }}
      >
        <thead>
          <tr
            style={{
              borderBottom: "2px solid #e5e7eb",
              textAlign: "left",
            }}
          >
            <th
              style={{ padding: "8px 12px", cursor: "pointer" }}
              onClick={() => toggleSort("severity")}
            >
              Severity {sortField === "severity" ? (sortDir === "asc" ? "\u2191" : "\u2193") : ""}
            </th>
            <th
              style={{ padding: "8px 12px", cursor: "pointer" }}
              onClick={() => toggleSort("gap_type")}
            >
              Type {sortField === "gap_type" ? (sortDir === "asc" ? "\u2191" : "\u2193") : ""}
            </th>
            <th style={{ padding: "8px 12px" }}>Description</th>
            <th style={{ padding: "8px 12px" }}>Recommendation</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((gap) => {
            const severityKey = gap.severity.toLowerCase();
            const colors = SEVERITY_COLORS[severityKey] ?? {
              bg: "#f3f4f6",
              text: "#6b7280",
            };
            return (
              <tr
                key={gap.id}
                style={{ borderBottom: "1px solid #f3f4f6" }}
              >
                <td style={{ padding: "10px 12px" }}>
                  <span
                    style={{
                      display: "inline-block",
                      padding: "2px 10px",
                      borderRadius: "9999px",
                      fontSize: "12px",
                      fontWeight: 600,
                      backgroundColor: colors.bg,
                      color: colors.text,
                      textTransform: "uppercase",
                    }}
                  >
                    {gap.severity}
                  </span>
                </td>
                <td style={{ padding: "10px 12px", color: "#374151" }}>
                  {gap.gap_type.replace(/_/g, " ")}
                </td>
                <td style={{ padding: "10px 12px", color: "#4b5563" }}>
                  {gap.description}
                </td>
                <td style={{ padding: "10px 12px", color: "#6b7280" }}>
                  {gap.recommendation ?? "-"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
