"use client";

import { useState, useCallback } from "react";
import dynamic from "next/dynamic";
import {
  fetchAssessmentMatrix,
  computeAssessmentMatrix,
  type MatrixResponse,
  type MatrixEntry,
} from "@/lib/api/assessment-matrix";
import { PageLayout } from "@/components/layout/PageLayout";
import { useEngagementData } from "@/hooks/useEngagementData";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const ScatterChart = dynamic(
  () => import("recharts").then((mod) => mod.ScatterChart),
  { ssr: false },
);
const Scatter = dynamic(
  () => import("recharts").then((mod) => mod.Scatter),
  { ssr: false },
);
const XAxis = dynamic(
  () => import("recharts").then((mod) => mod.XAxis),
  { ssr: false },
);
const YAxis = dynamic(
  () => import("recharts").then((mod) => mod.YAxis),
  { ssr: false },
);
const CartesianGrid = dynamic(
  () => import("recharts").then((mod) => mod.CartesianGrid),
  { ssr: false },
);
const Tooltip = dynamic(
  () => import("recharts").then((mod) => mod.Tooltip),
  { ssr: false },
);
const ReferenceLine = dynamic(
  () => import("recharts").then((mod) => mod.ReferenceLine),
  { ssr: false },
);
const ResponsiveContainer = dynamic(
  () => import("recharts").then((mod) => mod.ResponsiveContainer),
  { ssr: false },
);
const ZAxis = dynamic(
  () => import("recharts").then((mod) => mod.ZAxis),
  { ssr: false },
);

const QUADRANT_COLORS: Record<string, string> = {
  transform: "#22c55e",
  invest: "#f59e0b",
  maintain: "#3b82f6",
  deprioritize: "#94a3b8",
};

const QUADRANT_LABELS: Record<string, string> = {
  transform: "Transform",
  invest: "Invest",
  maintain: "Maintain",
  deprioritize: "Deprioritize",
};

function quadrantBadgeClass(quadrant: string): string {
  switch (quadrant) {
    case "transform":
      return "bg-green-100 text-green-800";
    case "invest":
      return "bg-amber-100 text-amber-800";
    case "maintain":
      return "bg-blue-100 text-blue-800";
    case "deprioritize":
      return "bg-slate-100 text-slate-600";
    default:
      return "bg-gray-100 text-gray-800";
  }
}

export default function AssessmentMatrixPage() {
  const [engagementId, setEngagementId] = useState("");
  const [computing, setComputing] = useState(false);

  const fetchData = useCallback(
    async (id: string, signal: AbortSignal) => {
      return fetchAssessmentMatrix(id, signal);
    },
    [],
  );

  const { data, loading, error, refetch } = useEngagementData<MatrixResponse>(
    engagementId,
    fetchData,
  );

  const handleCompute = async () => {
    if (!engagementId) return;
    setComputing(true);
    try {
      await computeAssessmentMatrix(engagementId);
      refetch();
    } catch {
      // Error handled by refetch
    } finally {
      setComputing(false);
    }
  };

  const entries = data?.entries ?? [];

  // Prepare scatter data grouped by quadrant
  const scatterData = entries.map((e) => ({
    x: e.ability_to_execute,
    y: e.value_score,
    z: e.element_count,
    name: e.process_area_name,
    quadrant: e.quadrant,
    fill: QUADRANT_COLORS[e.quadrant] ?? "#94a3b8",
  }));

  return (
    <PageLayout
      title="Assessment Overlay Matrix"
      description="Value vs. Ability-to-Execute analysis for process area prioritization"
    >
      <div className="space-y-4">
        <div className="flex items-center gap-4">
          <input
            type="text"
            placeholder="Engagement ID"
            value={engagementId}
            onChange={(e) => setEngagementId(e.target.value)}
            className="border rounded px-3 py-2 w-80"
          />
          <button
            onClick={handleCompute}
            disabled={!engagementId || computing}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {computing ? "Computing..." : "Compute Matrix"}
          </button>
        </div>

        {loading && <p className="text-muted-foreground">Loading...</p>}
        {error && <p className="text-red-600">{error}</p>}

        {data && entries.length > 0 && (
          <>
            {/* Quadrant Summary */}
            <div className="grid grid-cols-4 gap-4">
              {(["transform", "invest", "maintain", "deprioritize"] as const).map((q) => (
                <Card key={q}>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium">
                      {QUADRANT_LABELS[q]}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-2xl font-bold">
                      {data.quadrant_summary[q] ?? 0}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      process areas
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Scatter Chart */}
            <Card>
              <CardHeader>
                <CardTitle>Assessment Overlay</CardTitle>
                <CardDescription>
                  Each dot is a process area. Size indicates element count.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="w-full h-[500px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart margin={{ top: 20, right: 20, bottom: 40, left: 40 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        type="number"
                        dataKey="x"
                        name="Ability to Execute"
                        domain={[0, 100]}
                        label={{ value: "Ability to Execute", position: "bottom", offset: 20 }}
                      />
                      <YAxis
                        type="number"
                        dataKey="y"
                        name="Value"
                        domain={[0, 100]}
                        label={{ value: "Value", angle: -90, position: "insideLeft", offset: -10 }}
                      />
                      <ZAxis
                        type="number"
                        dataKey="z"
                        range={[60, 400]}
                        name="Elements"
                      />
                      <Tooltip
                        content={({ payload }) => {
                          if (!payload?.length) return null;
                          const d = payload[0].payload as (typeof scatterData)[0];
                          return (
                            <div className="bg-white border rounded p-2 shadow text-sm">
                              <p className="font-semibold">{d.name}</p>
                              <p>Value: {d.y.toFixed(1)}</p>
                              <p>Ability: {d.x.toFixed(1)}</p>
                              <p>Elements: {d.z}</p>
                              <p className="capitalize">{d.quadrant}</p>
                            </div>
                          );
                        }}
                      />
                      <ReferenceLine x={50} stroke="#666" strokeDasharray="5 5" />
                      <ReferenceLine y={50} stroke="#666" strokeDasharray="5 5" />
                      <Scatter data={scatterData} />
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {/* Detail Table */}
            <Card>
              <CardHeader>
                <CardTitle>Process Area Details</CardTitle>
                <CardDescription>
                  {entries.length} process areas assessed
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Process Area</TableHead>
                      <TableHead>Value</TableHead>
                      <TableHead>Ability</TableHead>
                      <TableHead>Quadrant</TableHead>
                      <TableHead>Elements</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {entries.map((entry: MatrixEntry) => (
                      <TableRow key={entry.id}>
                        <TableCell className="font-medium">
                          {entry.process_area_name}
                        </TableCell>
                        <TableCell>{entry.value_score.toFixed(1)}</TableCell>
                        <TableCell>{entry.ability_to_execute.toFixed(1)}</TableCell>
                        <TableCell>
                          <Badge className={quadrantBadgeClass(entry.quadrant)}>
                            {QUADRANT_LABELS[entry.quadrant]}
                          </Badge>
                        </TableCell>
                        <TableCell>{entry.element_count}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </>
        )}

        {data && entries.length === 0 && (
          <Card>
            <CardContent className="py-8 text-center text-muted-foreground">
              No assessment data yet. Click &quot;Compute Matrix&quot; to generate.
            </CardContent>
          </Card>
        )}
      </div>
    </PageLayout>
  );
}
