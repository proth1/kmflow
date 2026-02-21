import type {
  AlternativeSuggestionData,
  EpistemicPlanData,
  FinancialAssumptionData,
  FinancialAssumptionType,
  FinancialImpactData,
  ScenarioComparisonData,
  ScenarioCoverageData,
  ScenarioData,
  ScenarioRankingData,
  SimulationResultData,
  SuggestionDispositionType,
} from "@/lib/api";

export type {
  AlternativeSuggestionData,
  EpistemicPlanData,
  FinancialAssumptionData,
  FinancialAssumptionType,
  FinancialImpactData,
  ScenarioComparisonData,
  ScenarioCoverageData,
  ScenarioData,
  ScenarioRankingData,
  SimulationResultData,
  SuggestionDispositionType,
};

export interface NewAssumptionState {
  name: string;
  assumption_type: FinancialAssumptionType;
  value: number;
  unit: string;
  confidence: number;
}

export interface RankingWeights {
  evidence: number;
  simulation: number;
  financial: number;
  governance: number;
}
