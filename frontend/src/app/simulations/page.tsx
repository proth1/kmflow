"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchScenarios,
  fetchSimulationResults,
  runScenario,
  type ScenarioData,
  type SimulationResultData,
} from "@/lib/api";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { FlaskConical, Play, RefreshCw, AlertCircle } from "lucide-react";

export default function SimulationsPage() {
  const [scenarios, setScenarios] = useState<ScenarioData[]>([]);
  const [results, setResults] = useState<SimulationResultData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [scenarioResult, resultResult] = await Promise.all([
        fetchScenarios(),
        fetchSimulationResults(),
      ]);
      setScenarios(scenarioResult.items);
      setResults(resultResult.items);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load simulation data",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function handleRun(scenarioId: string) {
    setRunning(scenarioId);
    setError(null);
    try {
      await runScenario(scenarioId);
      await loadData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to run simulation",
      );
    } finally {
      setRunning(null);
    }
  }

  if (loading) {
    return (
      <div className="p-6 space-y-4">
        <h1 className="text-2xl font-bold">Simulations</h1>
        <div className="flex items-center gap-2 text-muted-foreground">
          <RefreshCw className="h-4 w-4 animate-spin" />
          Loading simulation data...
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Simulations</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Scenario modeling and what-if analysis for process optimization
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadData}>
          <RefreshCw className="h-3 w-3 mr-1.5" />
          Refresh
        </Button>
      </div>

      {error && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-destructive mt-0.5" />
              <p className="text-sm text-destructive">{error}</p>
            </div>
          </CardContent>
        </Card>
      )}

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

      <Tabs defaultValue="scenarios">
        <TabsList>
          <TabsTrigger value="scenarios">
            <FlaskConical className="h-4 w-4 mr-1.5" />
            Scenarios
          </TabsTrigger>
          <TabsTrigger value="results">
            <Play className="h-4 w-4 mr-1.5" />
            Results
          </TabsTrigger>
        </TabsList>

        <TabsContent value="scenarios">
          <Card>
            <CardHeader>
              <CardTitle>Simulation Scenarios</CardTitle>
              <CardDescription>
                Define scenarios for process simulation and what-if analysis
              </CardDescription>
            </CardHeader>
            <CardContent>
              {scenarios.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No scenarios defined. Create one via the API.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Description</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {scenarios.map((s) => (
                      <TableRow key={s.id}>
                        <TableCell className="font-medium">
                          {s.name}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{s.simulation_type}</Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground max-w-xs truncate">
                          {s.description || "—"}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {new Date(s.created_at).toLocaleDateString()}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            size="sm"
                            onClick={() => handleRun(s.id)}
                            disabled={running === s.id}
                          >
                            {running === s.id ? (
                              <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" />
                            ) : (
                              <Play className="h-3 w-3 mr-1.5" />
                            )}
                            Run
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="results">
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
                          {r.recommendations
                            ? r.recommendations.length
                            : 0}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {r.completed_at
                            ? new Date(r.completed_at).toLocaleDateString()
                            : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
