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
  type ScenarioData,
  type SimulationResultData,
  type ScenarioComparisonData,
  type ScenarioCoverageData,
  type EpistemicPlanData,
  type AlternativeSuggestionData,
  type FinancialAssumptionData,
  type FinancialImpactData,
  type ScenarioRankingData,
  type SuggestionDispositionType,
} from "@/lib/api";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  FlaskConical,
  Play,
  RefreshCw,
  GitCompare,
  Eye,
  Brain,
  Lightbulb,
  DollarSign,
  Trophy,
} from "lucide-react";
import { Button } from "@/components/ui/button";

import ErrorBanner from "./components/ErrorBanner";
import StatsCards from "./components/StatsCards";
import ScenariosTab from "./components/ScenariosTab";
import ResultsTab from "./components/ResultsTab";
import CompareTab from "./components/CompareTab";
import CoverageTab from "./components/CoverageTab";
import EpistemicTab from "./components/EpistemicTab";
import SuggestionsTab from "./components/SuggestionsTab";
import FinancialTab from "./components/FinancialTab";
import RankingTab from "./components/RankingTab";
import type { NewAssumptionState, RankingWeights } from "./components/types";

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
  const [newAssumption, setNewAssumption] = useState<NewAssumptionState>({
    name: "",
    assumption_type: "cost_per_role",
    value: 0,
    unit: "",
    confidence: 0.8,
  });

  // Ranking state
  const [rankingData, setRankingData] = useState<ScenarioRankingData | null>(null);
  const [loadingRanking, setLoadingRanking] = useState(false);
  const [weights, setWeights] = useState<RankingWeights>({
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

      {error && <ErrorBanner error={error} />}

      <StatsCards scenarios={scenarios} results={results} />

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

        <TabsContent value="scenarios">
          <ScenariosTab
            scenarios={scenarios}
            showCreate={showCreate}
            newName={newName}
            newType={newType}
            newDescription={newDescription}
            creating={creating}
            running={running}
            onToggleCreate={() => setShowCreate(!showCreate)}
            onNewNameChange={setNewName}
            onNewTypeChange={setNewType}
            onNewDescriptionChange={setNewDescription}
            onCreate={handleCreate}
            onCancelCreate={() => { setShowCreate(false); setError(null); }}
            onRun={handleRun}
          />
        </TabsContent>

        <TabsContent value="results">
          <ResultsTab results={results} />
        </TabsContent>

        <TabsContent value="compare">
          <CompareTab
            scenarios={scenarios}
            baselineId={baselineId}
            compareIds={compareIds}
            comparisonData={comparisonData}
            comparing={comparing}
            onBaselineChange={setBaselineId}
            onToggleCompareId={toggleCompareId}
            onCompare={handleCompare}
          />
        </TabsContent>

        <TabsContent value="coverage">
          <CoverageTab
            scenarios={scenarios}
            coverageScenarioId={coverageScenarioId}
            coverageData={coverageData}
            loadingCoverage={loadingCoverage}
            onScenarioChange={setCoverageScenarioId}
            onLoadCoverage={handleLoadCoverage}
          />
        </TabsContent>

        <TabsContent value="epistemic">
          <EpistemicTab
            scenarios={scenarios}
            epistemicScenarioId={epistemicScenarioId}
            epistemicPlan={epistemicPlan}
            loadingEpistemic={loadingEpistemic}
            onScenarioChange={setEpistemicScenarioId}
            onLoadEpistemic={handleLoadEpistemic}
          />
        </TabsContent>

        <TabsContent value="suggestions">
          <SuggestionsTab
            scenarios={scenarios}
            suggestionsScenarioId={suggestionsScenarioId}
            suggestions={suggestions}
            loadingSuggestions={loadingSuggestions}
            generatingSuggestions={generatingSuggestions}
            onScenarioChange={setSuggestionsScenarioId}
            onLoadSuggestions={handleLoadSuggestions}
            onGenerateSuggestions={handleGenerateSuggestions}
            onDispositionChange={handleDispositionChange}
          />
        </TabsContent>

        <TabsContent value="financial">
          <FinancialTab
            scenarios={scenarios}
            financialScenarioId={financialScenarioId}
            assumptions={assumptions}
            financialImpact={financialImpact}
            loadingFinancial={loadingFinancial}
            showAssumptionForm={showAssumptionForm}
            newAssumption={newAssumption}
            onScenarioChange={setFinancialScenarioId}
            onLoadFinancial={handleLoadFinancial}
            onToggleAssumptionForm={() => setShowAssumptionForm(!showAssumptionForm)}
            onNewAssumptionChange={setNewAssumption}
            onCreateAssumption={handleCreateAssumption}
            onCancelAssumptionForm={() => setShowAssumptionForm(false)}
            onDeleteAssumption={handleDeleteAssumption}
          />
        </TabsContent>

        <TabsContent value="ranking">
          <RankingTab
            scenarios={scenarios}
            rankingData={rankingData}
            loadingRanking={loadingRanking}
            weights={weights}
            onWeightsChange={setWeights}
            onLoadRanking={handleLoadRanking}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
