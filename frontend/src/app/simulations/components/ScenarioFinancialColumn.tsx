"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import CostRangeDisplay from "./CostRangeDisplay";
import AssumptionTable from "./AssumptionTable";
import type { CostRange } from "./CostRangeDisplay";
import type { EngagementAssumptionData } from "@/lib/api/simulations";
import type { SensitivityEntryData } from "@/lib/api/simulations";

interface ScenarioFinancialColumnProps {
  scenarioName: string;
  costRange: CostRange;
  topSensitivities: SensitivityEntryData[];
  overallConfidence: number;
  assumptions: EngagementAssumptionData[];
  onAssumptionSave: (id: string, updates: { value?: number; confidence?: number }) => Promise<void>;
}

function confidenceBadgeVariant(confidence: number): "default" | "secondary" | "destructive" {
  if (confidence >= 0.8) return "default";
  if (confidence >= 0.5) return "secondary";
  return "destructive";
}

export default function ScenarioFinancialColumn({
  scenarioName,
  costRange,
  topSensitivities,
  overallConfidence,
  assumptions,
  onAssumptionSave,
}: ScenarioFinancialColumnProps) {
  return (
    <Card className="flex flex-col h-full">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{scenarioName}</CardTitle>
          <Badge variant={confidenceBadgeVariant(overallConfidence)}>
            {(overallConfidence * 100).toFixed(0)}% confidence
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 flex-1">
        <CostRangeDisplay range={costRange} label="Cost Range" />

        {topSensitivities.length > 0 && (
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">
              Top Sensitivities
            </div>
            <div className="space-y-1.5">
              {topSensitivities.map((s, i) => (
                <div key={i} className="flex items-center justify-between text-sm">
                  <span className="truncate mr-2">{s.assumption_name}</span>
                  <span className="text-muted-foreground text-xs shrink-0">
                    ${s.impact_range.optimistic.toLocaleString()} &ndash; ${s.impact_range.pessimistic.toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">
            Assumptions
          </div>
          <AssumptionTable assumptions={assumptions} onSave={onAssumptionSave} />
        </div>
      </CardContent>
    </Card>
  );
}
