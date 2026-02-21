"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { ScenarioData, SimulationResultData } from "./types";

interface StatsCardsProps {
  scenarios: ScenarioData[];
  results: SimulationResultData[];
}

export default function StatsCards({ scenarios, results }: StatsCardsProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <Card>
        <CardHeader className="pb-2">
          <CardDescription>Scenarios</CardDescription>
          <CardTitle className="text-3xl">{scenarios.length}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            Defined simulation scenarios
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardDescription>Completed Runs</CardDescription>
          <CardTitle className="text-3xl">
            {results.filter((r) => r.status === "completed").length}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            Successfully executed simulations
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardDescription>Total Results</CardDescription>
          <CardTitle className="text-3xl">{results.length}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            All simulation results
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
