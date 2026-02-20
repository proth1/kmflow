"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  createScenario,
  createFinancialAssumption,
  deleteFinancialAssumption,
  fetchEpistemicPlan,
  fetchFinancialAssumptions,
  fetchFinancialImpact,
  fetchScenarioComparison,
  fetchScenarioCoverage,
  fetchScenarioRanking,
  fetchScenarios,
  fetchSimulationResults,
  fetchSuggestions,
  requestSuggestions,
  runScenario,
  updateSuggestionDisposition,
  type AlternativeSuggestionData,
  type EpistemicPlanData,
  type FinancialAssumptionData,
  type FinancialAssumptionType,
  type FinancialImpactData,
  type ScenarioComparisonData,
  type ScenarioCoverageData,
  type ScenarioData,
  type ScenarioRankingData,
  type SimulationResultData,
  type SuggestionDispositionType,
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
import {
  FlaskConical,
  Play,
  RefreshCw,
  AlertCircle,
  Plus,
  GitCompare,
  Eye,
  Brain,
  Lightbulb,
  DollarSign,
  Trophy,
  Trash2,
} from "lucide-react";
import EvidenceHeatmap from "@/components/EvidenceHeatmap";
import SuggestionCard from "@/components/SuggestionCard";

const SIMULATION_TYPES = ["what_if", "capacity", "process_change", "control_removal"];

export default function SimulationsPage() {
  const [scenarios, setScenarios] = useState<ScenarioData[]>([]);
  const [results, setResults] = useState<SimulationResultData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const isInitialLoad = useRef(true);

  // Creation form state
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState("what_if");
  const [newDescription, setNewDescription] = useState("");
  const [creating, setCreating] = useState(false);

  // Comparison state
  const [baselineId, setBaselineId] = useState<string>("");
  const [compareIds, setCompareIds] = useState<Set<string>>(new Set());
  const [comparisonData, setComparisonData] = useState<ScenarioComparisonData | null>(null);
  const [comparing, setComparing] = useState(false);

  // Coverage state
  const [coverageScenarioId, setCoverageScenarioId] = useState<string>("");
  const [coverageData, setCoverageData] = useState<ScenarioCoverageData | null>(null);
  const [loadingCoverage, setLoadingCoverage] = useState(false);

  // Epistemic plan state
  const [epistemicScenarioId, setEpistemicScenarioId] = useState<string>("");
  const [epistemicPlan, setEpistemicPlan] = useState<EpistemicPlanData | null>(null);
  const [loadingEpistemic, setLoadingEpistemic] = useState(false);

  // Suggestions state
  const [suggestionsScenarioId, setSuggestionsScenarioId] = useState<string>("");
  const [suggestions, setSuggestions] = useState<AlternativeSuggestionData[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [generatingSuggestions, setGeneratingSuggestions] = useState(false);

  // Financial state
  const [financialScenarioId, setFinancialScenarioId] = useState<string>("");
  const [assumptions, setAssumptions] = useState<FinancialAssumptionData[]>([]);
  const [financialImpact, setFinancialImpact] = useState<FinancialImpactData | null>(null);
  const [loadingFinancial, setLoadingFinancial] = useState(false);
  const [showAssumptionForm, setShowAssumptionForm] = useState(false);
  const [newAssumption, setNewAssumption] = useState({
    name: "",
    assumption_type: "cost_per_role" as FinancialAssumptionType,
    value: 0,
    unit: "",
    confidence: 0.8,
  });

  // Ranking state
  const [rankingData, setRankingData] = useState<ScenarioRankingData | null>(null);
  const [loadingRanking, setLoadingRanking] = useState(false);
  const [weights, setWeights] = useState({
    evidence: 0.30,
    simulation: 0.25,
    financial: 0.25,
    governance: 0.20,
  });

  const loadData = useCallback(async (silent = false) => {
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
      if (!silent) {
        setError(
          err instanceof Error ? err.message : "Failed to load simulation data",
        );
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const silent = isInitialLoad.current;
    isInitialLoad.current = false;
    loadData(silent);
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

  async function handleCreate() {
    if (!newName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await createScenario({
        name: newName.trim(),
        simulation_type: newType,
        description: newDescription.trim() || undefined,
        engagement_id: scenarios[0]?.engagement_id ?? "",
      });
      setNewName("");
      setNewDescription("");
      setShowCreate(false);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create scenario");
    } finally {
      setCreating(false);
    }
  }

  async function handleCompare() {
    if (!baselineId || compareIds.size === 0) return;
    setComparing(true);
    setError(null);
    try {
      const data = await fetchScenarioComparison(baselineId, Array.from(compareIds));
      setComparisonData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to compare scenarios");
    } finally {
      setComparing(false);
    }
  }

  async function handleLoadCoverage() {
    if (!coverageScenarioId) return;
    setLoadingCoverage(true);
    setError(null);
    try {
      const data = await fetchScenarioCoverage(coverageScenarioId);
      setCoverageData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load coverage");
    } finally {
      setLoadingCoverage(false);
    }
  }

  async function handleLoadEpistemic() {
    if (!epistemicScenarioId) return;
    setLoadingEpistemic(true);
    setError(null);
    try {
      const data = await fetchEpistemicPlan(epistemicScenarioId);
      setEpistemicPlan(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load epistemic plan");
    } finally {
      setLoadingEpistemic(false);
    }
  }

  async function handleLoadSuggestions() {
    if (!suggestionsScenarioId) return;
    setLoadingSuggestions(true);
    setError(null);
    try {
      const data = await fetchSuggestions(suggestionsScenarioId);
      setSuggestions(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load suggestions");
    } finally {
      setLoadingSuggestions(false);
    }
  }

  async function handleGenerateSuggestions() {
    if (!suggestionsScenarioId) return;
    setGeneratingSuggestions(true);
    setError(null);
    try {
      const data = await requestSuggestions(suggestionsScenarioId);
      setSuggestions(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate suggestions");
    } finally {
      setGeneratingSuggestions(false);
    }
  }

  async function handleDispositionChange(
    suggestionId: string,
    disposition: SuggestionDispositionType,
    notes?: string,
  ) {
    if (!suggestionsScenarioId) return;
    try {
      const updated = await updateSuggestionDisposition(
        suggestionsScenarioId,
        suggestionId,
        disposition,
        notes,
      );
      setSuggestions((prev) =>
        prev.map((s) => (s.id === suggestionId ? updated : s)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update suggestion");
    }
  }

  async function handleLoadFinancial() {
    if (!financialScenarioId) return;
    setLoadingFinancial(true);
    setError(null);
    try {
      const [assumptionData, impactData] = await Promise.all([
        fetchFinancialAssumptions(financialScenarioId),
        fetchFinancialImpact(financialScenarioId),
      ]);
      setAssumptions(assumptionData.items);
      setFinancialImpact(impactData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load financial data");
    } finally {
      setLoadingFinancial(false);
    }
  }

  async function handleCreateAssumption() {
    if (!financialScenarioId || !newAssumption.name.trim()) return;
    setError(null);
    const engagementId = scenarios.find((s) => s.id === financialScenarioId)?.engagement_id;
    if (!engagementId) return;
    try {
      await createFinancialAssumption(financialScenarioId, {
        engagement_id: engagementId,
        ...newAssumption,
      });
      setNewAssumption({ name: "", assumption_type: "cost_per_role", value: 0, unit: "", confidence: 0.8 });
      setShowAssumptionForm(false);
      await handleLoadFinancial();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create assumption");
    }
  }

  async function handleDeleteAssumption(assumptionId: string) {
    if (!financialScenarioId) return;
    try {
      await deleteFinancialAssumption(financialScenarioId, assumptionId);
      setAssumptions((prev) => prev.filter((a) => a.id !== assumptionId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete assumption");
    }
  }

  async function handleLoadRanking() {
    const engagementId = scenarios[0]?.engagement_id;
    if (!engagementId) return;
    setLoadingRanking(true);
    setError(null);
    try {
      const data = await fetchScenarioRanking(engagementId, weights);
      setRankingData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load rankings");
    } finally {
      setLoadingRanking(false);
    }
  }

  function toggleCompareId(id: string) {
    setCompareIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < 4) {
        next.add(id);
      }
      return next;
    });
  }

  const assessmentColor: Record<string, string> = {
    improvement: "bg-emerald-100 text-emerald-800",
    neutral: "bg-slate-100 text-slate-800",
    high_risk_increase: "bg-red-100 text-red-800",
    efficiency_decrease: "bg-amber-100 text-amber-800",
  };

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
        <Button variant="outline" size="sm" onClick={() => loadData(false)}>
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
          <TabsTrigger value="compare">
            <GitCompare className="h-4 w-4 mr-1.5" />
            Compare
          </TabsTrigger>
          <TabsTrigger value="coverage">
            <Eye className="h-4 w-4 mr-1.5" />
            Coverage
          </TabsTrigger>
          <TabsTrigger value="epistemic">
            <Brain className="h-4 w-4 mr-1.5" />
            Evidence Gaps
          </TabsTrigger>
          <TabsTrigger value="suggestions">
            <Lightbulb className="h-4 w-4 mr-1.5" />
            Suggestions
          </TabsTrigger>
          <TabsTrigger value="financial">
            <DollarSign className="h-4 w-4 mr-1.5" />
            Financial
          </TabsTrigger>
          <TabsTrigger value="ranking">
            <Trophy className="h-4 w-4 mr-1.5" />
            Ranking
          </TabsTrigger>
        </TabsList>

        {/* ---- Scenarios Tab ---- */}
        <TabsContent value="scenarios">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Simulation Scenarios</CardTitle>
                  <CardDescription>
                    Define scenarios for process simulation and what-if analysis
                  </CardDescription>
                </div>
                <Button size="sm" variant="outline" onClick={() => setShowCreate(!showCreate)}>
                  <Plus className="h-3 w-3 mr-1.5" />
                  New Scenario
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {showCreate && (
                <div className="border rounded-lg p-4 mb-4 space-y-3 bg-muted/30">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <input
                      type="text"
                      placeholder="Scenario name"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      className="border rounded px-3 py-1.5 text-sm w-full"
                    />
                    <select
                      value={newType}
                      onChange={(e) => setNewType(e.target.value)}
                      className="border rounded px-3 py-1.5 text-sm w-full"
                    >
                      {SIMULATION_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t.replace(/_/g, " ")}
                        </option>
                      ))}
                    </select>
                  </div>
                  <input
                    type="text"
                    placeholder="Description (optional)"
                    value={newDescription}
                    onChange={(e) => setNewDescription(e.target.value)}
                    className="border rounded px-3 py-1.5 text-sm w-full"
                  />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={handleCreate} disabled={creating || !newName.trim() || !scenarios[0]?.engagement_id}>
                      {creating ? "Creating..." : "Create"}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => { setShowCreate(false); setError(null); }}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}

              {scenarios.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No scenarios defined. Create one to get started.
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
                          {s.description || "\u2014"}
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

        {/* ---- Results Tab ---- */}
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
                            : "\u2014"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ---- Compare Tab ---- */}
        <TabsContent value="compare">
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
                  <label htmlFor="baseline-select" className="text-sm font-medium mb-1 block">Baseline Scenario</label>
                  <select
                    id="baseline-select"
                    value={baselineId}
                    onChange={(e) => setBaselineId(e.target.value)}
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
                            onChange={() => toggleCompareId(s.id)}
                            disabled={!compareIds.has(s.id) && compareIds.size >= 4}
                          />
                          {s.name}
                        </label>
                      ))}
                  </div>
                </div>
              </div>

              <Button
                onClick={handleCompare}
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
        </TabsContent>

        {/* ---- Coverage Tab ---- */}
        <TabsContent value="coverage">
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
                  <label htmlFor="coverage-select" className="text-sm font-medium mb-1 block">Select Scenario</label>
                  <select
                    id="coverage-select"
                    value={coverageScenarioId}
                    onChange={(e) => setCoverageScenarioId(e.target.value)}
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
                  onClick={handleLoadCoverage}
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
        </TabsContent>

        {/* ---- Evidence Gaps (Epistemic) Tab ---- */}
        <TabsContent value="epistemic">
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
                  <label htmlFor="epistemic-select" className="text-sm font-medium mb-1 block">Select Scenario</label>
                  <select
                    id="epistemic-select"
                    value={epistemicScenarioId}
                    onChange={(e) => setEpistemicScenarioId(e.target.value)}
                    className="border rounded px-3 py-1.5 text-sm w-full"
                  >
                    <option value="">Select scenario...</option>
                    {scenarios.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>
                <Button onClick={handleLoadEpistemic} disabled={loadingEpistemic || !epistemicScenarioId}>
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
                        <div className="text-2xl font-bold">{epistemicPlan.aggregated_view.total}</div>
                        <div className="text-xs text-muted-foreground">Total Actions</div>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="pt-4 pb-3">
                        <div className="text-2xl font-bold text-red-600">{epistemicPlan.aggregated_view.high_priority_count}</div>
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
                          <TableCell className="font-medium text-sm">{a.target_element_name}</TableCell>
                          <TableCell className="text-sm text-muted-foreground max-w-xs truncate">{a.evidence_gap_description}</TableCell>
                          <TableCell className="text-sm">
                            {(a.current_confidence * 100).toFixed(0)}% → {(a.projected_confidence * 100).toFixed(0)}%
                          </TableCell>
                          <TableCell>
                            <Badge variant={a.information_gain_score > 0.5 ? "default" : "secondary"}>
                              {a.information_gain_score.toFixed(3)}
                            </Badge>
                          </TableCell>
                          <TableCell>
                            <Badge variant={a.priority === "high" ? "destructive" : a.priority === "medium" ? "default" : "secondary"}>
                              {a.priority}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs">{a.recommended_evidence_category}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ---- Suggestions Tab ---- */}
        <TabsContent value="suggestions">
          <Card>
            <CardHeader>
              <CardTitle>Alternative Suggestions</CardTitle>
              <CardDescription>
                LLM-assisted scenario alternatives with governance flags and evidence gaps
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <label htmlFor="suggestions-select" className="text-sm font-medium mb-1 block">Select Scenario</label>
                  <select
                    id="suggestions-select"
                    value={suggestionsScenarioId}
                    onChange={(e) => setSuggestionsScenarioId(e.target.value)}
                    className="border rounded px-3 py-1.5 text-sm w-full"
                  >
                    <option value="">Select scenario...</option>
                    {scenarios.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>
                <Button onClick={handleLoadSuggestions} disabled={loadingSuggestions || !suggestionsScenarioId} variant="outline">
                  {loadingSuggestions ? <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" /> : <Eye className="h-3 w-3 mr-1.5" />}
                  Load
                </Button>
                <Button onClick={handleGenerateSuggestions} disabled={generatingSuggestions || !suggestionsScenarioId}>
                  {generatingSuggestions ? <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" /> : <Lightbulb className="h-3 w-3 mr-1.5" />}
                  Generate
                </Button>
              </div>

              {suggestions.length > 0 && (
                <div className="space-y-3">
                  {suggestions.map((s) => (
                    <SuggestionCard key={s.id} suggestion={s} onDispositionChange={handleDispositionChange} />
                  ))}
                </div>
              )}

              {suggestions.length === 0 && suggestionsScenarioId && !loadingSuggestions && (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No suggestions yet. Click Generate to request LLM-assisted alternatives.
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ---- Financial Tab ---- */}
        <TabsContent value="financial">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Financial Assumptions & Impact</CardTitle>
                  <CardDescription>
                    Manage cost assumptions and view financial impact estimation
                  </CardDescription>
                </div>
                {financialScenarioId && (
                  <Button size="sm" variant="outline" onClick={() => setShowAssumptionForm(!showAssumptionForm)}>
                    <Plus className="h-3 w-3 mr-1.5" />
                    Add Assumption
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <label htmlFor="financial-select" className="text-sm font-medium mb-1 block">Select Scenario</label>
                  <select
                    id="financial-select"
                    value={financialScenarioId}
                    onChange={(e) => setFinancialScenarioId(e.target.value)}
                    className="border rounded px-3 py-1.5 text-sm w-full"
                  >
                    <option value="">Select scenario...</option>
                    {scenarios.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>
                <Button onClick={handleLoadFinancial} disabled={loadingFinancial || !financialScenarioId}>
                  {loadingFinancial ? <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" /> : <DollarSign className="h-3 w-3 mr-1.5" />}
                  Load
                </Button>
              </div>

              {showAssumptionForm && (
                <div className="border rounded-lg p-4 space-y-3 bg-muted/30">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <input type="text" placeholder="Name" value={newAssumption.name}
                      onChange={(e) => setNewAssumption({ ...newAssumption, name: e.target.value })}
                      className="border rounded px-3 py-1.5 text-sm" />
                    <select value={newAssumption.assumption_type}
                      onChange={(e) => setNewAssumption({ ...newAssumption, assumption_type: e.target.value as FinancialAssumptionType })}
                      className="border rounded px-3 py-1.5 text-sm">
                      <option value="cost_per_role">Cost Per Role</option>
                      <option value="technology_cost">Technology Cost</option>
                      <option value="volume_forecast">Volume Forecast</option>
                      <option value="implementation_cost">Implementation Cost</option>
                    </select>
                    <input type="number" placeholder="Value" value={newAssumption.value || ""}
                      onChange={(e) => setNewAssumption({ ...newAssumption, value: parseFloat(e.target.value) || 0 })}
                      className="border rounded px-3 py-1.5 text-sm" />
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <input type="text" placeholder="Unit (e.g. USD/month)" value={newAssumption.unit}
                      onChange={(e) => setNewAssumption({ ...newAssumption, unit: e.target.value })}
                      className="border rounded px-3 py-1.5 text-sm" />
                    <div className="flex items-center gap-2">
                      <label className="text-sm">Confidence:</label>
                      <input type="range" min="0" max="1" step="0.05" value={newAssumption.confidence}
                        onChange={(e) => setNewAssumption({ ...newAssumption, confidence: parseFloat(e.target.value) })}
                        className="flex-1" />
                      <span className="text-sm font-medium w-12">{(newAssumption.confidence * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={handleCreateAssumption} disabled={!newAssumption.name.trim() || !newAssumption.unit.trim()}>Create</Button>
                    <Button size="sm" variant="ghost" onClick={() => setShowAssumptionForm(false)}>Cancel</Button>
                  </div>
                </div>
              )}

              {assumptions.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium mb-2">Assumptions</h3>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Name</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Value</TableHead>
                        <TableHead>Unit</TableHead>
                        <TableHead>Confidence</TableHead>
                        <TableHead className="w-10"></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {assumptions.map((a) => (
                        <TableRow key={a.id}>
                          <TableCell className="font-medium text-sm">{a.name}</TableCell>
                          <TableCell><Badge variant="outline">{a.assumption_type.replace(/_/g, " ")}</Badge></TableCell>
                          <TableCell className="text-sm">{a.value.toLocaleString()}</TableCell>
                          <TableCell className="text-sm text-muted-foreground">{a.unit}</TableCell>
                          <TableCell className="text-sm">{(a.confidence * 100).toFixed(0)}%</TableCell>
                          <TableCell>
                            <Button size="sm" variant="ghost" onClick={() => handleDeleteAssumption(a.id)}>
                              <Trash2 className="h-3 w-3 text-muted-foreground" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}

              {financialImpact && (
                <div className="space-y-3">
                  <h3 className="text-sm font-medium">Financial Impact</h3>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <Card>
                      <CardContent className="pt-4 pb-3">
                        <div className="text-2xl font-bold text-emerald-600">${financialImpact.cost_range.optimistic.toLocaleString()}</div>
                        <div className="text-xs text-muted-foreground">Optimistic</div>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="pt-4 pb-3">
                        <div className="text-2xl font-bold">${financialImpact.cost_range.expected.toLocaleString()}</div>
                        <div className="text-xs text-muted-foreground">Expected</div>
                      </CardContent>
                    </Card>
                    <Card>
                      <CardContent className="pt-4 pb-3">
                        <div className="text-2xl font-bold text-red-600">${financialImpact.cost_range.pessimistic.toLocaleString()}</div>
                        <div className="text-xs text-muted-foreground">Pessimistic</div>
                      </CardContent>
                    </Card>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ---- Ranking Tab ---- */}
        <TabsContent value="ranking">
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
                    <label className="text-xs font-medium capitalize">{dim}: {(weights[dim] * 100).toFixed(0)}%</label>
                    <input type="range" min="0" max="1" step="0.05" value={weights[dim]}
                      onChange={(e) => setWeights({ ...weights, [dim]: parseFloat(e.target.value) })}
                      className="w-full" />
                  </div>
                ))}
              </div>

              <Button onClick={handleLoadRanking} disabled={loadingRanking || scenarios.length === 0}>
                {loadingRanking ? <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" /> : <Trophy className="h-3 w-3 mr-1.5" />}
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
                          <Badge variant={r.composite_score >= 0.7 ? "default" : r.composite_score >= 0.4 ? "secondary" : "outline"}>
                            {(r.composite_score * 100).toFixed(1)}%
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm">{(r.evidence_score * 100).toFixed(1)}%</TableCell>
                        <TableCell className="text-sm">{(r.simulation_score * 100).toFixed(1)}%</TableCell>
                        <TableCell className="text-sm">{(r.financial_score * 100).toFixed(1)}%</TableCell>
                        <TableCell className="text-sm">{(r.governance_score * 100).toFixed(1)}%</TableCell>
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
        </TabsContent>
      </Tabs>
    </div>
  );
}
