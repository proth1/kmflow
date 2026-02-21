"use client";

import { RefreshCw, Eye, Lightbulb } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import SuggestionCard from "@/components/SuggestionCard";
import type {
  AlternativeSuggestionData,
  ScenarioData,
  SuggestionDispositionType,
} from "./types";

interface SuggestionsTabProps {
  scenarios: ScenarioData[];
  suggestionsScenarioId: string;
  suggestions: AlternativeSuggestionData[];
  loadingSuggestions: boolean;
  generatingSuggestions: boolean;
  onScenarioChange: (id: string) => void;
  onLoadSuggestions: () => void;
  onGenerateSuggestions: () => void;
  onDispositionChange: (
    suggestionId: string,
    disposition: SuggestionDispositionType,
    notes?: string,
  ) => Promise<void>;
}

export default function SuggestionsTab({
  scenarios,
  suggestionsScenarioId,
  suggestions,
  loadingSuggestions,
  generatingSuggestions,
  onScenarioChange,
  onLoadSuggestions,
  onGenerateSuggestions,
  onDispositionChange,
}: SuggestionsTabProps) {
  return (
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
            <label htmlFor="suggestions-select" className="text-sm font-medium mb-1 block">
              Select Scenario
            </label>
            <select
              id="suggestions-select"
              value={suggestionsScenarioId}
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
            onClick={onLoadSuggestions}
            disabled={loadingSuggestions || !suggestionsScenarioId}
            variant="outline"
          >
            {loadingSuggestions ? (
              <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" />
            ) : (
              <Eye className="h-3 w-3 mr-1.5" />
            )}
            Load
          </Button>
          <Button
            onClick={onGenerateSuggestions}
            disabled={generatingSuggestions || !suggestionsScenarioId}
          >
            {generatingSuggestions ? (
              <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" />
            ) : (
              <Lightbulb className="h-3 w-3 mr-1.5" />
            )}
            Generate
          </Button>
        </div>

        {suggestions.length > 0 && (
          <div className="space-y-3">
            {suggestions.map((s) => (
              <SuggestionCard
                key={s.id}
                suggestion={s}
                onDispositionChange={onDispositionChange}
              />
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
  );
}
