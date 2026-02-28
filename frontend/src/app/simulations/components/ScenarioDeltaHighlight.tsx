"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { CostRange } from "./CostRangeDisplay";

interface ScenarioDeltaHighlightProps {
  scenarioA: { name: string; costRange: CostRange };
  scenarioB: { name: string; costRange: CostRange };
  method?: string;
}

function formatDelta(value: number): string {
  const abs = Math.abs(value);
  const formatted = `$${abs.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`;
  return value < 0 ? `-${formatted}` : `+${formatted}`;
}

/**
 * Shows the cost delta between two scenarios with color highlighting.
 * Green indicates savings (negative delta), red indicates increased cost.
 */
export default function ScenarioDeltaHighlight({
  scenarioA,
  scenarioB,
  method,
}: ScenarioDeltaHighlightProps) {
  const deltaLow = scenarioB.costRange.low - scenarioA.costRange.low;
  const deltaMid = scenarioB.costRange.mid - scenarioA.costRange.mid;
  const deltaHigh = scenarioB.costRange.high - scenarioA.costRange.high;

  // Determine if overall is savings or cost increase
  const isSaving = deltaMid < 0;
  const colorClass = isSaving ? "text-emerald-600" : "text-red-600";
  const bgClass = isSaving ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200";

  // Build human-friendly delta range label
  const absLow = Math.min(Math.abs(deltaLow), Math.abs(deltaHigh));
  const absHigh = Math.max(Math.abs(deltaLow), Math.abs(deltaHigh));
  const rangeLabel = isSaving
    ? `Save $${absLow.toLocaleString()}\u2013$${absHigh.toLocaleString()}`
    : `Cost increase $${absLow.toLocaleString()}\u2013$${absHigh.toLocaleString()}`;

  return (
    <Card className={`border ${bgClass}`}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">
          {scenarioB.name} vs {scenarioA.name}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className={`text-xl font-bold ${colorClass}`}>{rangeLabel}</div>

        <div className="grid grid-cols-3 gap-3">
          <div>
            <div className={`text-lg font-semibold ${colorClass}`}>
              {formatDelta(deltaLow)}
            </div>
            <div className="text-xs text-muted-foreground">Low</div>
          </div>
          <div>
            <div className={`text-lg font-semibold ${colorClass}`}>
              {formatDelta(deltaMid)}
            </div>
            <div className="text-xs text-muted-foreground">Mid</div>
          </div>
          <div>
            <div className={`text-lg font-semibold ${colorClass}`}>
              {formatDelta(deltaHigh)}
            </div>
            <div className="text-xs text-muted-foreground">High</div>
          </div>
        </div>

        {method && (
          <div className="text-xs text-muted-foreground">
            Method: {method}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
