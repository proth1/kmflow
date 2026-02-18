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

const COMPLIANCE_CLASSES: Record<string, { bg: string; text: string; border: string }> = {
  fully_compliant: { bg: "bg-green-50", text: "text-green-700", border: "border-green-200" },
  partially_compliant: { bg: "bg-yellow-50", text: "text-yellow-700", border: "border-yellow-200" },
  non_compliant: { bg: "bg-red-50", text: "text-red-600", border: "border-red-200" },
  not_assessed: { bg: "bg-gray-100", text: "text-gray-500", border: "border-gray-200" },
};

export default function RegulatoryOverlay({
  engagementId,
}: RegulatoryOverlayProps) {
  const [compliance, setCompliance] = useState<ComplianceStateData | null>(null);
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
        className="p-6 text-[hsl(var(--muted-foreground))] text-center text-sm"
        data-testid="regulatory-overlay-loading"
      >
        Loading regulatory overlay...
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="p-6 text-red-600 bg-red-50 rounded-xl text-center text-sm"
        data-testid="regulatory-overlay-error"
      >
        {error}
      </div>
    );
  }

  const level = compliance?.level ?? "not_assessed";
  const colors = COMPLIANCE_CLASSES[level] ?? COMPLIANCE_CLASSES.not_assessed;
  const coverage = compliance?.policy_coverage ?? 0;

  const coverageBarClass =
    coverage >= 90 ? "bg-green-500" : coverage >= 50 ? "bg-yellow-400" : "bg-red-500";
  const coverageTextClass =
    coverage >= 90 ? "text-green-700" : coverage >= 50 ? "text-yellow-700" : "text-red-600";

  return (
    <div data-testid="regulatory-overlay">
      {/* Compliance Status */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        {/* Level Badge */}
        <div
          className={`rounded-xl p-5 text-center border ${colors.bg} ${colors.border}`}
        >
          <div className="text-xs font-semibold uppercase tracking-wide text-[hsl(var(--muted-foreground))] mb-2">
            Compliance Level
          </div>
          <div className={`text-lg font-bold uppercase ${colors.text}`}>
            {level.replace(/_/g, " ")}
          </div>
        </div>

        {/* Coverage Gauge */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-5 text-center">
          <div className="text-xs font-semibold uppercase tracking-wide text-[hsl(var(--muted-foreground))] mb-2">
            Policy Coverage
          </div>
          <div className={`text-3xl font-bold ${coverageTextClass}`}>
            {coverage.toFixed(1)}%
          </div>
          <div className="h-2 bg-gray-100 rounded-full mt-2 overflow-hidden">
            <div
              className={`h-full rounded-full transition-[width] duration-300 ${coverageBarClass}`}
              style={{ width: `${Math.min(coverage, 100)}%` }}
            />
          </div>
        </div>
      </div>

      {/* Process Counts */}
      {compliance && (
        <div className="grid grid-cols-3 gap-3 mb-6">
          <div className="text-center p-3 bg-gray-50 rounded-lg">
            <div className="text-2xl font-bold text-[hsl(var(--foreground))]">
              {compliance.total_processes}
            </div>
            <div className="text-xs text-[hsl(var(--muted-foreground))]">
              Total Processes
            </div>
          </div>
          <div className="text-center p-3 bg-green-50 rounded-lg">
            <div className="text-2xl font-bold text-green-700">
              {compliance.governed_count}
            </div>
            <div className="text-xs text-[hsl(var(--muted-foreground))]">Governed</div>
          </div>
          <div className="text-center p-3 bg-red-50 rounded-lg">
            <div className="text-2xl font-bold text-red-600">
              {compliance.ungoverned_count}
            </div>
            <div className="text-xs text-[hsl(var(--muted-foreground))]">Ungoverned</div>
          </div>
        </div>
      )}

      {/* Ungoverned Processes List */}
      {ungoverned.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-red-600 mb-3">
            Ungoverned Processes ({ungoverned.length})
          </h3>
          <div className="flex flex-col gap-1.5">
            {ungoverned.map((proc) => (
              <div
                key={proc.process_id}
                className="flex items-center gap-2 p-2 px-3 bg-red-50 rounded-lg text-sm"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-red-600 shrink-0" />
                <span className="text-[hsl(var(--foreground))]">
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
