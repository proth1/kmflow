"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowLeftRight, RefreshCw } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import ScenarioFinancialColumn from "../components/ScenarioFinancialColumn";
import ScenarioDeltaHighlight from "../components/ScenarioDeltaHighlight";
import type { CostRange } from "../components/CostRangeDisplay";
import type {
  ScenarioData,
  FinancialImpactData,
  EngagementAssumptionData,
  SensitivityEntryData,
} from "@/lib/api/simulations";
import {
  fetchScenarios,
  fetchFinancialImpact,
  fetchEngagementAssumptions,
  updateEngagementAssumption,
} from "@/lib/api/simulations";

interface ScenarioColumn {
  scenario: ScenarioData;
  impact: FinancialImpactData;
  assumptions: EngagementAssumptionData[];
  costRange: CostRange;
  topSensitivities: SensitivityEntryData[];
}

function impactToCostRange(impact: FinancialImpactData): CostRange {
  return {
    low: impact.cost_range.optimistic,
    mid: impact.cost_range.expected,
    high: impact.cost_range.pessimistic,
  };
}

export default function FinancialImpactPage() {
  const searchParams = useSearchParams();
  const engagementId = searchParams.get("engagement_id") ?? "";

  const [scenarios, setScenarios] = useState<ScenarioData[]>([]);
  const [columns, setColumns] = useState<ScenarioColumn[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [compareA, setCompareA] = useState<string>("");
  const [compareB, setCompareB] = useState<string>("");

  // Use ref to avoid stale closure in loadAllScenarios
  const compareInitialized = useRef(false);

  // Load scenarios when engagement ID is set
  useEffect(() => {
    if (!engagementId) return;
    let cancelled = false;

    async function load() {
      try {
        const result = await fetchScenarios(engagementId);
        if (!cancelled) setScenarios(result.items);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load scenarios");
      }
    }
    load();

    return () => { cancelled = true; };
  }, [engagementId]);

  // Load all scenario data in parallel
  const loadAllScenarios = useCallback(async () => {
    if (scenarios.length === 0) return;
    setLoading(true);
    setError(null);

    try {
      // Fetch assumptions once (engagement-scoped, same for all scenarios)
      const assumptions = await fetchEngagementAssumptions(engagementId);

      // Fetch financial impact for all scenarios in parallel
      const cols = await Promise.all(
        scenarios.map(async (scenario): Promise<ScenarioColumn> => {
          const impact = await fetchFinancialImpact(scenario.id);
          return {
            scenario,
            impact,
            assumptions: assumptions.items,
            costRange: impactToCostRange(impact),
            topSensitivities: impact.sensitivity_analysis.slice(0, 3),
          };
        }),
      );

      setColumns(cols);

      // Initialize comparison selectors once (avoid re-render loop)
      if (!compareInitialized.current && cols.length >= 2) {
        setCompareA(cols[0].scenario.id);
        setCompareB(cols[1].scenario.id);
        compareInitialized.current = true;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load financial data");
    } finally {
      setLoading(false);
    }
  }, [scenarios, engagementId]);

  // Auto-load when scenarios are available
  useEffect(() => {
    if (scenarios.length > 0 && columns.length === 0) {
      loadAllScenarios();
    }
  }, [scenarios, columns.length, loadAllScenarios]);

  // Handle assumption edit with cache invalidation
  const handleAssumptionSave = useCallback(async (
    assumptionId: string,
    updates: { value?: number; confidence?: number },
  ) => {
    await updateEngagementAssumption(engagementId, assumptionId, updates);
    setStatusMessage("Assumption updated — recalculating estimates...");

    // Reload financial data to reflect updated assumptions
    await loadAllScenarios();
    setStatusMessage("Estimates updated successfully");
    setTimeout(() => setStatusMessage(null), 3000);
  }, [engagementId, loadAllScenarios]);

  const colA = columns.find((c) => c.scenario.id === compareA);
  const colB = columns.find((c) => c.scenario.id === compareB);

  if (!engagementId) {
    return (
      <div className="container mx-auto py-8">
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            No engagement selected. Add <code>?engagement_id=UUID</code> to the URL.
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Financial Impact Dashboard</h1>
          <p className="text-muted-foreground text-sm">
            Side-by-side scenario cost comparison with ranges and assumptions
          </p>
        </div>
        <Button
          variant="outline"
          onClick={loadAllScenarios}
          disabled={loading}
        >
          {loading ? (
            <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4 mr-2" />
          )}
          Refresh
        </Button>
      </div>

      {statusMessage && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-lg px-4 py-2 text-sm">
          {statusMessage}
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-2 text-sm">
          {error}
        </div>
      )}

      {/* Side-by-side scenario columns */}
      {columns.length > 0 && (
        <div
          className="grid gap-6"
          style={{ gridTemplateColumns: `repeat(${Math.min(columns.length, 3)}, 1fr)` }}
        >
          {columns.map((col) => (
            <ScenarioFinancialColumn
              key={col.scenario.id}
              scenarioName={col.scenario.name}
              costRange={col.costRange}
              topSensitivities={col.topSensitivities}
              overallConfidence={
                col.assumptions.length > 0
                  ? col.assumptions.reduce((sum, a) => sum + a.confidence, 0) /
                    col.assumptions.length
                  : 0
              }
              assumptions={col.assumptions}
              onAssumptionSave={handleAssumptionSave}
            />
          ))}
        </div>
      )}

      {/* Delta comparison */}
      {columns.length >= 2 && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <ArrowLeftRight className="h-4 w-4 text-muted-foreground" />
              <CardTitle className="text-base">Scenario Comparison</CardTitle>
            </div>
            <CardDescription>
              Select two scenarios to compare cost deltas
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-4 items-end">
              <div className="flex-1">
                <label className="text-sm font-medium mb-1 block">Scenario A (baseline)</label>
                <select
                  value={compareA}
                  onChange={(e) => setCompareA(e.target.value)}
                  className="border rounded px-3 py-1.5 text-sm w-full"
                >
                  {columns.map((c) => (
                    <option key={c.scenario.id} value={c.scenario.id}>
                      {c.scenario.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex-1">
                <label className="text-sm font-medium mb-1 block">Scenario B</label>
                <select
                  value={compareB}
                  onChange={(e) => setCompareB(e.target.value)}
                  className="border rounded px-3 py-1.5 text-sm w-full"
                >
                  {columns.map((c) => (
                    <option key={c.scenario.id} value={c.scenario.id}>
                      {c.scenario.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {colA && colB && compareA !== compareB && (
              <ScenarioDeltaHighlight
                scenarioA={{ name: colA.scenario.name, costRange: colA.costRange }}
                scenarioB={{ name: colB.scenario.name, costRange: colB.costRange }}
              />
            )}
          </CardContent>
        </Card>
      )}

      {!loading && columns.length === 0 && scenarios.length === 0 && (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            No scenarios found for this engagement. Create scenarios in the Simulations tab first.
          </CardContent>
        </Card>
      )}
    </div>
  );
}
