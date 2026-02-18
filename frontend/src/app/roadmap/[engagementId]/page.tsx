/**
 * Transformation Roadmap Page.
 *
 * Displays a 4-phase transformation roadmap generated from TOM gap
 * analysis, with timeline visualization and initiative details.
 */
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import RoadmapTimeline from "@/components/RoadmapTimeline";
import KPICard from "@/components/KPICard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
    <div className="max-w-6xl mx-auto p-8">
      {/* Header */}
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold mb-1">Transformation Roadmap</h1>
          <p className="text-[hsl(var(--muted-foreground))] text-sm">
            Phased improvement plan based on TOM gap analysis
          </p>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link href={`/tom/${engagementId}`}>Back to TOM Dashboard</Link>
        </Button>
      </div>

      {/* TOM ID input (for selecting which TOM to view roadmap for) */}
      {!roadmap && !loading && (
        <Card className="mb-8">
          <CardContent className="pt-8 pb-8 text-center">
            <h2 className="text-lg font-semibold mb-4">
              Select Target Operating Model
            </h2>
            <p className="text-[hsl(var(--muted-foreground))] text-sm mb-4">
              Enter a TOM ID to view the transformation roadmap
            </p>
            <div className="flex gap-2 justify-center">
              <Input
                type="text"
                placeholder="TOM ID (UUID)"
                value={tomId}
                onChange={(e) => setTomId(e.target.value)}
                className="w-80"
              />
            </div>
          </CardContent>
        </Card>
      )}

      {loading && (
        <div className="text-center text-[hsl(var(--muted-foreground))] py-12">
          Loading roadmap...
        </div>
      )}

      {error && (
        <div className="text-center text-red-600 py-6 bg-red-50 rounded-xl border border-red-200 mb-6">
          {error}
        </div>
      )}

      {roadmap && (
        <>
          {/* KPI Summary */}
          <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-4 mb-8">
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
              value={roadmap.phases[2]?.initiatives.length ?? 0}
              status={
                (roadmap.phases[2]?.initiatives.length ?? 0) > 0
                  ? "critical"
                  : "good"
              }
              subtitle="Phase 3 transformation"
            />
          </div>

          {/* Roadmap Timeline */}
          <Card>
            <CardHeader className="pb-5">
              <CardTitle className="text-base">Implementation Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <RoadmapTimeline
                phases={roadmap.phases}
                totalInitiatives={roadmap.total_initiatives}
                estimatedMonths={roadmap.estimated_duration_months}
              />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
