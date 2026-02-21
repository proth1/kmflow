"use client";

import { RefreshCw, Trophy } from "lucide-react";
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
import type { ScenarioData, ScenarioRankingData, RankingWeights } from "./types";

interface RankingTabProps {
  scenarios: ScenarioData[];
  rankingData: ScenarioRankingData | null;
  loadingRanking: boolean;
  weights: RankingWeights;
  onWeightsChange: (updated: RankingWeights) => void;
  onLoadRanking: () => void;
}

export default function RankingTab({
  scenarios,
  rankingData,
  loadingRanking,
  weights,
  onWeightsChange,
  onLoadRanking,
}: RankingTabProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Scenario Ranking</CardTitle>
        <CardDescription>
          Composite scoring across evidence, simulation, financial, and governance dimensions
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {(["evidence", "simulation", "financial", "governance"] as const).map((dim) => (
            <div key={dim} className="space-y-1">
              <label className="text-xs font-medium capitalize">
                {dim}: {(weights[dim] * 100).toFixed(0)}%
              </label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={weights[dim]}
                onChange={(e) =>
                  onWeightsChange({ ...weights, [dim]: parseFloat(e.target.value) })
                }
                className="w-full"
              />
            </div>
          ))}
        </div>

        <Button
          onClick={onLoadRanking}
          disabled={loadingRanking || scenarios.length === 0}
        >
          {loadingRanking ? (
            <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" />
          ) : (
            <Trophy className="h-3 w-3 mr-1.5" />
          )}
          Rank Scenarios
        </Button>

        {rankingData && rankingData.rankings.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">#</TableHead>
                <TableHead>Scenario</TableHead>
                <TableHead>Composite</TableHead>
                <TableHead>Evidence</TableHead>
                <TableHead>Simulation</TableHead>
                <TableHead>Financial</TableHead>
                <TableHead>Governance</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rankingData.rankings.map((r, i) => (
                <TableRow key={r.scenario_id}>
                  <TableCell className="font-bold">{i + 1}</TableCell>
                  <TableCell className="font-medium">{r.scenario_name}</TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        r.composite_score >= 0.7
                          ? "default"
                          : r.composite_score >= 0.4
                            ? "secondary"
                            : "outline"
                      }
                    >
                      {(r.composite_score * 100).toFixed(1)}%
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm">
                    {(r.evidence_score * 100).toFixed(1)}%
                  </TableCell>
                  <TableCell className="text-sm">
                    {(r.simulation_score * 100).toFixed(1)}%
                  </TableCell>
                  <TableCell className="text-sm">
                    {(r.financial_score * 100).toFixed(1)}%
                  </TableCell>
                  <TableCell className="text-sm">
                    {(r.governance_score * 100).toFixed(1)}%
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {rankingData && rankingData.rankings.length === 0 && (
          <p className="text-sm text-muted-foreground py-4 text-center">
            No scenarios found. Create scenarios first.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
