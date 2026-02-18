/**
 * TOM Dashboard Page.
 *
 * Displays TOM alignment analysis with dimension maturity cards,
 * gap prioritization, and regulatory overlay for an engagement.
 */
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import KPICard from "@/components/KPICard";
import TOMDimensionCard from "@/components/TOMDimensionCard";
import RegulatoryOverlay from "@/components/RegulatoryOverlay";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
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
      <div className="max-w-6xl mx-auto p-8">
        <div className="text-center text-[hsl(var(--muted-foreground))] py-12">
          Loading TOM dashboard...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-6xl mx-auto p-8">
        <div className="text-center text-red-600 py-12 bg-red-50 rounded-xl border border-red-200">
          <h2 className="text-xl font-semibold mb-2">Error</h2>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  const totalGaps = gaps?.total ?? 0;
  const criticalGaps =
    gaps?.items.filter((g) => g.severity > 0.7).length ?? 0;
  const highPriorityGaps =
    gaps?.items.filter((g) => g.priority_score > 0.5).length ?? 0;

  return (
    <div className="max-w-6xl mx-auto p-8">
      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold mb-1">TOM Alignment Dashboard</h1>
          <p className="text-[hsl(var(--muted-foreground))] text-sm">
            Target Operating Model gap analysis and maturity assessment
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant={showOverlay ? "default" : "outline"}
            size="sm"
            onClick={() => setShowOverlay(!showOverlay)}
            className={showOverlay ? "bg-purple-700 hover:bg-purple-800" : ""}
          >
            {showOverlay ? "Hide" : "Show"} Regulatory Overlay
          </Button>
          <Button asChild size="sm">
            <Link href={`/roadmap/${engagementId}`}>View Roadmap</Link>
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-4 mb-8">
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
        <div className="mb-8">
          <h2 className="text-base font-semibold mb-4 text-[hsl(var(--foreground))]">
            Dimension Maturity
          </h2>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-4">
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
        <Card className="mb-8">
          <CardHeader className="pb-4">
            <CardTitle className="text-base">Gap Analysis Results</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Dimension</TableHead>
                  <TableHead>Gap Type</TableHead>
                  <TableHead>Severity</TableHead>
                  <TableHead>Priority</TableHead>
                  <TableHead>Recommendation</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {gaps.items
                  .sort((a, b) => b.priority_score - a.priority_score)
                  .map((gap) => (
                    <TableRow key={gap.id}>
                      <TableCell className="capitalize">
                        {gap.dimension.replace(/_/g, " ")}
                      </TableCell>
                      <TableCell>
                        <span
                          className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                            gap.gap_type === "full_gap"
                              ? "bg-red-50 text-red-600"
                              : gap.gap_type === "partial_gap"
                                ? "bg-orange-50 text-orange-700"
                                : "bg-yellow-50 text-yellow-700"
                          }`}
                        >
                          {gap.gap_type.replace(/_/g, " ")}
                        </span>
                      </TableCell>
                      <TableCell className="text-[hsl(var(--muted-foreground))]">
                        {(gap.severity * 100).toFixed(0)}%
                      </TableCell>
                      <TableCell className="text-[hsl(var(--muted-foreground))]">
                        {gap.priority_score.toFixed(3)}
                      </TableCell>
                      <TableCell className="text-[hsl(var(--muted-foreground))] max-w-[300px]">
                        {gap.recommendation ?? "-"}
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Regulatory Overlay Toggle */}
      {showOverlay && (
        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="text-base">Regulatory Governance Overlay</CardTitle>
          </CardHeader>
          <CardContent>
            <RegulatoryOverlay engagementId={engagementId} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
