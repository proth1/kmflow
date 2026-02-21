"use client";

import { RefreshCw, Eye } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import EvidenceHeatmap from "@/components/EvidenceHeatmap";
import type { ScenarioCoverageData, ScenarioData } from "./types";

interface CoverageTabProps {
  scenarios: ScenarioData[];
  coverageScenarioId: string;
  coverageData: ScenarioCoverageData | null;
  loadingCoverage: boolean;
  onScenarioChange: (id: string) => void;
  onLoadCoverage: () => void;
}

export default function CoverageTab({
  scenarios,
  coverageScenarioId,
  coverageData,
  loadingCoverage,
  onScenarioChange,
  onLoadCoverage,
}: CoverageTabProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Evidence Coverage</CardTitle>
        <CardDescription>
          Bright / Dim / Dark evidence classification per process element
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label htmlFor="coverage-select" className="text-sm font-medium mb-1 block">
              Select Scenario
            </label>
            <select
              id="coverage-select"
              value={coverageScenarioId}
              onChange={(e) => onScenarioChange(e.target.value)}
              className="border rounded px-3 py-1.5 text-sm w-full"
            >
              <option value="">Select scenario...</option>
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <Button
            onClick={onLoadCoverage}
            disabled={loadingCoverage || !coverageScenarioId}
          >
            {loadingCoverage ? (
              <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" />
            ) : (
              <Eye className="h-3 w-3 mr-1.5" />
            )}
            Load Coverage
          </Button>
        </div>

        {coverageData && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
              <Card>
                <CardContent className="pt-4 pb-3">
                  <div className="text-2xl font-bold text-emerald-600">
                    {coverageData.bright_count}
                  </div>
                  <div className="text-xs text-muted-foreground">Bright</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 pb-3">
                  <div className="text-2xl font-bold text-amber-600">
                    {coverageData.dim_count}
                  </div>
                  <div className="text-xs text-muted-foreground">Dim</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 pb-3">
                  <div className="text-2xl font-bold text-slate-500">
                    {coverageData.dark_count}
                  </div>
                  <div className="text-xs text-muted-foreground">Dark</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 pb-3">
                  <div className="text-2xl font-bold">
                    {(coverageData.aggregate_confidence * 100).toFixed(1)}%
                  </div>
                  <div className="text-xs text-muted-foreground">Aggregate Confidence</div>
                </CardContent>
              </Card>
            </div>

            <EvidenceHeatmap elements={coverageData.elements} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
