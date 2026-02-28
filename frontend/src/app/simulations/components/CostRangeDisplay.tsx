"use client";

import {
  Card,
  CardContent,
} from "@/components/ui/card";

/**
 * A cost range requiring low, mid, and high values.
 * This type enforces that all three values must be present —
 * a plain `number` prop is rejected at compile time.
 */
export interface CostRange {
  low: number;
  mid: number;
  high: number;
}

interface CostRangeDisplayProps {
  range: CostRange;
  label?: string;
  currency?: string;
}

function formatCurrency(value: number, currency: string): string {
  return `${currency}${Math.abs(value).toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`;
}

/**
 * Renders a cost range as three labeled cards (Low, Mid, High).
 *
 * Requires a `CostRange` object — never a single number.
 * The TypeScript type system prevents passing `number` as `range`.
 */
export default function CostRangeDisplay({
  range,
  label,
  currency = "$",
}: CostRangeDisplayProps) {
  return (
    <div>
      {label && (
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">
          {label}
        </div>
      )}
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <CardContent className="pt-4 pb-3">
            <div className="text-xl font-bold text-emerald-600">
              {formatCurrency(range.low, currency)}
            </div>
            <div className="text-xs text-muted-foreground">Low</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-3">
            <div className="text-xl font-bold">
              {formatCurrency(range.mid, currency)}
            </div>
            <div className="text-xs text-muted-foreground">Mid</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-3">
            <div className="text-xl font-bold text-red-600">
              {formatCurrency(range.high, currency)}
            </div>
            <div className="text-xs text-muted-foreground">High</div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
