"use client";

import { RefreshCw, Brain } from "lucide-react";
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
import type { EpistemicPlanData, ScenarioData } from "./types";

interface EpistemicTabProps {
  scenarios: ScenarioData[];
  epistemicScenarioId: string;
  epistemicPlan: EpistemicPlanData | null;
  loadingEpistemic: boolean;
  onScenarioChange: (id: string) => void;
  onLoadEpistemic: () => void;
}

export default function EpistemicTab({
  scenarios,
  epistemicScenarioId,
  epistemicPlan,
  loadingEpistemic,
  onScenarioChange,
  onLoadEpistemic,
}: EpistemicTabProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Epistemic Action Plan</CardTitle>
        <CardDescription>
          Ranked evidence gaps by information gain to guide targeted evidence collection
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label htmlFor="epistemic-select" className="text-sm font-medium mb-1 block">
              Select Scenario
            </label>
            <select
              id="epistemic-select"
              value={epistemicScenarioId}
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
            onClick={onLoadEpistemic}
            disabled={loadingEpistemic || !epistemicScenarioId}
          >
            {loadingEpistemic ? (
              <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" />
            ) : (
              <Brain className="h-3 w-3 mr-1.5" />
            )}
            Generate Plan
          </Button>
        </div>

        {epistemicPlan && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <Card>
                <CardContent className="pt-4 pb-3">
                  <div className="text-2xl font-bold">
                    {epistemicPlan.aggregated_view.total}
                  </div>
                  <div className="text-xs text-muted-foreground">Total Actions</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 pb-3">
                  <div className="text-2xl font-bold text-red-600">
                    {epistemicPlan.aggregated_view.high_priority_count}
                  </div>
                  <div className="text-xs text-muted-foreground">High Priority</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 pb-3">
                  <div className="text-2xl font-bold text-emerald-600">
                    +{(epistemicPlan.aggregated_view.estimated_aggregate_uplift * 100).toFixed(1)}%
                  </div>
                  <div className="text-xs text-muted-foreground">Est. Aggregate Uplift</div>
                </CardContent>
              </Card>
            </div>

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Element</TableHead>
                  <TableHead>Gap Description</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Info Gain</TableHead>
                  <TableHead>Priority</TableHead>
                  <TableHead>Category</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {epistemicPlan.actions.map((a, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-medium text-sm">
                      {a.target_element_name}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground max-w-xs truncate">
                      {a.evidence_gap_description}
                    </TableCell>
                    <TableCell className="text-sm">
                      {(a.current_confidence * 100).toFixed(0)}% →{" "}
                      {(a.projected_confidence * 100).toFixed(0)}%
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={a.information_gain_score > 0.5 ? "default" : "secondary"}
                      >
                        {a.information_gain_score.toFixed(3)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          a.priority === "high"
                            ? "destructive"
                            : a.priority === "medium"
                              ? "default"
                              : "secondary"
                        }
                      >
                        {a.priority}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs">
                      {a.recommended_evidence_category}
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
