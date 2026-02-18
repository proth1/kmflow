/**
 * Sortable gap list table with severity badges.
 *
 * Displays evidence gaps with color-coded severity indicators
 * (HIGH=red, MEDIUM=orange, LOW=yellow) and optional sorting.
 */
"use client";

import { useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

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

const SEVERITY_CLASSES: Record<string, string> = {
  high: "bg-red-50 text-red-600",
  medium: "bg-orange-50 text-orange-600",
  low: "bg-yellow-50 text-yellow-600",
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
        className="p-4 text-[hsl(var(--muted-foreground))] text-center text-sm"
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
    <div data-testid="gap-table">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead
              className="cursor-pointer hover:text-[hsl(var(--foreground))]"
              onClick={() => toggleSort("severity")}
            >
              Severity {sortField === "severity" ? (sortDir === "asc" ? "\u2191" : "\u2193") : ""}
            </TableHead>
            <TableHead
              className="cursor-pointer hover:text-[hsl(var(--foreground))]"
              onClick={() => toggleSort("gap_type")}
            >
              Type {sortField === "gap_type" ? (sortDir === "asc" ? "\u2191" : "\u2193") : ""}
            </TableHead>
            <TableHead>Description</TableHead>
            <TableHead>Recommendation</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((gap) => {
            const severityKey = gap.severity.toLowerCase();
            const badgeClass = SEVERITY_CLASSES[severityKey] ?? "bg-gray-100 text-gray-500";
            return (
              <TableRow key={gap.id}>
                <TableCell>
                  <span
                    className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase ${badgeClass}`}
                  >
                    {gap.severity}
                  </span>
                </TableCell>
                <TableCell className="text-[hsl(var(--foreground))]">
                  {gap.gap_type.replace(/_/g, " ")}
                </TableCell>
                <TableCell className="text-[hsl(var(--muted-foreground))]">
                  {gap.description}
                </TableCell>
                <TableCell className="text-[hsl(var(--muted-foreground))]">
                  {gap.recommendation ?? "-"}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
