"use client";

import { RefreshCw, GitCompare } from "lucide-react";
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
import { Button } from "@/components/ui/button";
import type { ScenarioComparisonData, ScenarioData } from "./types";

const assessmentColor: Record<string, string> = {
  improvement: "bg-emerald-100 text-emerald-800",
  neutral: "bg-slate-100 text-slate-800",
  high_risk_increase: "bg-red-100 text-red-800",
  efficiency_decrease: "bg-amber-100 text-amber-800",
};

interface CompareTabProps {
  scenarios: ScenarioData[];
  baselineId: string;
  compareIds: Set<string>;
  comparisonData: ScenarioComparisonData | null;
  comparing: boolean;
  onBaselineChange: (id: string) => void;
  onToggleCompareId: (id: string) => void;
  onCompare: () => void;
}

export default function CompareTab({
  scenarios,
  baselineId,
  compareIds,
  comparisonData,
  comparing,
  onBaselineChange,
  onToggleCompareId,
  onCompare,
}: CompareTabProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Scenario Comparison</CardTitle>
        <CardDescription>
          Compare a baseline scenario against up to 4 alternatives side-by-side
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="baseline-select" className="text-sm font-medium mb-1 block">
              Baseline Scenario
            </label>
            <select
              id="baseline-select"
              value={baselineId}
              onChange={(e) => onBaselineChange(e.target.value)}
              className="border rounded px-3 py-1.5 text-sm w-full"
            >
              <option value="">Select baseline...</option>
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">
              Compare With (max 4)
            </label>
            <div className="space-y-1 max-h-40 overflow-y-auto border rounded p-2">
              {scenarios
                .filter((s) => s.id !== baselineId)
                .map((s) => (
                  <label key={s.id} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={compareIds.has(s.id)}
                      onChange={() => onToggleCompareId(s.id)}
                      disabled={!compareIds.has(s.id) && compareIds.size >= 4}
                    />
                    {s.name}
                  </label>
                ))}
            </div>
          </div>
        </div>

        <Button
          onClick={onCompare}
          disabled={comparing || !baselineId || compareIds.size === 0}
        >
          {comparing ? (
            <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" />
          ) : (
            <GitCompare className="h-3 w-3 mr-1.5" />
          )}
          Compare
        </Button>

        {comparisonData && (
          <div className="space-y-4 mt-4">
            <h3 className="text-sm font-medium">
              Baseline: {comparisonData.baseline_name}
            </h3>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Scenario</TableHead>
                  <TableHead>Assessment</TableHead>
                  <TableHead>Metric Deltas</TableHead>
                  <TableHead>Evidence Coverage</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {comparisonData.comparisons.map((c) => (
                  <TableRow key={c.scenario_id}>
                    <TableCell className="font-medium">
                      {c.scenario_name}
                    </TableCell>
                    <TableCell>
                      {c.assessment ? (
                        <Badge
                          className={assessmentColor[c.assessment] || "bg-slate-100"}
                        >
                          {c.assessment.replace(/_/g, " ")}
                        </Badge>
                      ) : (
                        <span className="text-sm text-muted-foreground">No results</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {c.deltas ? (
                        <div className="space-y-1">
                          {Object.entries(c.deltas).map(([key, val]) => (
                            <div key={key} className="text-xs">
                              <span className="font-medium">{key}:</span>{" "}
                              <span
                                className={
                                  val.delta > 0
                                    ? "text-emerald-600"
                                    : val.delta < 0
                                      ? "text-red-600"
                                      : ""
                                }
                              >
                                {val.delta > 0 ? "+" : ""}
                                {val.delta.toFixed(3)} ({val.pct_change}%)
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span className="text-sm text-muted-foreground">{"\u2014"}</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {c.coverage_summary ? (
                        <div className="flex gap-2 text-xs">
                          <span className="text-emerald-600 font-medium">
                            {c.coverage_summary.bright} Bright
                          </span>
                          <span className="text-amber-600 font-medium">
                            {c.coverage_summary.dim} Dim
                          </span>
                          <span className="text-slate-500 font-medium">
                            {c.coverage_summary.dark} Dark
                          </span>
                        </div>
                      ) : (
                        <span className="text-sm text-muted-foreground">{"\u2014"}</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
