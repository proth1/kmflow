/**
 * TOM dimension maturity card.
 *
 * Displays current vs target maturity for a TOM dimension with
 * a visual progress bar and gap indicator.
 */

import { Card, CardContent, CardHeader } from "@/components/ui/card";

export interface TOMDimensionProps {
  dimension: string;
  currentMaturity: number;
  targetMaturity: number;
  gapType: string;
  severity: number;
}

const DIMENSION_LABELS: Record<string, string> = {
  process_architecture: "Process Architecture",
  people_and_organization: "People & Organization",
  technology_and_data: "Technology & Data",
  governance_structures: "Governance Structures",
  performance_management: "Performance Management",
  risk_and_compliance: "Risk & Compliance",
};

const GAP_BADGE_CLASSES: Record<string, string> = {
  no_gap: "bg-green-50 text-green-700",
  deviation: "bg-yellow-50 text-yellow-700",
  partial_gap: "bg-orange-50 text-orange-700",
  full_gap: "bg-red-50 text-red-600",
};

const GAP_BAR_COLOR_CLASSES: Record<string, string> = {
  no_gap: "bg-green-700",
  deviation: "bg-yellow-600",
  partial_gap: "bg-orange-700",
  full_gap: "bg-red-600",
};

const GAP_BORDER_CLASSES: Record<string, string> = {
  no_gap: "border-green-200",
  deviation: "border-yellow-200",
  partial_gap: "border-orange-200",
  full_gap: "border-red-200",
};

export default function TOMDimensionCard({
  dimension,
  currentMaturity,
  targetMaturity,
  gapType,
  severity,
}: TOMDimensionProps) {
  const label = DIMENSION_LABELS[dimension] ?? dimension.replace(/_/g, " ");
  const badgeClass = GAP_BADGE_CLASSES[gapType] ?? GAP_BADGE_CLASSES.deviation;
  const barColorClass = GAP_BAR_COLOR_CLASSES[gapType] ?? GAP_BAR_COLOR_CLASSES.deviation;
  const borderClass = GAP_BORDER_CLASSES[gapType] ?? GAP_BORDER_CLASSES.deviation;
  const currentPct = Math.min((currentMaturity / 5) * 100, 100);
  const targetPct = Math.min((targetMaturity / 5) * 100, 100);

  return (
    <Card
      className={`border ${borderClass}`}
      data-testid="tom-dimension-card"
    >
      <CardHeader className="pb-0 pt-5 px-5">
        <div className="flex justify-between items-center">
          <span className="text-sm font-semibold text-[hsl(var(--foreground))]">
            {label}
          </span>
          <span
            className={`inline-block px-2.5 py-0.5 rounded-full text-[11px] font-semibold uppercase ${badgeClass}`}
          >
            {gapType.replace(/_/g, " ")}
          </span>
        </div>
      </CardHeader>

      <CardContent className="px-5 pb-5 pt-3 flex flex-col gap-3">
        {/* Maturity Bar */}
        <div>
          <div className="flex justify-between text-xs text-[hsl(var(--muted-foreground))] mb-1.5">
            <span>Current: {currentMaturity.toFixed(1)}</span>
            <span>Target: {targetMaturity.toFixed(1)}</span>
          </div>
          <div className="relative h-3 bg-gray-100 rounded-md overflow-visible">
            {/* Current maturity bar */}
            <div
              className={`absolute top-0 left-0 h-full rounded-md opacity-70 transition-[width] duration-300 ${barColorClass}`}
              style={{ width: `${currentPct}%` }}
            />
            {/* Target marker */}
            <div
              className="absolute top-[-2px] w-[3px] h-4 bg-gray-900 rounded-sm -translate-x-px"
              style={{ left: `${targetPct}%` }}
            />
          </div>
        </div>

        {/* Severity */}
        {severity > 0 && (
          <div className="text-xs text-[hsl(var(--muted-foreground))]">
            Severity: {(severity * 100).toFixed(0)}%
          </div>
        )}
      </CardContent>
    </Card>
  );
}
