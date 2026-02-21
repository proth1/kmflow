"use client";

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
import type { SimulationResultData } from "./types";

interface ResultsTabProps {
  results: SimulationResultData[];
}

export default function ResultsTab({ results }: ResultsTabProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Simulation Results</CardTitle>
        <CardDescription>
          Output from completed simulation runs
        </CardDescription>
      </CardHeader>
      <CardContent>
        {results.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center">
            No simulation results yet. Run a scenario to see results.
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Scenario</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Recommendations</TableHead>
                <TableHead>Completed</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {results.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                      {r.scenario_id.substring(0, 8)}...
                    </code>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        r.status === "completed"
                          ? "default"
                          : r.status === "failed"
                            ? "destructive"
                            : "secondary"
                      }
                    >
                      {r.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm">
                    {r.execution_time_ms}ms
                  </TableCell>
                  <TableCell className="text-sm">
                    {r.recommendations ? r.recommendations.length : 0}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {r.completed_at
                      ? new Date(r.completed_at).toLocaleDateString()
                      : "\u2014"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
