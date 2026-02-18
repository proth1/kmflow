/**
 * KPI metric card for dashboard display.
 *
 * Shows a label, value, and optional status indicator with
 * color-coding based on threshold states (good/warning/critical).
 */

import { cn } from "@/lib/utils";

export type KPIStatus = "good" | "warning" | "critical" | "neutral";

interface KPICardProps {
  label: string;
  value: string | number;
  status?: KPIStatus;
  subtitle?: string;
}

const STATUS_DOT_CLASSES: Record<KPIStatus, string> = {
  good: "bg-green-500",
  warning: "bg-yellow-500",
  critical: "bg-red-500",
  neutral: "bg-gray-400",
};

export default function KPICard({
  label,
  value,
  status = "neutral",
  subtitle,
}: KPICardProps) {
  return (
    <div
      className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-5 flex flex-col gap-2 min-w-40"
      data-testid="kpi-card"
    >
      <div className="text-xs font-medium uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
        {label}
      </div>
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "w-2.5 h-2.5 rounded-full shrink-0",
            STATUS_DOT_CLASSES[status]
          )}
        />
        <span className="text-3xl font-bold text-[hsl(var(--foreground))] leading-none">
          {value}
        </span>
      </div>
      {subtitle && (
        <div className="text-xs text-[hsl(var(--muted-foreground))]">{subtitle}</div>
      )}
    </div>
  );
}
